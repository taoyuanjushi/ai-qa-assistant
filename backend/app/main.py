from contextlib import asynccontextmanager
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.rag import router as rag_router
from app.core.error_codes import ErrorCode
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AppException
from app.core.logging_config import configure_logging
from app.db.database import init_db


configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 SQLite 表结构。"""
    for warning in settings.startup_warnings():
        if settings.strict_config_validation:
            raise AppException(
                message=warning,
                code=ErrorCode.CONFIG_ERROR,
                status_code=500,
            )
        logger.warning("config_warning %s", warning)

    # FastAPI 启动阶段执行一次，确保 conversation/message 表存在。
    init_db()
    # yield 之后应用开始接收请求；当前项目关闭阶段没有额外清理逻辑。
    yield


# settings.app_name 来自 backend/.env 或默认值，会显示在 OpenAPI 文档里。
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# 前端 Vite 开发服务器默认在 localhost:5173，CORS 允许它访问后端 API。
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id"],
)


@app.middleware("http")
async def log_requests(request, call_next):
    """Record request lifecycle without logging request bodies or secrets."""
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    logger.info(
        "request.start id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "request.error id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Request-Id"] = request_id
    logger.info(
        "request.end id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


register_exception_handlers(app)


# 最终聊天接口路径是 /api + /chat，即 POST /api/chat。
app.include_router(chat_router, prefix="/api")
app.include_router(conversation_router, prefix="/api")
app.include_router(rag_router, prefix="/api")


@app.get("/api/health")
def health_check() -> dict[str, str]:
    # 给前端或命令行提供一个轻量探活接口，不依赖大模型和数据库写入。
    return {"status": "ok"}
