from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


# SQLite 文件固定放在 backend/app.db，便于本地运行和排查数据。
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = BACKEND_DIR / "app.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# FastAPI 可能在不同线程中处理请求，SQLite 连接需要关闭同线程检查。
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """所有 SQLAlchemy ORM 模型的公共基类。"""

    pass


class Conversation(Base):
    """一次聊天会话，保存标题和会话更新时间。"""

    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    """单条消息，使用 role 区分用户消息和 AI 回复。"""

    __tablename__ = "message"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversation.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Document(Base):
    """上传后的文本或 Markdown 文档元信息。"""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chroma_collection: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # content 是旧版 RAG 遗留字段；新版 Chroma RAG 不再依赖它保存全文。
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    """旧版 RAG 遗留表；新版 Chroma RAG 不再使用它作为检索来源。"""

    __tablename__ = "document_chunk"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship(back_populates="chunks")


def _ensure_document_metadata_columns() -> None:
    """为已有学习用 SQLite 数据库补齐 document 元信息字段。"""
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(document)"))
        }
        if not columns:
            return

        if "file_type" not in columns:
            connection.execute(text("ALTER TABLE document ADD COLUMN file_type VARCHAR(30)"))
        if "chunk_count" not in columns:
            connection.execute(
                text("ALTER TABLE document ADD COLUMN chunk_count INTEGER DEFAULT 0")
            )
        if "chroma_collection" not in columns:
            connection.execute(
                text("ALTER TABLE document ADD COLUMN chroma_collection VARCHAR(100)")
            )


def _ensure_legacy_document_chunk_embedding_columns() -> None:
    """为旧 document_chunk 表补齐字段；新版 RAG 不再读取该表。"""
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(document_chunk)"))
        }
        if not columns:
            return

        if "embedding" not in columns:
            connection.execute(text("ALTER TABLE document_chunk ADD COLUMN embedding TEXT"))
        if "embedding_model" not in columns:
            connection.execute(
                text("ALTER TABLE document_chunk ADD COLUMN embedding_model VARCHAR(100)")
            )
        if "embedding_dim" not in columns:
            connection.execute(
                text("ALTER TABLE document_chunk ADD COLUMN embedding_dim INTEGER")
            )


def init_db() -> None:
    """根据 ORM 模型创建缺失的数据表。"""
    Base.metadata.create_all(bind=engine)
    _ensure_document_metadata_columns()
    _ensure_legacy_document_chunk_embedding_columns()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：为每个请求提供一个数据库 Session 并在结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
