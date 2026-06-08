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


@dataclass(frozen=True)
class Settings:
    """运行时配置快照，供 FastAPI 和 service 层读取。"""

    app_name: str = os.getenv("APP_NAME", "AI QA Assistant")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout: int = _get_int_env("LLM_TIMEOUT", 30)
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY", "")
    embedding_base_url: str = (
        os.getenv("EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL", "")
    ).rstrip("/")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "")
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    chroma_collection_name: str = os.getenv(
        "CHROMA_COLLECTION_NAME",
        "ai_qa_documents",
    )


settings = Settings()
