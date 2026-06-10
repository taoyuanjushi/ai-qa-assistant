import pytest

from app.db.database import Document
from app.services import rag_service as rag_service_module
from app.services.chroma_service import ChromaServiceError
from app.services.rag_service import DocumentNotFoundError, RagVectorStoreError, rag_service


def _create_document(db_session, filename: str = "paper.pdf") -> Document:
    document = Document(
        filename=filename,
        file_type="pdf",
        chunk_count=3,
        chroma_collection="test_collection",
        content="",
    )
    db_session.add(document)
    db_session.commit()
    return document


def test_delete_document_removes_sqlite_after_chroma_cleanup(db_session, monkeypatch):
    document = _create_document(db_session)
    deleted_document_ids: list[int] = []

    def fake_delete_document_chunks(document_id: int):
        deleted_document_ids.append(document_id)
        return {"document_id": document_id, "deleted": True}

    monkeypatch.setattr(
        rag_service_module.chroma_service,
        "delete_document_chunks",
        fake_delete_document_chunks,
    )

    response = rag_service.delete_document(db_session, document.id)

    assert response.document_id == document.id
    assert response.deleted is True
    assert deleted_document_ids == [document.id]
    assert db_session.get(Document, document.id) is None


def test_delete_document_keeps_sqlite_when_chroma_delete_fails(db_session, monkeypatch):
    document = _create_document(db_session)

    def fake_delete_document_chunks(document_id: int):
        raise ChromaServiceError(f"delete failed for {document_id}")

    monkeypatch.setattr(
        rag_service_module.chroma_service,
        "delete_document_chunks",
        fake_delete_document_chunks,
    )

    with pytest.raises(RagVectorStoreError, match="delete failed"):
        rag_service.delete_document(db_session, document.id)

    assert db_session.get(Document, document.id) is not None


def test_delete_document_returns_clear_error_for_missing_document(db_session):
    with pytest.raises(DocumentNotFoundError, match="document_id 不存在"):
        rag_service.delete_document(db_session, 999)
