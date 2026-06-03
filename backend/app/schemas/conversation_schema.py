from datetime import datetime

from pydantic import BaseModel


class ConversationSummary(BaseModel):
    """GET /api/conversations 返回的单个会话摘要。"""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageItem(BaseModel):
    """GET /api/conversations/{id}/messages 返回的单条消息。"""

    id: int
    role: str
    content: str
    created_at: datetime


class ConversationMessagesResponse(BaseModel):
    """某个会话下的全部可展示消息。"""

    conversation_id: int
    messages: list[MessageItem]
