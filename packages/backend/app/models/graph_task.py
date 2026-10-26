"""Durable build state for a derived Neo4j projection."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GraphBuildTask(Base):
    __tablename__ = "graph_build_tasks"
    __table_args__ = (
        UniqueConstraint("revision_id", "extractor_version", name="uq_graph_revision_extractor"),
        Index("ix_graph_build_status_lease", "status", "lease_until"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    extractor_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    active_build_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    relation_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))


class GraphCleanup(Base):
    """Cleanup intent remains after source/user rows have been removed."""

    __tablename__ = "graph_cleanup"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False))
    status: Mapped[str] = mapped_column(String(20), default="pending")
