import json
import re
from pathlib import Path
from collections.abc import Generator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.prompt import build_messages, build_rag_prompt
from app.db.database import Conversation, Document, Message, SessionLocal, utc_now
from app.schemas.rag_schema import (
    DocumentBatchUploadResponse,
    DocumentUploadFailure,
    DocumentSummary,
    DocumentUploadResponse,
    RagChatRequest,
    RagChatResponse,
    RagSource,
)
from app.services.chat_service import build_conversation_title
from app.services.chroma_service import ChromaServiceError, chroma_service
from app.services.document_parser import (
    DocumentParseError,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    extract_text_from_upload,
    get_file_type_from_filename,
)
from app.services.embedding_service import EmbeddingServiceError, embedding_service
from app.services.llm_service import LLMServiceError, llm_service


ALLOWED_DOCUMENT_EXTENSIONS = SUPPORTED_DOCUMENT_EXTENSIONS
MAX_CHUNK_CHARS = 800
MIN_CHUNK_CHARS = 20
# 限制单次上传的 chunk 数，避免误传超大文件造成 embedding 费用和耗时失控。
MAX_DOCUMENT_CHUNKS = 100
SINGLE_DOCUMENT_TOP_K = 5
MULTI_DOCUMENT_TOP_K = 10


class RagValidationError(ValueError):
    """RAG 请求参数或上传内容不合法。"""


class DocumentNotFoundError(LookupError):
    """请求的 document_id 不存在。"""


class ConversationNotFoundError(LookupError):
    """请求继续一个不存在的会话。"""


class RagEmbeddingError(RuntimeError):
    """RAG 生成 embedding 失败。"""


class RagVectorStoreError(RuntimeError):
    """RAG 写入或检索 Chroma 失败。"""


class RagModelError(RuntimeError):
    """RAG 调用大模型失败。"""


class RagDatabaseError(RuntimeError):
    """RAG 数据库写入失败。"""


def split_text_into_chunks(
    text: str,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
    min_chunk_chars: int = MIN_CHUNK_CHARS,
) -> list[str]:
    """按空行优先切分文本，超长段落再按固定字符数切分。"""
    # 先统一换行符，避免 Windows 和 Unix 换行差异影响段落切分。
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", normalized)
        if paragraph.strip()
    ]

    raw_chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chunk_chars:
            raw_chunks.append(paragraph)
            continue

        # 单个段落过长时按固定字符数切开，保证 Prompt 不会塞入过大的片段。
        for start in range(0, len(paragraph), max_chunk_chars):
            chunk = paragraph[start : start + max_chunk_chars].strip()
            if chunk:
                raw_chunks.append(chunk)

    return _merge_short_chunks(raw_chunks, max_chunk_chars, min_chunk_chars)


def _merge_short_chunks(
    chunks: list[str],
    max_chunk_chars: int,
    min_chunk_chars: int,
) -> list[str]:
    # 太短的段落和相邻内容合并，减少没有信息量的孤立 chunk。
    merged_chunks: list[str] = []
    buffer = ""

    for chunk in chunks:
        if len(chunk) < min_chunk_chars:
            buffer = f"{buffer}\n\n{chunk}" if buffer else chunk
            if len(buffer) >= min_chunk_chars:
                merged_chunks.append(buffer)
                buffer = ""
            continue

        if buffer:
            combined = f"{buffer}\n\n{chunk}"
            if len(combined) <= max_chunk_chars:
                chunk = combined
            else:
                merged_chunks.append(buffer)
            buffer = ""

        merged_chunks.append(chunk)

    if buffer:
        merged_chunks.append(buffer)

    return merged_chunks


def _safe_filename(filename: str | None) -> str:
    if not filename:
        return ""

    # 去掉可能的路径部分，只保留浏览器上传的原始文件名。
    return Path(filename.replace("\\", "/")).name


class RagService:
    """Chroma 版 RAG 业务层：上传入库、向量检索、Prompt 构造和消息落库。"""

    def create_document(
        self,
        db: Session,
        filename: str | None,
        content_bytes: bytes,
    ) -> DocumentUploadResponse:
        safe_filename = _safe_filename(filename)
        suffix = Path(safe_filename).suffix.lower()

        if not safe_filename or suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise RagValidationError("当前仅支持 TXT、Markdown、PDF、DOCX 文件。")
        if not content_bytes:
            raise RagValidationError("上传文件不能为空。")

        try:
            content = extract_text_from_upload(safe_filename, content_bytes)
            file_type = get_file_type_from_filename(safe_filename)
        except DocumentParseError as exc:
            raise RagValidationError(str(exc)) from exc

        if not content.strip():
            raise RagValidationError("上传文件内容不能为空。")

        # 本版只把 document 元信息写入 SQLite，chunk 文本和向量写入 Chroma。
        chunks = split_text_into_chunks(content)
        if not chunks:
            raise RagValidationError("文档没有可保存的文本片段。")
        if len(chunks) > MAX_DOCUMENT_CHUNKS:
            raise RagValidationError(
                f"当前最多支持一次上传 {MAX_DOCUMENT_CHUNKS} 个 chunk，请拆分文档后再上传。"
            )

        try:
            # 批量生成 chunk embedding，返回顺序需要和 chunks 保持一致。
            embeddings = embedding_service.get_embeddings(chunks)
        except EmbeddingServiceError as exc:
            raise RagEmbeddingError(str(exc)) from exc

        document: Document | None = None
        try:
            # 先 flush 拿到 document.id，用它生成 Chroma 里的稳定 chunk id。
            document = Document(
                filename=safe_filename,
                file_type=file_type,
                chunk_count=len(chunks),
                chroma_collection=settings.chroma_collection_name,
                content="",
            )
            db.add(document)
            db.flush()

            # Chroma 写入成功后再提交 SQLite，避免出现只有元信息没有向量数据的文档。
            chroma_service.add_chunks_to_chroma(
                document_id=document.id,
                filename=safe_filename,
                file_type=document.file_type,
                chunks=chunks,
                embeddings=embeddings,
            )
            db.commit()
        except ChromaServiceError as exc:
            db.rollback()
            if document is not None and document.id is not None:
                # Chroma 写入半失败时尽量清理，避免留下不可见的脏向量。
                self._delete_chroma_chunks_safely(document.id)
            raise RagVectorStoreError(str(exc)) from exc
        except SQLAlchemyError as exc:
            db.rollback()
            if document is not None and document.id is not None:
                self._delete_chroma_chunks_safely(document.id)
            raise RagDatabaseError("数据库保存文档元信息失败。") from exc

        return DocumentUploadResponse(
            document_id=document.id,
            filename=document.filename,
            file_type=document.file_type or file_type,
            chunk_count=document.chunk_count,
        )

    def create_documents_batch(
        self,
        db: Session,
        files: list[tuple[str | None, bytes]],
    ) -> DocumentBatchUploadResponse:
        uploaded: list[DocumentUploadResponse] = []
        failed: list[DocumentUploadFailure] = []

        for filename, content_bytes in files:
            safe_filename = _safe_filename(filename) or "未命名文件"
            try:
                uploaded.append(self.create_document(db, filename, content_bytes))
            except (
                RagValidationError,
                RagEmbeddingError,
                RagVectorStoreError,
                RagDatabaseError,
            ) as exc:
                failed.append(DocumentUploadFailure(filename=safe_filename, error=str(exc)))
            except Exception as exc:
                db.rollback()
                failed.append(DocumentUploadFailure(filename=safe_filename, error=str(exc)))

        return DocumentBatchUploadResponse(uploaded=uploaded, failed=failed)

    def list_documents(self, db: Session) -> list[DocumentSummary]:
        documents = (
            db.query(Document)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .all()
        )

        return [
            DocumentSummary(
                id=document.id,
                filename=document.filename,
                file_type=document.file_type,
                chunk_count=document.chunk_count or 0,
                created_at=document.created_at,
            )
            for document in documents
        ]

    def chat(self, db: Session, request: RagChatRequest) -> RagChatResponse:
        question = request.question.strip()
        if not question:
            raise RagValidationError("问题不能为空。")

        document_ids = self._resolve_document_ids(db, request)

        conversation = self._get_conversation(db, request.conversation_id)

        search_results = self._search_sources(question, document_ids)

        rag_prompt = build_rag_prompt(
            question,
            self._format_source_contents(search_results),
        )

        try:
            # 大模型只接收检索出的 top-k chunks，不接收整篇文档。
            answer = llm_service.chat(rag_prompt)
        except LLMServiceError as exc:
            db.rollback()
            raise RagModelError(str(exc)) from exc

        if conversation is None:
            conversation = Conversation(title=build_conversation_title(question))
            db.add(conversation)
            db.flush()

        try:
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=question,
                )
            )
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=answer,
                )
            )
            conversation.updated_at = utc_now()
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RagDatabaseError("数据库保存 RAG 对话失败。") from exc

        return RagChatResponse(
            conversation_id=conversation.id,
            answer=answer,
            sources=self._build_sources(search_results),
        )

    def stream_chat(self, request: RagChatRequest) -> Generator[str, None, None]:
        """流式 RAG：先返回 metadata/sources，再逐步返回回答 chunk。"""
        db = SessionLocal()
        full_answer = ""
        conversation: Conversation | None = None

        try:
            question = request.question.strip()
            if not question:
                yield self._ndjson_error("问题不能为空。")
                return

            document_ids = self._resolve_document_ids(db, request)
            conversation = self._get_conversation(db, request.conversation_id)
            if conversation is None:
                conversation = Conversation(title=build_conversation_title(question))
                db.add(conversation)
                db.flush()

            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=question,
                )
            )
            conversation.updated_at = utc_now()
            db.commit()

            search_results = self._search_sources(question, document_ids)
            sources = self._build_sources(search_results)
            yield self._ndjson(
                {
                    "type": "metadata",
                    "conversation_id": conversation.id,
                    "sources": [source.model_dump() for source in sources],
                }
            )

            rag_prompt = build_rag_prompt(
                question,
                self._format_source_contents(search_results),
            )
            messages = build_messages(rag_prompt)

            try:
                for chunk in llm_service.chat_completion_stream(messages):
                    full_answer += chunk
                    yield self._ndjson({"type": "chunk", "content": chunk})
            except LLMServiceError as exc:
                yield self._ndjson_error(str(exc))
                return

            if full_answer.strip():
                self._save_stream_assistant_message(db, conversation.id, full_answer)

            yield self._ndjson({"type": "done"})
        except (RagValidationError, DocumentNotFoundError, ConversationNotFoundError) as exc:
            db.rollback()
            yield self._ndjson_error(str(exc))
        except (RagEmbeddingError, RagVectorStoreError, RagDatabaseError) as exc:
            db.rollback()
            yield self._ndjson_error(str(exc))
        except SQLAlchemyError:
            db.rollback()
            yield self._ndjson_error("数据库保存 RAG 流式对话失败。")
        finally:
            db.close()

    def _ensure_document_exists(self, db: Session, document_id: int) -> None:
        document = db.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError("document_id 不存在。")

    def _resolve_document_ids(
        self,
        db: Session,
        request: RagChatRequest,
    ) -> list[int] | None:
        if request.document_ids is not None:
            document_ids = sorted({int(document_id) for document_id in request.document_ids})
        elif request.document_id is not None:
            document_ids = [request.document_id]
        else:
            document_ids = []

        if not document_ids:
            if db.query(Document.id).count() == 0:
                raise DocumentNotFoundError("当前还没有上传任何文档。")
            return None

        existing_ids = {
            document_id
            for (document_id,) in db.query(Document.id)
            .filter(Document.id.in_(document_ids))
            .all()
        }
        missing_ids = [document_id for document_id in document_ids if document_id not in existing_ids]
        if missing_ids:
            missing = ", ".join(str(document_id) for document_id in missing_ids)
            raise DocumentNotFoundError(f"document_ids 不存在：{missing}")

        return document_ids

    def _search_sources(
        self,
        question: str,
        document_ids: list[int] | None,
    ):
        try:
            question_embedding = embedding_service.get_embedding(question)
        except EmbeddingServiceError as exc:
            raise RagEmbeddingError(str(exc)) from exc

        top_k = SINGLE_DOCUMENT_TOP_K if document_ids and len(document_ids) == 1 else MULTI_DOCUMENT_TOP_K
        try:
            return chroma_service.search_chroma(
                query_embedding=question_embedding,
                document_ids=document_ids,
                top_k=top_k,
            )
        except ChromaServiceError as exc:
            raise RagVectorStoreError(str(exc)) from exc

    def _build_sources(self, search_results) -> list[RagSource]:
        return [
            RagSource(
                document_id=result.document_id,
                filename=result.filename,
                file_type=result.file_type,
                chunk_index=result.chunk_index,
                content=result.content,
                score=result.score,
            )
            for result in search_results
        ]

    def _format_source_contents(self, search_results) -> list[str]:
        return [
            (
                f"文档：{result.filename}\n"
                f"类型：{result.file_type or '未知类型'}\n"
                f"片段序号：{result.chunk_index}\n"
                f"内容：{result.content}"
            )
            for result in search_results
        ]

    def _save_stream_assistant_message(
        self,
        db: Session,
        conversation_id: int,
        answer: str,
    ) -> None:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("conversation_id 不存在。")

        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
            )
        )
        conversation.updated_at = utc_now()
        db.commit()

    def _ndjson(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False) + "\n"

    def _ndjson_error(self, message: str) -> str:
        return self._ndjson({"type": "error", "message": message})

    def _get_conversation(
        self,
        db: Session,
        conversation_id: int | None,
    ) -> Conversation | None:
        if conversation_id is None:
            return None

        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("conversation_id 不存在。")

        return conversation

    def _delete_chroma_chunks_safely(self, document_id: int) -> None:
        try:
            chroma_service.delete_document_chunks(document_id)
        except ChromaServiceError:
            return


rag_service = RagService()
