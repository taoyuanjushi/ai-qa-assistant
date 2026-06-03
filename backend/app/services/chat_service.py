from collections.abc import Generator

from app.core.prompt import build_messages_from_history
from sqlalchemy.orm import Session

from app.db.database import Conversation, Message, SessionLocal, utc_now
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.services.llm_service import LLMServiceError, llm_service


RECENT_MESSAGE_LIMIT = 8
ALLOWED_HISTORY_ROLES = ("user", "assistant")


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
        # 有 conversation_id 就读取已有会话；第一次提问暂时不写库。
        conversation = self._get_conversation(db, request.conversation_id)
        # 先读历史，再手动把当前问题放在 messages 最后，避免当前问题重复出现。
        history_messages = (
            self.get_recent_messages(db, conversation.id) if conversation else []
        )

        try:
            # 大模型调用是本流程中最容易失败的外部依赖。
            answer = llm_service.chat(request.message, history_messages)
        except LLMServiceError as exc:
            # 模型失败时撤销本次 Session 中可能存在的临时状态。
            db.rollback()
            raise ChatServiceError(str(exc)) from exc

        if conversation is None:
            # 第一次提问在模型成功后创建会话，避免失败请求留下空会话。
            conversation = Conversation(title=build_conversation_title(request.message))
            db.add(conversation)
            db.flush()

        # 模型成功后保存当前用户消息。
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=request.message,
            )
        )
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

    def start_stream_chat(
        self,
        db: Session,
        request: ChatRequest,
    ) -> tuple[int, list[dict[str, str]]]:
        """为流式接口准备会话、保存当前用户消息，并返回模型 messages。"""
        conversation = self._get_conversation(db, request.conversation_id)
        if conversation is None:
            conversation = Conversation(title=build_conversation_title(request.message))
            db.add(conversation)
            db.flush()

        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=request.message,
            )
        )
        conversation.updated_at = utc_now()
        db.commit()

        history_messages = self.get_recent_messages(db, conversation.id)
        messages = build_messages_from_history(history_messages)
        return conversation.id, messages

    def stream_answer_and_save(
        self,
        conversation_id: int,
        messages: list[dict[str, str]],
    ) -> Generator[str, None, None]:
        """流式返回模型文本，结束后保存一条完整 assistant message。"""
        full_answer = ""

        try:
            for chunk in llm_service.chat_completion_stream(messages):
                full_answer += chunk
                yield chunk
        except LLMServiceError as exc:
            error_text = f"\n\n[流式输出失败：{exc}]"
            full_answer += error_text
            yield error_text
        finally:
            if full_answer.strip():
                self._save_assistant_message(conversation_id, full_answer)

    def _save_assistant_message(self, conversation_id: int, answer: str) -> None:
        """流式输出结束后保存完整 assistant 回复。"""
        db = SessionLocal()
        try:
            conversation = db.get(Conversation, conversation_id)
            if conversation is None:
                return

            db.add(
                Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=answer,
                )
            )
            conversation.updated_at = utc_now()
            db.commit()
        finally:
            db.close()

    def get_recent_messages(
        self,
        db: Session,
        conversation_id: int,
        limit: int = RECENT_MESSAGE_LIMIT,
    ) -> list[dict[str, str]]:
        """读取某个会话最近几条 user/assistant 消息，并按旧到新返回。"""
        safe_limit = min(max(limit, 1), 10)
        recent_messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.role.in_(ALLOWED_HISTORY_ROLES),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(safe_limit)
            .all()
        )

        return [
            {"role": message.role, "content": message.content}
            for message in reversed(recent_messages)
        ]

    def _get_conversation(
        self,
        db: Session,
        conversation_id: int | None,
    ) -> Conversation | None:
        """没有 conversation_id 表示新会话；有则读取已有会话。"""
        if conversation_id is None:
            return None

        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("conversation_id 不存在")

        return conversation


# 复用一个无状态 service 实例，避免每个请求重复创建对象。
chat_service = ChatService()
