from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """POST /api/chat 的请求体。"""

    message: str = Field(..., min_length=1)
    conversation_id: int | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("message 不能为空。")

        return message


class ChatResponse(BaseModel):
    """POST /api/chat 返回给前端的数据。"""

    conversation_id: int
    answer: str
