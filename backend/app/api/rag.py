from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.rag_schema import (
    DocumentBatchUploadResponse,
    DocumentSummary,
    DocumentUploadResponse,
    RagChatRequest,
    RagChatResponse,
)
from app.services.rag_service import (
    ConversationNotFoundError,
    DocumentNotFoundError,
    RagDatabaseError,
    RagEmbeddingError,
    RagModelError,
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RagEmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RagVectorStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RagDatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/documents/batch", response_model=DocumentBatchUploadResponse)
async def upload_documents_batch(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> DocumentBatchUploadResponse:
    """批量上传文档；单个文件失败时只进入 failed，不影响其他文件入库。"""
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一个文档。")

    upload_payload: list[tuple[str | None, bytes]] = []
    for file in files:
        upload_payload.append((file.filename, await file.read()))

    return rag_service.create_documents_batch(db, upload_payload)


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentSummary]:
    """返回已上传文档摘要，不返回完整 content。"""
    return rag_service.list_documents(db)


@router.post("/chat", response_model=RagChatResponse)
def rag_chat(
    request: RagChatRequest,
    db: Session = Depends(get_db),
) -> RagChatResponse:
    """基于 Chroma 检索结果执行 RAG 问答。"""
    try:
        return rag_service.chat(db, request)
    except RagValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DocumentNotFoundError, ConversationNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RagEmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RagVectorStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RagModelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RagDatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/chat/stream")
def rag_chat_stream(request: RagChatRequest) -> StreamingResponse:
    """基于 Chroma 检索结果执行流式 RAG 问答，返回 NDJSON。"""
    return StreamingResponse(
        rag_service.stream_chat(request),
        media_type="application/x-ndjson; charset=utf-8",
    )
