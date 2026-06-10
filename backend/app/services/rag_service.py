import json
import logging
import re
import time
from pathlib import Path
from collections.abc import Generator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.prompt import (
    CONTEXT_INSUFFICIENT_WARNING,
    CONTEXT_SOURCE_TEMPLATE,
    DOCUMENT_SUMMARY_CONTEXT_TEMPLATE,
    MULTI_DOC_PAPER_ANALYSIS_PROMPT_TEMPLATE,
    RAG_QA_PROMPT_TEMPLATE,
    build_messages,
    build_rag_prompt,
)
from app.db.database import Conversation, Document, Message, SessionLocal, utc_now
from app.schemas.rag_schema import (
    DocumentBatchUploadResponse,
    DocumentDeleteResponse,
    DocumentSummaryRegenerateResponse,
    DocumentUploadFailure,
    DocumentSummary,
    DocumentUploadResponse,
    DocumentReindexResponse,
    KnowledgeBaseClearResponse,
    RagChatRequest,
    RagChatResponse,
    RagSource,
)
from app.services.chat_service import build_conversation_title, chat_service
from app.services.chroma_service import ChromaServiceError, chroma_service
from app.services.document_parser import (
    DocumentParseError,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    extract_text_from_upload,
    get_file_type_from_filename,
)
from app.services.embedding_service import EmbeddingServiceError, embedding_service
from app.services.llm_service import LLMServiceError, llm_service
from app.services.rerank_service import rerank_sources
from app.services.summary_service import SummaryServiceError, generate_document_summary


logger = logging.getLogger(__name__)

ALLOWED_DOCUMENT_EXTENSIONS = SUPPORTED_DOCUMENT_EXTENSIONS
MAX_CHUNK_CHARS = 800
MIN_CHUNK_CHARS = 20
# 限制单次上传的 chunk 数，避免误传超大文件造成 embedding 费用和耗时失控。
MAX_DOCUMENT_CHUNKS = 100
SINGLE_DOCUMENT_TOP_K = 5
MULTI_DOCUMENT_TOP_K = 10
RAG_HISTORY_MESSAGE_LIMIT = 4
# cosine 相似度换算后的低分阈值；低于该值时只提示模型谨慎，不改变检索结果。
LOW_SOURCE_SCORE_THRESHOLD = 0.35
DOCUMENT_STATUS_READY = "ready"
DOCUMENT_STATUS_REINDEXING = "reindexing"
DOCUMENT_STATUS_FAILED = "failed"
SUMMARY_STATUS_PENDING = "pending"
SUMMARY_STATUS_READY = "ready"
SUMMARY_STATUS_FAILED = "failed"
SUMMARY_PREVIEW_CHARS = 100
REINDEX_MISSING_CONTENT_MESSAGE = "该文档缺少原始内容，无法重建索引，请重新上传。"
SUMMARY_MISSING_CONTENT_MESSAGE = "该文档缺少原始文本，无法重新生成摘要，请重新上传。"
PAPER_ANALYSIS_KEYWORDS = (
    "论文",
    "课题",
    "适合",
    "创新点",
    "借鉴",
    "启发",
    "对比",
    "方法",
    "AS-OCT",
    "少样本",
    "分割",
    "关键点",
)


def is_paper_analysis_question(question: str) -> bool:
    """识别是否需要使用多文档论文分析 Prompt。"""
    normalized_question = question.strip().lower()
    return any(keyword.lower() in normalized_question for keyword in PAPER_ANALYSIS_KEYWORDS)


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


class RagSummaryError(RuntimeError):
    """生成或重新生成文档摘要失败。"""


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

        # SQLite 保存 document 元信息和解析后的完整纯文本 content；Chroma 保存可检索 chunks。
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
                # 保存解析文本后，后续调整 chunk 策略或 embedding 模型时可以直接重建索引。
                content=content,
                status=DOCUMENT_STATUS_READY,
                summary_status=SUMMARY_STATUS_PENDING,
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
            self._populate_document_summary_safely(document, content)
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
            summary_status=document.summary_status or SUMMARY_STATUS_PENDING,
            summary_preview=self._build_summary_preview(document.summary),
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
                # 兜底捕获单文件异常，保证批量上传可以部分成功、部分失败。
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
                status=document.status or DOCUMENT_STATUS_READY,
                summary_status=document.summary_status or SUMMARY_STATUS_PENDING,
                summary_preview=self._build_summary_preview(document.summary),
                created_at=document.created_at,
            )
            for document in documents
        ]

    def delete_document(self, db: Session, document_id: int) -> DocumentDeleteResponse:
        document = db.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError("document_id 不存在。")

        try:
            # 先删 Chroma，再删 SQLite；如果向量删除失败，保留 SQLite 元信息方便继续排查和重试。
            chroma_service.delete_document_chunks(document_id)
        except ChromaServiceError as exc:
            raise RagVectorStoreError(str(exc)) from exc

        try:
            db.delete(document)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RagDatabaseError("数据库删除文档元信息失败。") from exc

        return DocumentDeleteResponse(
            document_id=document_id,
            deleted=True,
            message="文档已删除，对应向量索引也已清理",
        )

    def clear_knowledge_base(self, db: Session) -> KnowledgeBaseClearResponse:
        deleted_documents = db.query(Document).count()

        try:
            # 先清空 Chroma，成功后再删 SQLite；失败时保留元信息，避免“列表为空但向量还在”。
            chroma_service.clear_collection()
        except ChromaServiceError as exc:
            raise RagVectorStoreError(str(exc)) from exc

        try:
            # 不删除 conversation/message；清空知识库只是重置 RAG 资料，不影响聊天历史。
            for document in db.query(Document).all():
                db.delete(document)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RagDatabaseError("数据库清空文档元信息失败。") from exc

        return KnowledgeBaseClearResponse(
            deleted_documents=deleted_documents,
            cleared_vector_store=True,
            message="知识库已清空",
        )

    def reindex_document(self, db: Session, document_id: int) -> DocumentReindexResponse:
        document = db.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError("document_id 不存在。")

        # 旧版本上传的文档可能没有保存 content，这类文档无法无损重建索引。
        content = (document.content or "").strip()
        if not content:
            raise RagValidationError(REINDEX_MISSING_CONTENT_MESSAGE)

        # 重建索引复用当前切分策略，因此调整 MAX_CHUNK_CHARS 后无需改重建流程。
        chunks = split_text_into_chunks(content)
        if not chunks:
            raise RagValidationError("文档没有可保存的文本片段。")
        if len(chunks) > MAX_DOCUMENT_CHUNKS:
            raise RagValidationError(
                f"当前最多支持一次保存 {MAX_DOCUMENT_CHUNKS} 个 chunk，请拆分文档后重新上传。"
            )

        try:
            # 先落库 reindexing 状态，让前端刷新列表时能看到正在维护索引。
            document.status = DOCUMENT_STATUS_REINDEXING
            document.updated_at = utc_now()
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RagDatabaseError("数据库更新文档重建状态失败。") from exc

        try:
            # 先生成新 embedding；只有 embedding 成功后才删除旧向量，降低失败时的破坏面。
            embeddings = embedding_service.get_embeddings(chunks)
        except EmbeddingServiceError as exc:
            self._mark_document_status_safely(db, document, DOCUMENT_STATUS_FAILED)
            raise RagEmbeddingError(str(exc)) from exc

        try:
            # 显式删除旧 chunks，再写入当前 chunk/metadata/embedding 版本。
            chroma_service.delete_document_chunks(document.id)
            chroma_service.add_chunks_to_chroma(
                document_id=document.id,
                filename=document.filename,
                file_type=document.file_type,
                chunks=chunks,
                embeddings=embeddings,
                replace_existing=False,
            )
        except ChromaServiceError as exc:
            self._mark_document_status_safely(db, document, DOCUMENT_STATUS_FAILED)
            raise RagVectorStoreError(str(exc)) from exc

        try:
            # 只有 Chroma 写入成功后才把 SQLite 标记为 ready，避免元信息显示可用但向量不存在。
            document.chunk_count = len(chunks)
            document.chroma_collection = settings.chroma_collection_name
            document.status = DOCUMENT_STATUS_READY
            document.updated_at = utc_now()
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RagDatabaseError("数据库更新文档索引信息失败。") from exc

        return DocumentReindexResponse(
            document_id=document.id,
            filename=document.filename,
            chunk_count=document.chunk_count,
            status=document.status,
            message="文档索引已重建",
        )

    def regenerate_document_summary(
        self,
        db: Session,
        document_id: int,
    ) -> DocumentSummaryRegenerateResponse:
        document = db.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError("document_id 不存在。")

        content = (document.content or "").strip()
        if not content:
            raise RagValidationError(SUMMARY_MISSING_CONTENT_MESSAGE)

        try:
            document.summary_status = SUMMARY_STATUS_PENDING
            document.summary_updated_at = utc_now()
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RagDatabaseError("数据库更新摘要状态失败。") from exc

        try:
            summary = generate_document_summary(document.filename, content)
        except SummaryServiceError as exc:
            self._mark_document_summary_failed_safely(db, document)
            raise RagSummaryError(str(exc)) from exc

        try:
            document.summary = summary
            document.summary_status = SUMMARY_STATUS_READY
            document.summary_updated_at = utc_now()
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise RagDatabaseError("数据库保存文档摘要失败。") from exc

        return DocumentSummaryRegenerateResponse(
            document_id=document.id,
            filename=document.filename,
            summary=document.summary,
            summary_status=document.summary_status or SUMMARY_STATUS_READY,
            summary_updated_at=document.summary_updated_at,
            message="文档摘要已重新生成",
        )

    def chat(self, db: Session, request: RagChatRequest) -> RagChatResponse:
        question = request.question.strip()
        if not question:
            raise RagValidationError("问题不能为空。")

        document_ids = self._resolve_document_ids(db, request)
        logger.info(
            "rag.chat question=%s document_ids=%s",
            self._log_question(question),
            document_ids if document_ids is not None else "ALL",
        )

        conversation = self._get_conversation(db, request.conversation_id)
        is_paper_analysis = is_paper_analysis_question(question)
        history_messages = self._get_rag_history_messages(
            db,
            conversation,
            is_paper_analysis,
        )

        search_results = self._search_sources(question, document_ids)
        logger.info(
            "rag.chat.sources question=%s sources=%s",
            self._log_question(question),
            len(search_results),
        )

        rag_prompt = self._build_rag_user_prompt(db, question, search_results)

        try:
            # 大模型只接收检索出的 top-k chunks，不接收整篇文档。
            answer = llm_service.chat(rag_prompt, history_messages)
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
                yield self._ndjson_error("问题不能为空。", ErrorCode.RAG_ERROR)
                return

            document_ids = self._resolve_document_ids(db, request)
            logger.info(
                "rag.stream question=%s document_ids=%s",
                self._log_question(question),
                document_ids if document_ids is not None else "ALL",
            )
            conversation = self._get_conversation(db, request.conversation_id)
            is_paper_analysis = is_paper_analysis_question(question)
            history_messages = self._get_rag_history_messages(
                db,
                conversation,
                is_paper_analysis,
            )
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
            logger.info(
                "rag.stream.sources question=%s sources=%s",
                self._log_question(question),
                len(search_results),
            )
            sources = self._build_sources(search_results)
            yield self._ndjson(
                {
                    "type": "metadata",
                    "conversation_id": conversation.id,
                    "sources": [source.model_dump() for source in sources],
                }
            )

            rag_prompt = self._build_rag_user_prompt(db, question, search_results)
            messages = build_messages(rag_prompt, history_messages)

            try:
                for chunk in llm_service.chat_completion_stream(messages):
                    full_answer += chunk
                    yield self._ndjson({"type": "chunk", "content": chunk})
            except LLMServiceError as exc:
                yield self._ndjson_error(str(exc), ErrorCode.LLM_ERROR)
                return

            if full_answer.strip():
                self._save_stream_assistant_message(db, conversation.id, full_answer)

            yield self._ndjson({"type": "done"})
        except (RagValidationError, DocumentNotFoundError, ConversationNotFoundError) as exc:
            db.rollback()
            code = ErrorCode.RAG_ERROR
            if isinstance(exc, DocumentNotFoundError):
                code = ErrorCode.DOCUMENT_NOT_FOUND
            elif isinstance(exc, ConversationNotFoundError):
                code = ErrorCode.CONVERSATION_NOT_FOUND
            yield self._ndjson_error(str(exc), code)
        except (RagEmbeddingError, RagVectorStoreError, RagDatabaseError) as exc:
            db.rollback()
            if isinstance(exc, RagEmbeddingError):
                code = ErrorCode.EMBEDDING_ERROR
            elif isinstance(exc, RagVectorStoreError):
                code = ErrorCode.CHROMA_ERROR
            else:
                code = ErrorCode.DATABASE_ERROR
            yield self._ndjson_error(str(exc), code)
        except SQLAlchemyError:
            db.rollback()
            yield self._ndjson_error("数据库保存 RAG 流式对话失败。", ErrorCode.DATABASE_ERROR)
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
        start_time = time.perf_counter()
        try:
            question_embedding = embedding_service.get_embedding(question)
        except EmbeddingServiceError as exc:
            raise RagEmbeddingError(str(exc)) from exc

        default_top_k = (
            SINGLE_DOCUMENT_TOP_K
            if document_ids and len(document_ids) == 1
            else MULTI_DOCUMENT_TOP_K
        )
        final_top_k = (
            max(1, settings.rerank_final_top_k)
            if settings.rerank_enabled
            else default_top_k
        )
        candidate_top_k = (
            max(final_top_k, settings.rerank_candidate_top_k)
            if settings.rerank_enabled
            else default_top_k
        )

        try:
            candidate_sources = chroma_service.search_chroma(
                query_embedding=question_embedding,
                document_ids=document_ids,
                top_k=candidate_top_k,
            )
        except ChromaServiceError as exc:
            raise RagVectorStoreError(str(exc)) from exc

        if not settings.rerank_enabled:
            logger.info(
                "Rerank disabled: sources=%s final=%s duration_ms=%.2f",
                len(candidate_sources),
                min(default_top_k, len(candidate_sources)),
                (time.perf_counter() - start_time) * 1000,
            )
            return candidate_sources[:default_top_k]

        try:
            final_sources = rerank_sources(
                question=question,
                sources=candidate_sources,
                top_k=final_top_k,
            )
        except Exception as exc:
            logger.warning("Rerank failed, fallback to Chroma order: %s", exc)
            final_sources = candidate_sources[:final_top_k]

        logger.info(
            "RAG search finished: rerank_enabled=%s candidate=%s final=%s duration_ms=%.2f",
            settings.rerank_enabled,
            len(candidate_sources),
            len(final_sources),
            (time.perf_counter() - start_time) * 1000,
        )
        return final_sources

    def _log_question(self, question: str) -> str:
        return " ".join(question.strip().split())[:120]

    def _build_sources(self, search_results) -> list[RagSource]:
        return [
            RagSource(
                document_id=result.document_id,
                filename=result.filename,
                file_type=result.file_type,
                chunk_index=result.chunk_index,
                content=result.content,
                score=result.score,
                rerank_score=getattr(result, "rerank_score", None),
                rerank_reason=getattr(result, "rerank_reason", None),
            )
            for result in search_results
        ]

    def _build_rag_user_prompt(self, db: Session, question: str, search_results) -> str:
        is_paper_analysis = is_paper_analysis_question(question)
        prompt_template = MULTI_DOC_PAPER_ANALYSIS_PROMPT_TEMPLATE if is_paper_analysis else RAG_QA_PROMPT_TEMPLATE
        return build_rag_prompt(
            question=question,
            context_sources=self._format_context_sources(search_results),
            prompt_template=prompt_template,
            context_warning=self._build_context_warning(search_results),
            document_summaries=(
                self._format_document_summaries(db, search_results)
                if is_paper_analysis
                else ""
            ),
        )

    def _get_rag_history_messages(
        self,
        db: Session,
        conversation: Conversation | None,
        is_paper_analysis: bool,
    ) -> list[dict[str, str]]:
        if conversation is None or is_paper_analysis:
            return []

        return chat_service.get_recent_messages(
            db,
            conversation.id,
            limit=RAG_HISTORY_MESSAGE_LIMIT,
        )

    def _build_context_warning(self, search_results) -> str:
        if not search_results:
            return CONTEXT_INSUFFICIENT_WARNING

        if all(result.score < LOW_SOURCE_SCORE_THRESHOLD for result in search_results):
            return CONTEXT_INSUFFICIENT_WARNING

        return ""

    def _format_context_sources(self, search_results) -> str:
        formatted_sources = [
            CONTEXT_SOURCE_TEMPLATE.format(
                source_index=index,
                filename=result.filename or "未知文档",
                document_id=result.document_id,
                file_type=result.file_type or "未知类型",
                chunk_index=result.chunk_index,
                score=f"{result.score:.4f}",
                rerank_score=(
                    f"{getattr(result, 'rerank_score', None):.4f}"
                    if getattr(result, "rerank_score", None) is not None
                    else "无"
                ),
                content=result.content,
            )
            for index, result in enumerate(search_results, start=1)
        ]
        return "\n\n".join(formatted_sources)

    def _format_document_summaries(self, db: Session, search_results) -> str:
        document_ids = sorted({result.document_id for result in search_results})
        if not document_ids:
            return ""

        documents = (
            db.query(Document)
            .filter(Document.id.in_(document_ids))
            .order_by(Document.id.asc())
            .all()
        )
        formatted_summaries = [
            DOCUMENT_SUMMARY_CONTEXT_TEMPLATE.format(
                filename=document.filename,
                document_id=document.id,
                summary=document.summary.strip(),
            )
            for document in documents
            if document.summary and document.summary.strip()
        ]
        return "\n\n".join(formatted_summaries)

    def _populate_document_summary_safely(self, document: Document, content: str) -> None:
        try:
            document.summary = generate_document_summary(document.filename, content)
            document.summary_status = SUMMARY_STATUS_READY
            document.summary_updated_at = utc_now()
        except SummaryServiceError as exc:
            logger.warning("Generate summary failed for document %s: %s", document.id, exc)
            document.summary = None
            document.summary_status = SUMMARY_STATUS_FAILED
            document.summary_updated_at = utc_now()

    def _mark_document_summary_failed_safely(
        self,
        db: Session,
        document: Document,
    ) -> None:
        try:
            document.summary_status = SUMMARY_STATUS_FAILED
            document.summary_updated_at = utc_now()
            db.commit()
        except SQLAlchemyError:
            db.rollback()

    def _build_summary_preview(self, summary: str | None) -> str | None:
        if not summary or not summary.strip():
            return None

        compact_summary = " ".join(summary.strip().split())
        return compact_summary[:SUMMARY_PREVIEW_CHARS]

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

    def _ndjson_error(self, message: str, code: str = ErrorCode.INTERNAL_ERROR) -> str:
        return self._ndjson({"type": "error", "code": code, "message": message})

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

    def _mark_document_status_safely(
        self,
        db: Session,
        document: Document,
        status: str,
    ) -> None:
        try:
            document.status = status
            document.updated_at = utc_now()
            db.commit()
        except SQLAlchemyError:
            db.rollback()

    def _delete_chroma_chunks_safely(self, document_id: int) -> None:
        try:
            chroma_service.delete_document_chunks(document_id)
        except ChromaServiceError:
            return


rag_service = RagService()
