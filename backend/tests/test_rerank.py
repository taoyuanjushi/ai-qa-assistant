from types import SimpleNamespace

from app.services import rerank_service as rerank_service_module
from app.services.rerank_service import rerank_sources


def _source(index: int, content: str, score: float):
    return SimpleNamespace(
        document_id=index,
        filename=f"paper-{index}.pdf",
        file_type="pdf",
        chunk_index=index,
        content=content,
        score=score,
        distance=1 - score,
        rerank_score=None,
        rerank_reason=None,
    )


def test_rule_rerank_boosts_keyword_matched_sources():
    sources = [
        _source(1, "This chunk discusses a general database concept.", 0.6),
        _source(2, "This paper discusses AS-OCT few-shot segmentation.", 0.55),
    ]

    reranked = rerank_sources(
        "AS-OCT few-shot segmentation 方法",
        sources,
        top_k=2,
    )

    assert reranked[0].document_id == 2
    assert reranked[0].rerank_score is not None
    assert reranked[0].rerank_score > reranked[1].rerank_score


def test_model_rerank_uses_professional_rerank_api(monkeypatch):
    sources = [
        _source(1, "This chunk discusses a general database concept.", 0.8),
        _source(2, "This paper discusses AS-OCT few-shot segmentation.", 0.5),
    ]

    monkeypatch.setattr(
        rerank_service_module,
        "settings",
        SimpleNamespace(
            rerank_model="BAAI/bge-reranker-v2-m3",
            rerank_base_url="https://api.example.com/v1",
            rerank_api_key="test-key",
            rerank_api_format="generic",
            rerank_timeout=30,
            rerank_use_llm=False,
        ),
    )

    class FakeResponse:
        ok = True
        status_code = 200

        def json(self):
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.93},
                    {"index": 0, "relevance_score": 0.12},
                ]
            }

    def fake_post(url, headers, json, timeout):
        assert url == "https://api.example.com/v1/rerank"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "BAAI/bge-reranker-v2-m3"
        assert json["query"] == "AS-OCT segmentation"
        assert json["top_n"] == 2
        assert timeout == 30
        return FakeResponse()

    monkeypatch.setattr(rerank_service_module.requests, "post", fake_post)

    reranked = rerank_sources("AS-OCT segmentation", sources, top_k=2)

    assert reranked[0].document_id == 2
    assert reranked[0].rerank_score == 0.93
    assert "专业 Rerank 模型" in reranked[0].rerank_reason


def test_llm_rerank_failure_falls_back_to_rule_rerank(monkeypatch):
    sources = [
        _source(1, "unrelated content", 0.7),
        _source(2, "prototype learning for segmentation", 0.65),
    ]

    monkeypatch.setattr(
        rerank_service_module,
        "settings",
        SimpleNamespace(rerank_use_llm=True),
    )

    def fake_chat(message, history_messages=None):
        raise RuntimeError("llm rerank failed")

    monkeypatch.setattr(rerank_service_module.llm_service, "chat", fake_chat)

    reranked = rerank_sources("prototype learning segmentation", sources, top_k=1)

    assert len(reranked) == 1
    assert reranked[0].document_id == 2
