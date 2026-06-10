from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.database import get_db
from app.schemas.rag_schema import (
    DocumentBatchUploadResponse,
    DocumentDeleteResponse,
    DocumentReindexResponse,
    DocumentSummary,
    DocumentSummaryRegenerateResponse,
    DocumentUploadResponse,
    KnowledgeBaseClearResponse,
    RagChatRequest,
    RagChatResponse,
)
from app.services.rag_service import (
    ConversationNotFoundError,
    DocumentNotFoundError,
    RagDatabaseError,
    RagEmbeddingError,
    RagModelError,
    RagSummaryError,
    RagValidationError,
    RagVectorStoreError,
    rag_service,
)


router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    """上传 TXT/Markdown 文档，SQLite 保存元信息，Chroma 保存 chunks。"""
    try:
        content_bytes = await file.read()
        return rag_service.create_document(db, file.filename, content_bytes)
    except RagValidationError as exc:
        raise _app_exception(ErrorCode.FILE_UPLOAD_ERROR, 400, exc) from exc
    except RagEmbeddingError as exc:
        raise _app_exception(ErrorCode.EMBEDDING_ERROR, 502, exc) from exc
    except RagVectorStoreError as exc:
        raise _app_exception(ErrorCode.CHROMA_ERROR, 502, exc) from exc
    except RagDatabaseError as exc:
        raise _app_exception(ErrorCode.DATABASE_ERROR, 500, exc) from exc


@router.post("/documents/batch", response_model=DocumentBatchUploadResponse)
async def upload_documents_batch(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> DocumentBatchUploadResponse:
    """批量上传文档；单个文件失败时只进入 failed，不影响其他文件入库。"""
    if not files:
        raise AppException(
            message="请选择至少一个文档。",
            code=ErrorCode.FILE_UPLOAD_ERROR,
            status_code=400,
        )

    upload_payload: list[tuple[str | None, bytes]] = []
    for file in files:
        upload_payload.append((file.filename, await file.read()))

    return rag_service.create_documents_batch(db, upload_payload)


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentSummary]:
    """返回已上传文档摘要，不返回完整 content。"""
    # 列表只给前端展示和选择范围使用，完整 content 不返回，避免大文档撑大响应体。
    return rag_service.list_documents(db)


@router.delete("/documents", response_model=KnowledgeBaseClearResponse)
def clear_knowledge_base(db: Session = Depends(get_db)) -> KnowledgeBaseClearResponse:
    """清空知识库文档元信息和 Chroma 向量索引，不删除聊天历史。"""
    # 这个路由必须放在 /documents/{document_id} 前面，避免 "documents" 被当成 document_id。
    try:
        return rag_service.clear_knowledge_base(db)
    except RagVectorStoreError as exc:
        raise _app_exception(ErrorCode.CHROMA_ERROR, 502, exc) from exc
    except RagDatabaseError as exc:
        raise _app_exception(ErrorCode.DATABASE_ERROR, 500, exc) from exc


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentDeleteResponse:
    """删除单个文档，同时清理 SQLite 元信息和 Chroma 向量索引。"""
    try:
        return rag_service.delete_document(db, document_id)
    except DocumentNotFoundError as exc:
        raise _app_exception(ErrorCode.DOCUMENT_NOT_FOUND, 404, exc) from exc
    except RagVectorStoreError as exc:
        raise _app_exception(ErrorCode.CHROMA_ERROR, 502, exc) from exc
    except RagDatabaseError as exc:
        raise _app_exception(ErrorCode.DATABASE_ERROR, 500, exc) from exc


@router.post("/documents/{document_id}/reindex", response_model=DocumentReindexResponse)
def reindex_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentReindexResponse:
    """基于 document.content 重建单个文档的 Chroma 索引。"""
    # 重建索引属于写操作，但不会重新上传文件；原始内容来自 SQLite 的 document.content。
    try:
        return rag_service.reindex_document(db, document_id)
    except RagValidationError as exc:
        raise _app_exception(ErrorCode.VALIDATION_ERROR, 400, exc) from exc
    except DocumentNotFoundError as exc:
        raise _app_exception(ErrorCode.DOCUMENT_NOT_FOUND, 404, exc) from exc
    except RagEmbeddingError as exc:
        raise _app_exception(ErrorCode.EMBEDDING_ERROR, 502, exc) from exc
    except RagVectorStoreError as exc:
        raise _app_exception(ErrorCode.CHROMA_ERROR, 502, exc) from exc
    except RagDatabaseError as exc:
        raise _app_exception(ErrorCode.DATABASE_ERROR, 500, exc) from exc


@router.post(
    "/documents/{document_id}/summary/regenerate",
    response_model=DocumentSummaryRegenerateResponse,
)
def regenerate_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentSummaryRegenerateResponse:
    """基于 document.content 重新生成单个文档摘要。"""
    try:
        return rag_service.regenerate_document_summary(db, document_id)
    except RagValidationError as exc:
        raise _app_exception(ErrorCode.VALIDATION_ERROR, 400, exc) from exc
    except DocumentNotFoundError as exc:
        raise _app_exception(ErrorCode.DOCUMENT_NOT_FOUND, 404, exc) from exc
    except RagSummaryError as exc:
        raise _app_exception(ErrorCode.SUMMARY_ERROR, 502, exc) from exc
    except RagDatabaseError as exc:
        raise _app_exception(ErrorCode.DATABASE_ERROR, 500, exc) from exc


@router.post("/chat", response_model=RagChatResponse)
def rag_chat(
    request: RagChatRequest,
    db: Session = Depends(get_db),
) -> RagChatResponse:
    """基于 Chroma 检索结果执行 RAG 问答。"""
    try:
        return rag_service.chat(db, request)
    except RagValidationError as exc:
        raise _app_exception(ErrorCode.RAG_ERROR, 400, exc) from exc
    except (DocumentNotFoundError, ConversationNotFoundError) as exc:
        code = (
            ErrorCode.DOCUMENT_NOT_FOUND
            if isinstance(exc, DocumentNotFoundError)
            else ErrorCode.CONVERSATION_NOT_FOUND
        )
        raise _app_exception(code, 404, exc) from exc
    except RagEmbeddingError as exc:
        raise _app_exception(ErrorCode.EMBEDDING_ERROR, 502, exc) from exc
    except RagVectorStoreError as exc:
        raise _app_exception(ErrorCode.CHROMA_ERROR, 502, exc) from exc
    except RagModelError as exc:
        raise _app_exception(ErrorCode.LLM_ERROR, 502, exc) from exc
    except RagDatabaseError as exc:
        raise _app_exception(ErrorCode.DATABASE_ERROR, 500, exc) from exc


@router.post("/chat/stream")
def rag_chat_stream(request: RagChatRequest) -> StreamingResponse:
    """基于 Chroma 检索结果执行流式 RAG 问答，返回 NDJSON。"""
    # stream_chat 内部自己创建和关闭 Session，避免普通依赖在响应流结束前提前关闭。
    return StreamingResponse(
        rag_service.stream_chat(request),
        media_type="application/x-ndjson; charset=utf-8",
    )


def _app_exception(code: str, status_code: int, exc: Exception) -> AppException:
    return AppException(
        message=str(exc),
        code=code,
        status_code=status_code,
    )
