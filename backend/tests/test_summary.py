from app.db.database import Document
from app.services import rag_service as rag_service_module
from app.services import summary_service as summary_service_module
from app.services.rag_service import (
    SUMMARY_STATUS_FAILED,
    SUMMARY_STATUS_READY,
    rag_service,
)
from app.services.summary_service import SummaryServiceError, generate_document_summary


def test_generate_document_summary_uses_llm_service(monkeypatch):
    captured_messages = []

    def fake_chat(message, history_messages=None):
        captured_messages.append(message)
        return "1. 文档主题：RAG\n2. 核心内容：检索增强生成"

    monkeypatch.setattr(summary_service_module.llm_service, "chat", fake_chat)

    summary = generate_document_summary("rag.md", "RAG means retrieval augmented generation.")

    assert "文档主题" in summary
    assert "rag.md" in captured_messages[0]


def test_upload_summary_failure_does_not_block_document_create(db_session, monkeypatch):
    def fake_get_embeddings(texts: list[str]):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def fake_add_chunks_to_chroma(**kwargs):
        return None

    def fake_generate_document_summary(filename: str, text: str):
        raise SummaryServiceError("summary failed")

    monkeypatch.setattr(rag_service_module.embedding_service, "get_embeddings", fake_get_embeddings)
    monkeypatch.setattr(rag_service_module.chroma_service, "add_chunks_to_chroma", fake_add_chunks_to_chroma)
    monkeypatch.setattr(rag_service_module, "generate_document_summary", fake_generate_document_summary)

    response = rag_service.create_document(
        db_session,
        "notes.md",
        "RAG 文档内容。\n\n第二段。".encode("utf-8"),
    )
    document = db_session.get(Document, response.document_id)

    assert response.summary_status == SUMMARY_STATUS_FAILED
    assert document is not None
    assert document.summary_status == SUMMARY_STATUS_FAILED
    assert document.chunk_count > 0


def test_regenerate_document_summary_updates_document(db_session, monkeypatch):
    document = Document(
        filename="paper.pdf",
        file_type="pdf",
        chunk_count=1,
        chroma_collection="test",
        content="paper content",
        summary_status=SUMMARY_STATUS_FAILED,
    )
    db_session.add(document)
    db_session.commit()

    monkeypatch.setattr(
        rag_service_module,
        "generate_document_summary",
        lambda filename, text: "新的文档摘要",
    )

    response = rag_service.regenerate_document_summary(db_session, document.id)
    refreshed_document = db_session.get(Document, document.id)

    assert response.summary_status == SUMMARY_STATUS_READY
    assert response.summary == "新的文档摘要"
    assert refreshed_document.summary == "新的文档摘要"
    assert refreshed_document.summary_status == SUMMARY_STATUS_READY
