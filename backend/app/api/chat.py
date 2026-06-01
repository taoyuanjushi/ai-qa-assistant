from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChatServiceError as exc:
        # 大模型调用或业务编排失败，对前端表现为上游服务不可用。
        raise HTTPException(status_code=502, detail=str(exc)) from exc
