import json
import logging
import time
from typing import Any

import requests

from app.core.config import settings
from app.core.prompt import build_messages


logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    """大模型调用或响应解析失败时抛出。"""

    pass


class LLMService:
    def chat(
        self,
        message: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> str:
        """调用 OpenAI-compatible chat completions 接口并返回回答文本。"""
        # 配置缺失时不发起外部请求，直接返回可读错误。
        self._validate_settings()
        start_time = time.perf_counter()

        try:
            # requests.post 会同步等待模型服务响应，超时时间来自 .env。
            response = requests.post(
                self._chat_completions_url(),
                headers=self._headers(),
                json={
                    # model 指定使用哪个大模型。
                    "model": settings.llm_model,
                    # messages 包含系统提示词、最近历史消息和本次用户问题。
                    "messages": build_messages(message, history_messages),
                },
                timeout=settings.llm_timeout,
            )
        except requests.RequestException as exc:
            # 网络错误、超时、连接失败都会走到这里。
            logger.exception(
                "llm.request_failed model=%s duration_ms=%.2f",
                settings.llm_model,
                (time.perf_counter() - start_time) * 1000,
            )
            raise LLMServiceError(f"大模型 API 请求失败：{exc}") from exc

        if not response.ok:
            # 4xx/5xx 不自动抛异常，需要手动转换成业务错误。
            logger.warning(
                "llm.response_error model=%s status=%s duration_ms=%.2f",
                settings.llm_model,
                response.status_code,
                (time.perf_counter() - start_time) * 1000,
            )
            raise LLMServiceError(self._format_error_response(response))

        try:
            # OpenAI-compatible 接口正常情况下返回 JSON。
            data = response.json()
        except ValueError as exc:
            raise LLMServiceError("大模型 API 返回的不是有效 JSON。") from exc

        # 只把回答文本返回给 chat_service，隐藏模型响应的复杂结构。
        answer = self._extract_answer(data)
        logger.info(
            "llm.success model=%s duration_ms=%.2f",
            settings.llm_model,
            (time.perf_counter() - start_time) * 1000,
        )
        return answer

    def chat_completion_stream(self, messages: list[dict[str, str]]):
        """流式调用 OpenAI-compatible chat completions，逐步产出文本 chunk。"""
        self._validate_settings()
        start_time = time.perf_counter()
        chunk_count = 0

        try:
            with requests.post(
                self._chat_completions_url(),
                headers=self._headers(),
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "stream": True,
                },
                stream=True,
                timeout=settings.llm_timeout,
            ) as response:
                if not response.ok:
                    logger.warning(
                        "llm.stream_response_error model=%s status=%s duration_ms=%.2f",
                        settings.llm_model,
                        response.status_code,
                        (time.perf_counter() - start_time) * 1000,
                    )
                    raise LLMServiceError(self._format_error_response(response))

                # text/event-stream 没有 charset 时，requests 会默认按 ISO-8859-1
                # 解码，中文会变成乱码；这里保留 bytes 并手动按 UTF-8 解码。
                for raw_line in response.iter_lines(decode_unicode=False):
                    line = self._decode_stream_line(raw_line)
                    if not line:
                        continue

                    chunk = self._extract_stream_chunk(line)
                    if chunk:
                        chunk_count += 1
                        yield chunk
                logger.info(
                    "llm.stream_success model=%s chunks=%s duration_ms=%.2f",
                    settings.llm_model,
                    chunk_count,
                    (time.perf_counter() - start_time) * 1000,
                )
        except requests.RequestException as exc:
            logger.exception(
                "llm.stream_request_failed model=%s chunks=%s duration_ms=%.2f",
                settings.llm_model,
                chunk_count,
                (time.perf_counter() - start_time) * 1000,
            )
            raise LLMServiceError(f"大模型 API 流式请求失败：{exc}") from exc

    def _decode_stream_line(self, raw_line: bytes | str) -> str:
        """把模型流中的一行按 UTF-8 解码成字符串。"""
        if isinstance(raw_line, bytes):
            return raw_line.decode("utf-8", errors="replace")

        return raw_line

    def _extract_stream_chunk(self, line: str) -> str:
        """从 OpenAI-compatible SSE 行中提取增量文本。"""
        line = line.strip()
        if not line.startswith("data:"):
            return ""

        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return ""

        try:
            payload = json.loads(data)
        except ValueError:
            return ""

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""

        delta = choices[0].get("delta", {})
        if isinstance(delta, dict) and isinstance(delta.get("content"), str):
            return delta["content"]

        message = choices[0].get("message", {})
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]

        text = choices[0].get("text")
        if isinstance(text, str):
            return text

        return ""

    def _validate_settings(self) -> None:
        """在真正发请求前检查必要环境变量，失败时给出明确提示。"""
        missing = []
        if not settings.llm_api_key:
            missing.append("LLM_API_KEY")
        if not settings.llm_base_url:
            missing.append("LLM_BASE_URL")
        if not settings.llm_model:
            missing.append("LLM_MODEL")

        if missing:
            names = ", ".join(missing)
            raise LLMServiceError(f"缺少环境变量：{names}")

    def _chat_completions_url(self) -> str:
        """兼容传入 base url 或完整 /chat/completions url 两种配置。"""
        if settings.llm_base_url.endswith("/chat/completions"):
            return settings.llm_base_url

        return f"{settings.llm_base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        # Authorization 使用 Bearer Token，这是 OpenAI-compatible API 的常见格式。
        return {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    def _format_error_response(self, response: requests.Response) -> str:
        """把模型服务的非 2xx 响应整理成后端可返回的错误信息。"""
        try:
            error: Any = response.json()
        except ValueError:
            error = response.text

        return f"大模型 API 返回错误：HTTP {response.status_code}，{error}"

    def _extract_answer(self, data: dict[str, Any]) -> str:
        """兼容 chat/completions 的 message.content 和部分 text 格式。"""
        # 标准 chat completions 响应会把候选结果放在 choices 数组中。
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            # 优先读取 choices[0].message.content，这是聊天模型的主流返回格式。
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content

            # 兼容少数服务返回 choices[0].text 的格式。
            text = choices[0].get("text")
            if isinstance(text, str) and text.strip():
                return text

        raise LLMServiceError("大模型 API 返回结果中没有可用回答。")


llm_service = LLMService()
