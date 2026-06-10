from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DocumentUploadResponse(BaseModel):
    """POST /api/rag/documents 上传成功后的响应。"""

    document_id: int
    filename: str
    file_type: str
    chunk_count: int
    summary_status: str = "pending"
    summary_preview: str | None = None


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
    status: str = "ready"
    summary_status: str | None = "pending"
    summary_preview: str | None = None
    created_at: datetime


class DocumentDeleteResponse(BaseModel):
    """DELETE /api/rag/documents/{document_id} 删除成功后的响应。"""

    document_id: int
    deleted: bool
    message: str


class KnowledgeBaseClearResponse(BaseModel):
    """DELETE /api/rag/documents 清空知识库后的响应。"""

    deleted_documents: int
    cleared_vector_store: bool
    message: str


class DocumentReindexResponse(BaseModel):
    """POST /api/rag/documents/{document_id}/reindex 重建索引后的响应。"""

    document_id: int
    filename: str
    chunk_count: int
    status: str
    message: str


class DocumentSummaryRegenerateResponse(BaseModel):
    """POST /api/rag/documents/{document_id}/summary/regenerate 的响应。"""

    document_id: int
    filename: str
    summary: str | None = None
    summary_status: str
    summary_updated_at: datetime | None = None
    message: str


class RagChatRequest(BaseModel):
    """POST /api/rag/chat 的请求体。"""

    question: str = Field(..., min_length=1)
    document_id: int | None = None
    document_ids: list[int] | None = None
    conversation_id: int | None = None

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question 不能为空。")

        return question


class RagSource(BaseModel):
    """RAG 回答引用到的文档片段。"""

    document_id: int
    filename: str
    file_type: str | None = None
    chunk_index: int
    content: str
    score: float
    rerank_score: float | None = None
    rerank_reason: str | None = None


class RagChatResponse(BaseModel):
    """POST /api/rag/chat 返回给前端的数据。"""

    conversation_id: int
    answer: str
    sources: list[RagSource]
