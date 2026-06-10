import json
import logging
import math
import re
import time
from dataclasses import is_dataclass, replace
from typing import Any

import requests

from app.core.config import settings
from app.services.llm_service import LLMServiceError, llm_service


logger = logging.getLogger(__name__)

MAX_RERANK_CONTENT_CHARS = 500
KEYWORD_BOOST_PER_HIT = 0.04
KEYWORD_BOOST_LIMIT = 0.25


class RerankServiceError(RuntimeError):
    """专业 rerank API 调用或响应解析失败时抛出。"""


def rerank_sources(question: str, sources: list[Any], top_k: int = 5) -> list[Any]:
    """对 Chroma 粗召回 sources 重排；失败时始终回退到规则排序。"""
    if not sources:
        return []

    safe_top_k = max(1, min(int(top_k or 1), len(sources)))

    if _has_model_rerank_config():
        try:
            reranked = _model_rerank_sources(question, sources, safe_top_k)
            logger.info(
                "Model rerank succeeded: model=%s candidates=%s final=%s",
                _settings_value("rerank_model", ""),
                len(sources),
                len(reranked),
            )
            return reranked
        except Exception as exc:
            logger.warning("Model rerank failed, fallback to next rerank strategy: %s", exc)
    elif _settings_value("rerank_model", ""):
        logger.warning("Model rerank config incomplete, fallback to next rerank strategy.")

    if settings.rerank_use_llm:
        try:
            reranked = _llm_rerank_sources(question, sources, safe_top_k)
            logger.info(
                "LLM rerank succeeded: candidates=%s final=%s",
                len(sources),
                len(reranked),
            )
            return reranked
        except Exception as exc:
            logger.warning("LLM rerank failed, fallback to rule rerank: %s", exc)

    reranked = _rule_rerank_sources(question, sources, safe_top_k)
    logger.info(
        "Rule rerank finished: candidates=%s final=%s",
        len(sources),
        len(reranked),
    )
    return reranked


def _model_rerank_sources(question: str, sources: list[Any], top_k: int) -> list[Any]:
    documents = [_build_model_rerank_document(source) for source in sources]
    payload = _build_model_rerank_payload(question, documents, top_k)
    start_time = time.perf_counter()

    try:
        response = requests.post(
            _model_rerank_url(),
            headers=_model_rerank_headers(),
            json=payload,
            timeout=_settings_value("rerank_timeout", _settings_value("llm_timeout", 30)),
        )
    except requests.RequestException as exc:
        logger.exception(
            "rerank.request_failed model=%s candidates=%s duration_ms=%.2f",
            _settings_value("rerank_model", ""),
            len(sources),
            (time.perf_counter() - start_time) * 1000,
        )
        raise RerankServiceError(f"Rerank API 请求失败：{exc}") from exc

    if not response.ok:
        logger.warning(
            "rerank.response_error model=%s status=%s candidates=%s duration_ms=%.2f",
            _settings_value("rerank_model", ""),
            response.status_code,
            len(sources),
            (time.perf_counter() - start_time) * 1000,
        )
        raise RerankServiceError(_format_model_rerank_error(response))

    try:
        data = response.json()
    except ValueError as exc:
        raise RerankServiceError("Rerank API 返回的不是有效 JSON。") from exc

    ranking_items = _parse_model_ranking(data)
    if not ranking_items:
        raise RerankServiceError("Rerank API 没有返回有效排序结果。")

    ranked_sources: list[Any] = []
    seen_indexes: set[int] = set()
    for item in ranking_items:
        source_position = item["source_position"]
        if source_position < 0 or source_position >= len(sources):
            continue
        if source_position in seen_indexes:
            continue

        seen_indexes.add(source_position)
        ranked_sources.append(
            _with_rerank_fields(
                sources[source_position],
                rerank_score=item["rerank_score"],
                rerank_reason=f"专业 Rerank 模型：{_settings_value('rerank_model', '')}",
            )
        )

    if not ranked_sources:
        raise RerankServiceError("Rerank API 返回的 index 无法匹配候选 source。")

    # 少数供应商可能返回不足 top_k 条结果，剩余候选继续用规则排序补齐。
    if len(ranked_sources) < top_k:
        remaining = [
            source for index, source in enumerate(sources) if index not in seen_indexes
        ]
        ranked_sources.extend(_rule_rerank_sources(question, remaining, top_k - len(ranked_sources)))

    logger.info(
        "rerank.success model=%s candidates=%s final=%s duration_ms=%.2f",
        _settings_value("rerank_model", ""),
        len(sources),
        len(ranked_sources[:top_k]),
        (time.perf_counter() - start_time) * 1000,
    )
    return ranked_sources[:top_k]


def _llm_rerank_sources(question: str, sources: list[Any], top_k: int) -> list[Any]:
    prompt = _build_llm_rerank_prompt(question, sources, top_k)
    try:
        answer = llm_service.chat(prompt)
    except LLMServiceError:
        raise

    ranking_items = _parse_llm_ranking(answer)
    if not ranking_items:
        raise ValueError("LLM rerank 没有返回有效排序结果。")

    ranked_sources: list[Any] = []
    seen_indexes: set[int] = set()
    for item in ranking_items:
        source_index = item.get("source_index")
        if not isinstance(source_index, int):
            continue

        # Prompt 中编号从 1 开始，转换成 Python list 下标。
        source_position = source_index - 1
        if source_position < 0 or source_position >= len(sources):
            continue
        if source_position in seen_indexes:
            continue

        seen_indexes.add(source_position)
        rerank_score = _safe_float(item.get("rerank_score"), default=0.0)
        ranked_sources.append(
            _with_rerank_fields(
                sources[source_position],
                rerank_score=rerank_score,
                rerank_reason=str(item.get("reason") or "LLM rerank"),
            )
        )

    if not ranked_sources:
        raise ValueError("LLM rerank 返回的 source_index 无法匹配候选 source。")

    # LLM 可能只返回部分候选，剩余候选用规则排序补齐，避免 final_top_k 不足。
    if len(ranked_sources) < top_k:
        remaining = [
            source for index, source in enumerate(sources) if index not in seen_indexes
        ]
        ranked_sources.extend(_rule_rerank_sources(question, remaining, top_k - len(ranked_sources)))

    return ranked_sources[:top_k]


def _rule_rerank_sources(question: str, sources: list[Any], top_k: int) -> list[Any]:
    keywords = _extract_keywords(question)
    scored_sources = []
    for index, source in enumerate(sources):
        base_score = _base_relevance_score(source)
        keyword_boost = _keyword_boost(source, keywords)
        rerank_score = round(min(1.0, max(0.0, base_score + keyword_boost)), 4)
        scored_sources.append(
            (
                rerank_score,
                base_score,
                -index,
                _with_rerank_fields(
                    source,
                    rerank_score=rerank_score,
                    rerank_reason=_build_rule_reason(keyword_boost),
                ),
            )
        )

    scored_sources.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in scored_sources[:top_k]]


def _build_llm_rerank_prompt(question: str, sources: list[Any], top_k: int) -> str:
    candidates = []
    for index, source in enumerate(sources, start=1):
        content = _get_field(source, "content", "") or ""
        candidates.append(
            "\n".join(
                [
                    f"[{index}]",
                    f"文档名：{_get_field(source, 'filename', '未知文档')}",
                    f"chunk_index：{_get_field(source, 'chunk_index', '')}",
                    f"score：{_get_field(source, 'score', '')}",
                    f"内容摘要：{str(content)[:MAX_RERANK_CONTENT_CHARS]}",
                ]
            )
        )

    return f"""你是一个只负责检索结果重排的助手，不要回答用户问题。
请根据用户问题，判断候选片段和问题的相关性，并只返回 JSON 数组。

要求：
1. JSON 数组最多包含 {top_k} 个对象。
2. source_index 必须使用候选片段前面的编号。
3. rerank_score 取 0 到 1，越大表示越相关。
4. reason 用一句中文说明重排理由。
5. 不要输出 Markdown，不要输出解释文字。

用户问题：
{question}

候选片段：
{chr(10).join(candidates)}

返回 JSON 示例：
[
  {{"source_index": 1, "rerank_score": 0.92, "reason": "直接讨论用户问题中的核心概念"}}
]"""


def _has_model_rerank_config() -> bool:
    return bool(
        _settings_value("rerank_model", "")
        and _settings_value("rerank_base_url", "")
        and _settings_value("rerank_api_key", "")
    )


def _build_model_rerank_document(source: Any) -> str:
    content = str(_get_field(source, "content", "") or "")
    metadata = "\n".join(
        [
            f"文档名：{_get_field(source, 'filename', '未知文档')}",
            f"chunk_index：{_get_field(source, 'chunk_index', '')}",
        ]
    )
    return f"{metadata}\n内容：{content[:MAX_RERANK_CONTENT_CHARS]}"


def _build_model_rerank_payload(
    question: str,
    documents: list[str],
    top_k: int,
) -> dict[str, Any]:
    api_format = _resolve_model_rerank_format()
    if api_format == "dashscope":
        return {
            "model": _settings_value("rerank_model", ""),
            "input": {
                "query": question,
                "documents": documents,
            },
            "parameters": {
                "top_n": top_k,
                "return_documents": False,
            },
        }

    return {
        "model": _settings_value("rerank_model", ""),
        "query": question,
        "documents": documents,
        "top_n": top_k,
        "return_documents": False,
    }


def _resolve_model_rerank_format() -> str:
    configured_format = str(_settings_value("rerank_api_format", "auto") or "auto").lower()
    if configured_format != "auto":
        return configured_format

    base_url = str(_settings_value("rerank_base_url", "")).lower()
    if "dashscope" in base_url or "/services/rerank/" in base_url:
        return "dashscope"

    return "generic"


def _model_rerank_url() -> str:
    base_url = str(_settings_value("rerank_base_url", "")).rstrip("/")
    lower_url = base_url.lower()
    if lower_url.endswith("/rerank") or lower_url.endswith("/reranking"):
        return base_url
    if "/services/rerank/" in lower_url:
        return base_url

    return f"{base_url}/rerank"


def _model_rerank_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_settings_value('rerank_api_key', '')}",
        "Content-Type": "application/json",
    }


def _format_model_rerank_error(response: requests.Response) -> str:
    try:
        error: Any = response.json()
    except ValueError:
        error = response.text

    return f"Rerank API 返回错误：HTTP {response.status_code}，{error}"


def _parse_model_ranking(data: dict[str, Any]) -> list[dict[str, Any]]:
    results = _extract_model_results(data)
    ranking_items: list[dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        source_position = _extract_model_result_index(item)
        if source_position is None:
            continue

        rerank_score = _extract_model_result_score(item)
        ranking_items.append(
            {
                "source_position": source_position,
                "rerank_score": rerank_score,
            }
        )

    ranking_items.sort(key=lambda item: item["rerank_score"], reverse=True)
    return ranking_items


def _extract_model_results(data: dict[str, Any]) -> list[Any]:
    results = data.get("results")
    if isinstance(results, list):
        return results

    output = data.get("output")
    if isinstance(output, dict) and isinstance(output.get("results"), list):
        return output["results"]

    items = data.get("data")
    if isinstance(items, list):
        return items

    return []


def _extract_model_result_index(item: dict[str, Any]) -> int | None:
    if "source_index" in item:
        index = _safe_int(item.get("source_index"))
        return index - 1 if index is not None else None

    for field_name in ("index", "document_index"):
        if field_name in item:
            return _safe_int(item.get(field_name))

    return None


def _extract_model_result_score(item: dict[str, Any]) -> float:
    for field_name in ("relevance_score", "score", "rerank_score"):
        if field_name in item:
            score = _safe_float(item.get(field_name), default=0.0)
            return round(float(score or 0.0), 4)

    return 0.0


def _parse_llm_ranking(answer: str) -> list[dict[str, Any]]:
    text = answer.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    if not text.startswith("["):
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        text = match.group(0)

    data = json.loads(text)
    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict)]


def _extract_keywords(question: str) -> set[str]:
    text = question.lower()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9\-_/]{1,}|[\u4e00-\u9fff]{2,}", text)
        if len(token.strip()) >= 2
    }
    domain_keywords = {
        "论文",
        "课题",
        "适合",
        "创新点",
        "借鉴",
        "启发",
        "对比",
        "方法",
        "技术路线",
        "as-oct",
        "少样本",
        "分割",
        "关键点",
        "few-shot",
        "segmentation",
        "prototype",
        "boundary",
    }
    return tokens | {keyword for keyword in domain_keywords if keyword in text}


def _base_relevance_score(source: Any) -> float:
    score = _safe_float(_get_field(source, "score", None), default=None)
    if score is not None and math.isfinite(score):
        return min(1.0, max(0.0, score))

    distance = _safe_float(_get_field(source, "distance", None), default=None)
    if distance is not None and math.isfinite(distance):
        return min(1.0, max(0.0, 1 / (1 + max(distance, 0.0))))

    return 0.0


def _keyword_boost(source: Any, keywords: set[str]) -> float:
    if not keywords:
        return 0.0

    haystack = " ".join(
        [
            str(_get_field(source, "filename", "")),
            str(_get_field(source, "content", "")),
        ]
    ).lower()
    hit_count = sum(1 for keyword in keywords if keyword.lower() in haystack)
    return min(KEYWORD_BOOST_LIMIT, hit_count * KEYWORD_BOOST_PER_HIT)


def _build_rule_reason(keyword_boost: float) -> str:
    if keyword_boost > 0:
        return "规则重排：原始相似度较高，并命中问题关键词。"

    return "规则重排：按原始相似度排序。"


def _with_rerank_fields(source: Any, rerank_score: float, rerank_reason: str) -> Any:
    if is_dataclass(source):
        return replace(
            source,
            rerank_score=rerank_score,
            rerank_reason=rerank_reason,
        )

    if isinstance(source, dict):
        copied = dict(source)
        copied["rerank_score"] = rerank_score
        copied["rerank_reason"] = rerank_reason
        return copied

    try:
        setattr(source, "rerank_score", rerank_score)
        setattr(source, "rerank_reason", rerank_reason)
    except Exception:
        return source

    return source


def _get_field(source: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(field_name, default)

    return getattr(source, field_name, default)


def _safe_float(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _settings_value(name: str, default: Any) -> Any:
    return getattr(settings, name, default)
