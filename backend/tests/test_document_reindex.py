import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, Document, get_db
from app.main import app
from app.services import rag_service as rag_service_module
from app.services.embedding_service import EmbeddingServiceError
from app.services.rag_service import (
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_READY,
    DocumentNotFoundError,
    RagEmbeddingError,
    RagValidationError,
    rag_service,
)


def _create_document(
    db_session,
    content: str = "第一段用于重建索引。\n\n第二段用于生成新的 chunk。",
    chunk_count: int = 1,
) -> Document:
    document = Document(
        filename="notes.md",
        file_type="markdown",
        chunk_count=chunk_count,
        chroma_collection="test_collection",
        content=content,
        status=DOCUMENT_STATUS_READY,
    )
    db_session.add(document)
    db_session.commit()
    return document


def test_create_document_saves_content_for_future_reindex(db_session, monkeypatch):
    added_payloads = []

    def fake_get_embeddings(texts: list[str]):
        return [[float(index), 0.0, 0.0] for index, _ in enumerate(texts)]

    def fake_add_chunks_to_chroma(**kwargs):
        added_payloads.append(kwargs)

    monkeypatch.setattr(rag_service_module.embedding_service, "get_embeddings", fake_get_embeddings)
    monkeypatch.setattr(rag_service_module.chroma_service, "add_chunks_to_chroma", fake_add_chunks_to_chroma)

    response = rag_service.create_document(
        db_session,
        "future.md",
        "这是用于重建索引的原始文本。\n\n第二段内容。".encode("utf-8"),
    )

    document = db_session.get(Document, response.document_id)
    assert document is not None
    assert document.content.startswith("这是用于重建索引")
    assert document.status == DOCUMENT_STATUS_READY
    assert added_payloads[0]["document_id"] == document.id


def test_reindex_document_rebuilds_chroma_and_updates_chunk_count(db_session, monkeypatch):
    document = _create_document(db_session)
    deleted_document_ids: list[int] = []
    added_payloads = []

    def fake_get_embeddings(texts: list[str]):
        return [[float(index), 1.0, 0.0] for index, _ in enumerate(texts)]

    def fake_delete_document_chunks(document_id: int):
        deleted_document_ids.append(document_id)
        return {"deleted": True}

    def fake_add_chunks_to_chroma(**kwargs):
        added_payloads.append(kwargs)

    monkeypatch.setattr(rag_service_module.embedding_service, "get_embeddings", fake_get_embeddings)
    monkeypatch.setattr(rag_service_module.chroma_service, "delete_document_chunks", fake_delete_document_chunks)
    monkeypatch.setattr(rag_service_module.chroma_service, "add_chunks_to_chroma", fake_add_chunks_to_chroma)

    response = rag_service.reindex_document(db_session, document.id)
    refreshed_document = db_session.get(Document, document.id)

    assert response.document_id == document.id
    assert response.message == "文档索引已重建"
    assert response.chunk_count == refreshed_document.chunk_count
    assert response.status == DOCUMENT_STATUS_READY
    assert deleted_document_ids == [document.id]
    assert added_payloads[0]["document_id"] == document.id
    assert added_payloads[0]["replace_existing"] is False
    assert refreshed_document.status == DOCUMENT_STATUS_READY


def test_reindex_document_returns_clear_error_when_content_missing(db_session):
    document = _create_document(db_session, content="", chunk_count=0)

    with pytest.raises(RagValidationError, match="该文档缺少原始内容，无法重建索引，请重新上传"):
        rag_service.reindex_document(db_session, document.id)


def test_reindex_document_marks_failed_when_embedding_fails(db_session, monkeypatch):
    document = _create_document(db_session)
    deleted_document_ids: list[int] = []

    def fake_get_embeddings(texts: list[str]):
        raise EmbeddingServiceError("embedding failed")

    def fake_delete_document_chunks(document_id: int):
        deleted_document_ids.append(document_id)

    monkeypatch.setattr(rag_service_module.embedding_service, "get_embeddings", fake_get_embeddings)
    monkeypatch.setattr(rag_service_module.chroma_service, "delete_document_chunks", fake_delete_document_chunks)

    with pytest.raises(RagEmbeddingError, match="embedding failed"):
        rag_service.reindex_document(db_session, document.id)

    refreshed_document = db_session.get(Document, document.id)
    assert refreshed_document.status == DOCUMENT_STATUS_FAILED
    assert deleted_document_ids == []


def test_reindex_document_returns_clear_error_for_missing_document(db_session):
    with pytest.raises(DocumentNotFoundError, match="document_id 不存在"):
        rag_service.reindex_document(db_session, 999)


def test_reindex_document_api_route(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup_db = TestingSessionLocal()
    document = _create_document(setup_db)
    document_id = document.id
    setup_db.close()

    def fake_get_embeddings(texts: list[str]):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def fake_delete_document_chunks(document_id: int):
        return {"deleted": True}

    def fake_add_chunks_to_chroma(**kwargs):
        return None

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(rag_service_module.embedding_service, "get_embeddings", fake_get_embeddings)
    monkeypatch.setattr(rag_service_module.chroma_service, "delete_document_chunks", fake_delete_document_chunks)
    monkeypatch.setattr(rag_service_module.chroma_service, "add_chunks_to_chroma", fake_add_chunks_to_chroma)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.post(f"/api/rag/documents/{document_id}/reindex")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["document_id"] == document_id
    assert response.json()["message"] == "文档索引已重建"
    engine.dispose()
