"""Durable import status; Redis only schedules work, it does not own state."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ImportTask(Base):
    __tablename__ = "import_tasks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    file_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("knowledge_files.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stage: Mapped[str] = mapped_column(String(30), default="pending")
    message: Mapped[str] = mapped_column(Text, default="等待处理")
    percent: Mapped[int] = mapped_column(Integer, default=0)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
