from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """POST /api/rag/documents 上传成功后的响应。"""

    document_id: int
    filename: str
    file_type: str
    chunk_count: int


class DocumentUploadFailure(BaseModel):
    """批量上传中单个文件失败的信息。"""

    filename: str
    error: str


class DocumentBatchUploadResponse(BaseModel):
    """POST /api/rag/documents/batch 上传多个文件后的响应。"""

    uploaded: list[DocumentUploadResponse]
    failed: list[DocumentUploadFailure]


class DocumentSummary(BaseModel):
    """GET /api/rag/documents 的单个文档摘要。"""

    id: int
    filename: str
    file_type: str | None = None
    chunk_count: int
    created_at: datetime


class RagChatRequest(BaseModel):
    """POST /api/rag/chat 的请求体。"""

    question: str = Field(..., min_length=1)
    document_id: int | None = None
    document_ids: list[int] | None = None
    conversation_id: int | None = None


class RagSource(BaseModel):
    """RAG 回答引用到的文档片段。"""

    document_id: int
    filename: str
    file_type: str | None = None
    chunk_index: int
    content: str
    score: float


class RagChatResponse(BaseModel):
    """POST /api/rag/chat 返回给前端的数据。"""

    conversation_id: int
    answer: str
    sources: list[RagSource]
