from sqlalchemy.orm import Session

from app.db.database import Conversation, Message, utc_now
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.services.llm_service import LLMServiceError, llm_service


class ConversationNotFoundError(LookupError):
    """请求继续一个不存在的会话时抛出，路由层会转换成 404。"""


class ChatServiceError(RuntimeError):
    """聊天业务编排失败时抛出，路由层会转换成 502。"""


def build_conversation_title(message: str) -> str:
    """用第一条用户消息生成会话标题，避免保存过长或空白标题。"""
    # 把连续空白压缩成单个空格，避免标题中出现换行和多余空格。
    title = " ".join(message.strip().split())
    if not title:
        return "New conversation"

    # 标题只取前 50 个字符，完整消息仍然会保存到 message 表。
    return title[:50]


class ChatService:
    """聊天业务层：串联会话、消息落库和大模型调用。"""

    def handle_chat(self, db: Session, request: ChatRequest) -> ChatResponse:
        """执行一次用户提问的完整后端流程。"""
        # 新会话会在这里创建；旧会话会在这里校验是否存在。
        conversation = self._get_or_create_conversation(db, request)

        # 先把用户消息加入 Session，等 AI 回复成功后再一起提交事务。
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=request.message,
            )
        )

        try:
            # 大模型调用是本流程中最容易失败的外部依赖。
            answer = llm_service.chat(request.message)
        except LLMServiceError as exc:
            # 模型失败时撤销本次 Session 中尚未提交的用户消息和新会话。
            db.rollback()
            raise ChatServiceError(str(exc)) from exc

        # 模型成功后保存 assistant 回复，形成一问一答两条消息。
        db.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
            )
        )
        # 更新会话时间，方便后续按最近对话排序。
        conversation.updated_at = utc_now()
        # 用户消息、AI 回复和会话更新时间在同一个事务中提交。
        db.commit()

        # API 层只需要返回前端继续展示所需的会话 ID 和回答文本。
        return ChatResponse(conversation_id=conversation.id, answer=answer)

    def _get_or_create_conversation(
        self,
        db: Session,
        request: ChatRequest,
    ) -> Conversation:
        """没有 conversation_id 就新建会话，否则读取已有会话。"""
        if request.conversation_id is None:
            # 第一次提问不传 conversation_id，后端用消息内容生成新会话标题。
            conversation = Conversation(title=build_conversation_title(request.message))
            db.add(conversation)
            # flush 只把 INSERT 发送到数据库以拿到 id，不等于 commit。
            db.flush()
            return conversation

        # 继续会话时按主键读取已有 conversation。
        conversation = db.get(Conversation, request.conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("conversation_id 不存在")

        return conversation


# 复用一个无状态 service 实例，避免每个请求重复创建对象。
chat_service = ChatService()
