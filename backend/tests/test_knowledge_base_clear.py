import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, Conversation, Document, Message, get_db
from app.main import app
from app.services import rag_service as rag_service_module
from app.services.chroma_service import ChromaServiceError
from app.services.rag_service import RagVectorStoreError, rag_service


def _create_document(db_session, filename: str) -> Document:
    document = Document(
        filename=filename,
        file_type="markdown",
        chunk_count=2,
        chroma_collection="test_collection",
        content="",
    )
    db_session.add(document)
    return document


def test_clear_knowledge_base_removes_documents_but_keeps_chat_history(db_session, monkeypatch):
    _create_document(db_session, "one.md")
    _create_document(db_session, "two.md")
    conversation = Conversation(title="history")
    db_session.add(conversation)
    db_session.flush()
    db_session.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content="hello",
        )
    )
    db_session.commit()
    clear_calls = []

    def fake_clear_collection():
        clear_calls.append(True)
        return {"cleared_vector_store": True}

    monkeypatch.setattr(
        rag_service_module.chroma_service,
        "clear_collection",
        fake_clear_collection,
    )

    response = rag_service.clear_knowledge_base(db_session)

    assert response.deleted_documents == 2
    assert response.cleared_vector_store is True
    assert response.message == "知识库已清空"
    assert clear_calls == [True]
    assert db_session.query(Document).count() == 0
    assert db_session.query(Conversation).count() == 1
    assert db_session.query(Message).count() == 1


def test_clear_knowledge_base_keeps_documents_when_chroma_clear_fails(db_session, monkeypatch):
    _create_document(db_session, "one.md")
    db_session.commit()

    def fake_clear_collection():
        raise ChromaServiceError("clear failed")

    monkeypatch.setattr(
        rag_service_module.chroma_service,
        "clear_collection",
        fake_clear_collection,
    )

    with pytest.raises(RagVectorStoreError, match="clear failed"):
        rag_service.clear_knowledge_base(db_session)

    assert db_session.query(Document).count() == 1


def test_clear_empty_knowledge_base_still_clears_chroma(db_session, monkeypatch):
    clear_calls = []

    def fake_clear_collection():
        clear_calls.append(True)
        return {"cleared_vector_store": True}

    monkeypatch.setattr(
        rag_service_module.chroma_service,
        "clear_collection",
        fake_clear_collection,
    )

    response = rag_service.clear_knowledge_base(db_session)

    assert response.deleted_documents == 0
    assert response.cleared_vector_store is True
    assert clear_calls == [True]


def test_clear_knowledge_base_api_route_uses_delete_documents(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup_db = TestingSessionLocal()
    _create_document(setup_db, "api.md")
    setup_db.commit()
    setup_db.close()

    check_db = TestingSessionLocal()
    def fake_clear_collection():
        return {"cleared_vector_store": True}

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(
        rag_service_module.chroma_service,
        "clear_collection",
        fake_clear_collection,
    )
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.delete("/api/rag/documents")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "deleted_documents": 1,
        "cleared_vector_store": True,
        "message": "知识库已清空",
    }
    assert check_db.query(Document).count() == 0
    check_db.close()
    engine.dispose()
