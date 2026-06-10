from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.database import SessionLocal, get_db
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.services.chat_service import (
    ChatServiceError,
    ConversationNotFoundError,
    chat_service,
)


# 这个 router 自带 /chat 前缀，main.py 再统一加 /api 前缀。
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    """FastAPI 路由层：只负责 HTTP 入参、依赖注入和错误码转换。"""
    try:
        # request 已经由 Pydantic 校验，db 由 get_db 为本次请求创建。
        return chat_service.handle_chat(db, request)
    except ConversationNotFoundError as exc:
        # 用户传入不存在的 conversation_id，语义上是客户端请求资源不存在。
        raise AppException(
            message=str(exc),
            code=ErrorCode.CONVERSATION_NOT_FOUND,
            status_code=404,
        ) from exc
    except ChatServiceError as exc:
        # 大模型调用或业务编排失败，对前端表现为上游服务不可用。
        raise AppException(
            message=str(exc),
            code=ErrorCode.LLM_ERROR,
            status_code=502,
        ) from exc


@router.post("/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """流式聊天接口：逐步返回 AI 文本，并在结束后保存完整回复。"""
    db = SessionLocal()
    try:
        conversation_id, messages = chat_service.start_stream_chat(db, request)
    except ConversationNotFoundError as exc:
        raise AppException(
            message=str(exc),
            code=ErrorCode.CONVERSATION_NOT_FOUND,
            status_code=404,
        ) from exc
    finally:
        db.close()

    return StreamingResponse(
        chat_service.stream_answer_and_save(conversation_id, messages),
        headers={"X-Conversation-Id": str(conversation_id)},
        media_type="text/plain; charset=utf-8",
    )
