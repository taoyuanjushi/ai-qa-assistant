from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.rag import router as rag_router
from app.core.config import settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 SQLite 表结构。"""
    # FastAPI 启动阶段执行一次，确保 conversation/message 表存在。
    init_db()
    # yield 之后应用开始接收请求；当前项目关闭阶段没有额外清理逻辑。
    yield


# settings.app_name 来自 backend/.env 或默认值，会显示在 OpenAPI 文档里。
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# 前端 Vite 开发服务器默认在 localhost:5173，CORS 允许它访问后端 API。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id"],
)

# 最终聊天接口路径是 /api + /chat，即 POST /api/chat。
app.include_router(chat_router, prefix="/api")
app.include_router(conversation_router, prefix="/api")
app.include_router(rag_router, prefix="/api")


@app.get("/api/health")
def health_check() -> dict[str, str]:
    # 给前端或命令行提供一个轻量探活接口，不依赖大模型和数据库写入。
    return {"status": "ok"}
