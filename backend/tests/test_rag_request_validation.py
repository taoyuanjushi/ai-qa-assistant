import pytest
from fastapi.testclient import TestClient

from app.db.database import Conversation, Document, Message
from app.main import app
from app.schemas.rag_schema import RagChatRequest
from app.services.rag_service import DocumentNotFoundError, rag_service


def test_rag_chat_rejects_blank_question():
    with TestClient(app) as client:
        response = client.post("/api/rag/chat", json={"question": "   "})

    assert response.status_code == 422
    assert "question 不能为空" in response.text


def test_empty_document_ids_resolves_to_all_documents(db_session):
    db_session.add(
        Document(
            filename="notes.md",
            file_type="markdown",
            chunk_count=1,
            chroma_collection="test",
            content="",
        )
    )
    db_session.commit()

    request = RagChatRequest(question="总结全部文档", document_ids=[])

    assert rag_service._resolve_document_ids(db_session, request) is None


def test_empty_document_ids_without_documents_returns_clear_error(db_session):
    request = RagChatRequest(question="总结全部文档", document_ids=[])

    with pytest.raises(DocumentNotFoundError, match="当前还没有上传任何文档"):
        rag_service._resolve_document_ids(db_session, request)


def test_invalid_document_ids_return_clear_error(db_session):
    request = RagChatRequest(question="总结文档", document_ids=[999])

    with pytest.raises(DocumentNotFoundError, match="document_ids 不存在：999"):
        rag_service._resolve_document_ids(db_session, request)


def test_rag_history_keeps_recent_four_messages(db_session):
    conversation = Conversation(title="history")
    db_session.add(conversation)
    db_session.flush()
    for index in range(6):
        db_session.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=f"message {index}",
            )
        )
    db_session.commit()

    history_messages = rag_service._get_rag_history_messages(
        db_session,
        conversation,
        is_paper_analysis=False,
    )

    assert [message["content"] for message in history_messages] == [
        "message 2",
        "message 3",
        "message 4",
        "message 5",
    ]


def test_paper_analysis_does_not_include_chat_history(db_session):
    conversation = Conversation(title="paper")
    db_session.add(conversation)
    db_session.flush()
    db_session.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content="闲聊历史",
        )
    )
    db_session.commit()

    assert rag_service._get_rag_history_messages(
        db_session,
        conversation,
        is_paper_analysis=True,
    ) == []
