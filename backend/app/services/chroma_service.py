from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Any

from app.core.config import BACKEND_DIR, settings

try:
    # chromadb 是本版 RAG 的向量库依赖；这里延迟到实际使用时再报缺依赖错误。
    import chromadb
except ModuleNotFoundError:  # pragma: no cover - only happens before dependency install.
    chromadb = None


DEFAULT_TOP_K = 8
DIMENSION_MISMATCH_MARKER = "expecting embedding with dimension"
logger = logging.getLogger(__name__)


class ChromaServiceError(RuntimeError):
    """Chroma 初始化、写入或检索失败时抛出。"""


@dataclass(frozen=True)
class ChromaSearchResult:
    document_id: int
    filename: str
    file_type: str | None
    chunk_index: int
    content: str
    score: float
    distance: float | None = None
    rerank_score: float | None = None
    rerank_reason: str | None = None


def _persist_path() -> Path:
    # 配置允许写相对路径；相对路径统一解释为 backend/ 下的目录。
    path = Path(settings.chroma_persist_dir)
    if path.is_absolute():
        return path

    return BACKEND_DIR / path


class ChromaService:
    """Chroma 向量库访问层，隐藏 collection 的读写细节。"""

    def __init__(self) -> None:
        self._client = None
        self._collection = None

    def get_collection(self):
        if chromadb is None:
            raise ChromaServiceError("缺少 chromadb 依赖，请先安装 backend/requirements.txt。")

        # collection 和 client 在进程内复用，避免每次请求重复初始化 Chroma。
        if self._collection is not None:
            return self._collection

        try:
            persist_path = _persist_path()
            persist_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(persist_path))
            # 使用 cosine 距离，查询结果里的 distance 后面会换算成相似度分数。
            self._collection = self._client.get_or_create_collection(
                name=settings.chroma_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except Exception as exc:  # Chroma can raise several internal exception types.
            raise ChromaServiceError(f"初始化 Chroma 失败：{exc}") from exc

    def delete_document_chunks(self, document_id: int) -> dict[str, object]:
        collection = self.get_collection()
        safe_document_id = int(document_id)
        start_time = time.perf_counter()
        try:
            # document_id 写入 metadata 时是 int，这里保持同样类型，避免 where 过滤不命中。
            collection.delete(where={"document_id": safe_document_id})
            logger.info(
                "chroma.delete_document_chunks document_id=%s duration_ms=%.2f",
                safe_document_id,
                (time.perf_counter() - start_time) * 1000,
            )
            return {
                "document_id": safe_document_id,
                "deleted": True,
                "message": "Chroma 中匹配的文档向量已清理；如果没有匹配项则无需处理。",
            }
        except Exception as exc:
            message = str(exc)
            if "does not exist" in message.lower() or "no ids" in message.lower():
                return {
                    "document_id": safe_document_id,
                    "deleted": False,
                    "message": "Chroma 中没有找到该文档的向量索引。",
                }
            raise ChromaServiceError(f"删除 Chroma 旧 chunks 失败：{exc}") from exc

    def clear_collection(self) -> dict[str, object]:
        """清空当前 RAG collection，并立即重建一个空 collection 供后续上传使用。"""
        collection = self.get_collection()
        start_time = time.perf_counter()
        try:
            deleted_records = int(collection.count())
            if self._client is None:
                raise ChromaServiceError("Chroma client 尚未初始化。")

            # 删除 collection 比逐个 id 删除更彻底，能一起清掉 documents / embeddings / metadata。
            self._client.delete_collection(name=settings.chroma_collection_name)
            self._collection = None
            # 立刻重建空 collection，避免后续上传或检索拿到已经失效的内存引用。
            self.get_collection()
            logger.info(
                "chroma.clear_collection collection=%s deleted_records=%s duration_ms=%.2f",
                settings.chroma_collection_name,
                deleted_records,
                (time.perf_counter() - start_time) * 1000,
            )
            return {
                "deleted_records": deleted_records,
                "cleared_vector_store": True,
                "message": "Chroma collection 已清空。",
            }
        except ChromaServiceError:
            raise
        except Exception as exc:
            raise ChromaServiceError(f"清空 Chroma collection 失败：{exc}") from exc

    def add_chunks_to_chroma(
        self,
        document_id: int,
        filename: str,
        file_type: str | None,
        chunks: list[str],
        embeddings: list[list[float]],
        replace_existing: bool = True,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ChromaServiceError("chunks 数量和 embeddings 数量不一致。")
        if not chunks:
            raise ChromaServiceError("没有可写入 Chroma 的 chunk。")

        collection = self.get_collection()
        if replace_existing:
            # 上传同一 document_id 的新索引时默认先清旧数据；reindex 已显式删除时会关闭它。
            self.delete_document_chunks(document_id)

        created_at = datetime.now(timezone.utc).isoformat()
        # 每个 chunk 使用稳定 id，便于覆盖同一 document_id 的旧向量数据。
        ids = [f"doc_{document_id}_chunk_{index}" for index in range(len(chunks))]
        metadatas = [
            {
                "document_id": document_id,
                "filename": filename,
                "file_type": file_type or "",
                "chunk_index": index,
                "created_at": created_at,
            }
            for index in range(len(chunks))
        ]

        try:
            start_time = time.perf_counter()
            self._add_to_collection(collection, ids, chunks, embeddings, metadatas)
            logger.info(
                "chroma.add_success collection=%s document_id=%s chunks=%s duration_ms=%.2f",
                settings.chroma_collection_name,
                document_id,
                len(chunks),
                (time.perf_counter() - start_time) * 1000,
            )
        except Exception as exc:
            if self._is_dimension_mismatch_error(exc):
                # 只有空 collection 才自动重建，避免维度不一致时误删已有知识库。
                if self._reset_empty_collection():
                    collection = self.get_collection()
                    try:
                        self._add_to_collection(collection, ids, chunks, embeddings, metadatas)
                        return
                    except Exception as retry_exc:
                        raise ChromaServiceError(
                            f"重建空 Chroma collection 后写入 chunks 仍然失败：{retry_exc}"
                        ) from retry_exc

                raise ChromaServiceError(
                    "Chroma collection 的向量维度和当前 EMBEDDING_MODEL 不一致。"
                    "请清空 backend/chroma_db 或修改 CHROMA_COLLECTION_NAME 后重新上传文档。"
                ) from exc

            raise ChromaServiceError(f"写入 Chroma chunks 失败：{exc}") from exc

    def search_chroma(
        self,
        query_embedding: list[float],
        document_ids: list[int] | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[ChromaSearchResult]:
        if not query_embedding:
            raise ChromaServiceError("query embedding 不能为空。")

        collection = self.get_collection()
        safe_top_k = max(1, min(top_k, 20))
        safe_document_ids = sorted({int(document_id) for document_id in document_ids or []})
        if not safe_document_ids:
            return self._query_collection(collection, query_embedding, None, safe_top_k)

        results: list[ChromaSearchResult] = []
        per_document_top_k = safe_top_k if len(safe_document_ids) == 1 else min(safe_top_k, 4)
        for document_id in safe_document_ids:
            results.extend(
                self._query_collection(
                    collection,
                    query_embedding,
                    {"document_id": document_id},
                    per_document_top_k,
                )
            )

        return sorted(results, key=lambda result: result.score, reverse=True)[:safe_top_k]

    def _query_collection(
        self,
        collection,
        query_embedding: list[float],
        where: dict[str, int] | None,
        top_k: int,
    ) -> list[ChromaSearchResult]:
        safe_top_k = max(1, min(top_k, 20))
        start_time = time.perf_counter()

        try:
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": safe_top_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if where is not None:
                query_kwargs["where"] = where

            result = collection.query(**query_kwargs)
        except Exception as exc:
            logger.exception(
                "chroma.query_failed collection=%s where=%s top_k=%s duration_ms=%.2f",
                settings.chroma_collection_name,
                where,
                safe_top_k,
                (time.perf_counter() - start_time) * 1000,
            )
            raise ChromaServiceError(f"Chroma 检索失败：{exc}") from exc

        parsed_results = self._parse_query_result(result)
        logger.info(
            "chroma.query_success collection=%s where=%s top_k=%s results=%s duration_ms=%.2f",
            settings.chroma_collection_name,
            where,
            safe_top_k,
            len(parsed_results),
            (time.perf_counter() - start_time) * 1000,
        )
        return parsed_results

    def _parse_query_result(self, result: dict[str, Any]) -> list[ChromaSearchResult]:
        documents = (result.get("documents") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []

        # Chroma 返回结构是按 query 分组的二维数组；当前每次只查一个 query。
        parsed_results: list[ChromaSearchResult] = []
        for content, metadata, distance in zip(documents, metadatas, distances):
            if not isinstance(metadata, dict):
                continue
            if "document_id" not in metadata or "chunk_index" not in metadata:
                continue

            try:
                numeric_distance = float(distance)
            except (TypeError, ValueError):
                numeric_distance = 1.0

            # Collection 使用 cosine distance，转换为越大越相关的相似度分数。
            score = round(1 - numeric_distance, 4)
            parsed_results.append(
                ChromaSearchResult(
                    document_id=int(metadata["document_id"]),
                    filename=str(metadata.get("filename") or ""),
                    file_type=str(metadata.get("file_type") or "") or None,
                    chunk_index=int(metadata["chunk_index"]),
                    content=str(content),
                    score=score,
                    distance=numeric_distance,
                )
            )

        return parsed_results

    def _add_to_collection(
        self,
        collection,
        ids: list[str],
        chunks: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, object]],
    ) -> None:
        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def _is_dimension_mismatch_error(self, exc: Exception) -> bool:
        return DIMENSION_MISMATCH_MARKER in str(exc).lower()

    def _reset_empty_collection(self) -> bool:
        """只有 collection 为空时才自动重建，避免误删已上传的向量数据。"""
        if self._client is None or self._collection is None:
            return False

        try:
            if self._collection.count() != 0:
                return False

            self._client.delete_collection(name=settings.chroma_collection_name)
            self._collection = None
            return True
        except Exception:
            return False


chroma_service = ChromaService()
