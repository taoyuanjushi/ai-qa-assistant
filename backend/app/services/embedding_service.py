from typing import Any

import requests

from app.core.config import settings


MAX_EMBEDDING_BATCH_SIZE = 10


class EmbeddingServiceError(RuntimeError):
    """embedding 配置、调用或响应解析失败时抛出。"""


class EmbeddingService:
    """调用 OpenAI-compatible embeddings 接口，把文本转换成向量。"""

    def get_embedding(self, text: str) -> list[float]:
        embeddings = self.get_embeddings([text])
        return embeddings[0]

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [text.strip() for text in texts]
        if not clean_texts or any(not text for text in clean_texts):
            raise EmbeddingServiceError("生成 embedding 的文本不能为空。")

        self._validate_settings()

        embeddings: list[list[float]] = []
        for batch in self._chunk_texts(clean_texts):
            embeddings.extend(self._request_embeddings(batch))

        if len(embeddings) != len(clean_texts):
            raise EmbeddingServiceError("Embedding API 返回的向量数量和输入文本数量不一致。")

        return embeddings

    def _chunk_texts(self, texts: list[str]) -> list[list[str]]:
        """按供应商批量上限切分文本，避免一次传入超过 10 条 input。"""
        return [
            texts[index : index + MAX_EMBEDDING_BATCH_SIZE]
            for index in range(0, len(texts), MAX_EMBEDDING_BATCH_SIZE)
        ]

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """请求一批 embedding；texts 数量必须不超过 MAX_EMBEDDING_BATCH_SIZE。"""
        try:
            response = requests.post(
                self._embeddings_url(),
                headers=self._headers(),
                json={
                    "model": settings.embedding_model,
                    "input": texts,
                },
                timeout=settings.llm_timeout,
            )
        except requests.RequestException as exc:
            raise EmbeddingServiceError(f"Embedding API 请求失败：{exc}") from exc

        if not response.ok:
            raise EmbeddingServiceError(self._format_error_response(response))

        try:
            data = response.json()
        except ValueError as exc:
            raise EmbeddingServiceError("Embedding API 返回的不是有效 JSON。") from exc

        return self._extract_embeddings(data)

    def _validate_settings(self) -> None:
        missing = []
        if not settings.embedding_api_key:
            missing.append("EMBEDDING_API_KEY 或 LLM_API_KEY")
        if not settings.embedding_base_url:
            missing.append("EMBEDDING_BASE_URL 或 LLM_BASE_URL")
        if not settings.embedding_model:
            missing.append("EMBEDDING_MODEL")

        if missing:
            names = ", ".join(missing)
            raise EmbeddingServiceError(f"缺少 embedding 配置：{names}")

    def _embeddings_url(self) -> str:
        if settings.embedding_base_url.endswith("/embeddings"):
            return settings.embedding_base_url

        return f"{settings.embedding_base_url}/embeddings"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.embedding_api_key}",
            "Content-Type": "application/json",
        }

    def _format_error_response(self, response: requests.Response) -> str:
        try:
            error: Any = response.json()
        except ValueError:
            error = response.text

        return f"Embedding API 返回错误：HTTP {response.status_code}，{error}"

    def _extract_embeddings(self, data: dict[str, Any]) -> list[list[float]]:
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise EmbeddingServiceError("Embedding API 返回结果中没有 data 数组。")

        items = sorted(
            items,
            key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0,
        )
        embeddings: list[list[float]] = []

        for item in items:
            if not isinstance(item, dict):
                raise EmbeddingServiceError("Embedding API data 中存在无效条目。")

            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise EmbeddingServiceError("Embedding API 返回的 embedding 不是有效数组。")

            try:
                vector = [float(value) for value in embedding]
            except (TypeError, ValueError) as exc:
                raise EmbeddingServiceError("Embedding 向量中存在非数字值。") from exc

            embeddings.append(vector)

        return embeddings


embedding_service = EmbeddingService()
