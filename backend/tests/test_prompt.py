from types import SimpleNamespace

from app.core.prompt import RAG_QA_PROMPT_TEMPLATE, build_rag_prompt
from app.db.database import Document
from app.services.rag_service import rag_service


def _fake_search_result(**overrides):
    values = {
        "filename": "paper-a.pdf",
        "document_id": 7,
        "file_type": "pdf",
        "chunk_index": 3,
        "score": 0.81234,
        "content": "This paper discusses prototype learning for few-shot segmentation.",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_context_source_format_contains_metadata():
    context = rag_service._format_context_sources([_fake_search_result()])

    assert "[Source 1]" in context
    assert "文档名：paper-a.pdf" in context
    assert "文档ID：7" in context
    assert "文件类型：pdf" in context
    assert "chunk_index：3" in context
    assert "score：0.8123" in context


def test_multi_doc_prompt_contains_source_metadata(db_session):
    db_session.add(
        Document(
            id=7,
            filename="paper-a.pdf",
            file_type="pdf",
            chunk_count=1,
            chroma_collection="test",
            content="content",
            summary="本文讨论 few-shot segmentation。",
            summary_status="ready",
        )
    )
    db_session.commit()

    prompt = rag_service._build_rag_user_prompt(
        db_session,
        "请对比这些论文的创新点。",
        [_fake_search_result()],
    )

    assert "一、总体结论" in prompt
    assert "【文档摘要】" in prompt
    assert "本文讨论 few-shot segmentation。" in prompt
    assert "文档名：paper-a.pdf" in prompt
    assert "chunk_index：3" in prompt
    assert "score：0.8123" in prompt


def test_rag_prompt_contains_no_context_notice():
    prompt = build_rag_prompt(
        question="资料中有没有提到 Spring Boot？",
        context_sources="",
        prompt_template=RAG_QA_PROMPT_TEMPLATE,
    )

    assert "未检索到与用户问题直接相关的资料" in prompt
    assert "资料不足" in prompt


def test_low_score_sources_add_context_warning(db_session):
    prompt = rag_service._build_rag_user_prompt(
        db_session,
        "资料中有没有提到 Spring Boot？",
        [_fake_search_result(score=0.1)],
    )

    assert "当前检索到的资料可能不足，请不要强行下结论。" in prompt
