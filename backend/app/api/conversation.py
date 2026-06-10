from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.database import get_db
from app.schemas.conversation_schema import (
    ConversationMessagesResponse,
    ConversationSummary,
)
from app.services.conversation_service import (
    ConversationNotFoundError,
    conversation_service,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationSummary]:
    """查询历史会话列表，只返回会话摘要。"""
    return conversation_service.list_conversations(db)


@router.get("/{conversation_id}/messages", response_model=ConversationMessagesResponse)
def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> ConversationMessagesResponse:
    """查询某个会话下的全部 user/assistant 消息。"""
    try:
        return conversation_service.get_messages(db, conversation_id)
    except ConversationNotFoundError as exc:
        raise AppException(
            message=str(exc),
            code=ErrorCode.CONVERSATION_NOT_FOUND,
            status_code=404,
        ) from exc
