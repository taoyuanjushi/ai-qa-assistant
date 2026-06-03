from sqlalchemy.orm import Session

from app.db.database import Conversation, Message
from app.schemas.conversation_schema import (
    ConversationMessagesResponse,
    ConversationSummary,
    MessageItem,
)


DISPLAY_MESSAGE_ROLES = ("user", "assistant")


class ConversationNotFoundError(LookupError):
    """查询不存在的会话时抛出，路由层会转换成 404。"""


def build_fallback_title(content: str) -> str:
    """用第一条用户消息生成一个短标题。"""
    title = " ".join(content.strip().split())
    if not title:
        return "New conversation"

    return title[:20]


class ConversationService:
    """历史会话查询业务层。"""

    def list_conversations(self, db: Session) -> list[ConversationSummary]:
        """按更新时间倒序返回会话摘要，不包含消息正文列表。"""
        conversations = (
            db.query(Conversation)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .all()
        )

        return [
            ConversationSummary(
                id=conversation.id,
                title=self._get_display_title(db, conversation),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation in conversations
        ]

    def get_messages(
        self,
        db: Session,
        conversation_id: int,
    ) -> ConversationMessagesResponse:
        """按时间正序返回某个会话下的 user/assistant 消息。"""
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("conversation_id 不存在")

        messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.role.in_(DISPLAY_MESSAGE_ROLES),
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )

        return ConversationMessagesResponse(
            conversation_id=conversation_id,
            messages=[
                MessageItem(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    created_at=message.created_at,
                )
                for message in messages
            ],
        )

    def _get_display_title(self, db: Session, conversation: Conversation) -> str:
        """优先使用 conversation.title，空标题则回退到第一条用户消息。"""
        if conversation.title and conversation.title.strip():
            return conversation.title

        first_user_message = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.role == "user",
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
            .first()
        )
        if first_user_message is None:
            return "New conversation"

        return build_fallback_title(first_user_message.content)


conversation_service = ConversationService()
