import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# 后端配置统一从 backend/.env 读取，避免把 API Key 写进代码。
BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """运行时配置快照，供 FastAPI 和 service 层读取。"""

    app_env: str = os.getenv("APP_ENV", "local")
    app_name: str = os.getenv("APP_NAME", "AI QA Assistant")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout: int = _get_int_env("LLM_TIMEOUT", 30)
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY", "")
    embedding_base_url: str = (
        os.getenv("EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL", "")
    ).rstrip("/")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "")
    database_path: str = os.getenv("DATABASE_PATH", "app.db")
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    chroma_collection_name: str = os.getenv(
        "CHROMA_COLLECTION_NAME",
        "ai_qa_documents",
    )
    rerank_enabled: bool = _get_bool_env("RERANK_ENABLED", True)
    rerank_candidate_top_k: int = _get_int_env("RERANK_CANDIDATE_TOP_K", 20)
    rerank_final_top_k: int = _get_int_env("RERANK_FINAL_TOP_K", 5)
    rerank_api_key: str = (
        os.getenv("RERANK_API_KEY")
        or os.getenv("EMBEDDING_API_KEY")
        or os.getenv("LLM_API_KEY", "")
    )
    rerank_base_url: str = (
        os.getenv("RERANK_BASE_URL")
        or os.getenv("EMBEDDING_BASE_URL")
        or os.getenv("LLM_BASE_URL", "")
    ).rstrip("/")
    rerank_model: str = os.getenv("RERANK_MODEL", "")
    rerank_api_format: str = os.getenv("RERANK_API_FORMAT", "auto").strip().lower()
    rerank_timeout: int = _get_int_env("RERANK_TIMEOUT", _get_int_env("LLM_TIMEOUT", 30))
    rerank_use_llm: bool = _get_bool_env("RERANK_USE_LLM", False)
    strict_config_validation: bool = _get_bool_env("STRICT_CONFIG_VALIDATION", False)

    def startup_warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self.llm_api_key:
            warnings.append("LLM_API_KEY 未配置，普通聊天和摘要生成会失败。")
        if not self.llm_base_url:
            warnings.append("LLM_BASE_URL 未配置，普通聊天和摘要生成会失败。")
        if not self.llm_model:
            warnings.append("LLM_MODEL 未配置，普通聊天和摘要生成会失败。")
        if not self.embedding_api_key:
            warnings.append("EMBEDDING_API_KEY 或 LLM_API_KEY 未配置，RAG 上传和检索会失败。")
        if not self.embedding_base_url:
            warnings.append("EMBEDDING_BASE_URL 或 LLM_BASE_URL 未配置，RAG 上传和检索会失败。")
        if not self.embedding_model:
            warnings.append("EMBEDDING_MODEL 未配置，RAG 上传和检索会失败。")
        if self.rerank_enabled and self.rerank_model:
            if not self.rerank_api_key:
                warnings.append("RERANK_API_KEY、EMBEDDING_API_KEY 或 LLM_API_KEY 未配置，专业 Rerank 会失败。")
            if not self.rerank_base_url:
                warnings.append("RERANK_BASE_URL、EMBEDDING_BASE_URL 或 LLM_BASE_URL 未配置，专业 Rerank 会失败。")

        return warnings


settings = Settings()
