from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/chat 的请求体。"""

    message: str = Field(..., min_length=1)
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    """POST /api/chat 返回给前端的数据。"""

    conversation_id: int
    answer: str
