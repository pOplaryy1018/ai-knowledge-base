"""Immutable source snapshots and durable publication work."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    knowledge_base_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("knowledge_bases.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(30), default="document")
    current_revision_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", use_alter=True, name="fk_sources_current_revision", ondelete="SET NULL"))
    current_publication_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("source_publications.id", use_alter=True, name="fk_sources_current_publication", ondelete="SET NULL"))
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    last_sync_manifest: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    active_task_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceRevision(Base):
    __tablename__ = "source_revisions"
    __table_args__ = (UniqueConstraint("source_id", "raw_hash", "pipeline_version", name="uq_source_revision_content"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="RESTRICT"), index=True)
    raw_hash: Mapped[str] = mapped_column(String(128))
    pipeline_version: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20), default="staging")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_path: Mapped[str | None] = mapped_column(String(1000))
    commit: Mapped[str | None] = mapped_column(String(64))
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    filename: Mapped[str | None] = mapped_column(String(500))


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("revision_id", "logical_path", name="uq_source_document_path"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    revision_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", ondelete="RESTRICT"), index=True)
    logical_path: Mapped[str] = mapped_column(String(1000))
    text: Mapped[str] = mapped_column(Text)
    locator: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    content_hash: Mapped[str] = mapped_column(String(128))


class SourceSyncTask(Base):
    __tablename__ = "source_sync_tasks"
    __table_args__ = (Index("uq_source_active_sync", "source_id", unique=True, postgresql_where=text("status IN ('pending', 'processing')"), sqlite_where=text("status IN ('pending', 'processing')")),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="RESTRICT"), index=True)
    revision_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", ondelete="RESTRICT"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stage: Mapped[str] = mapped_column(String(30), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    active_token: Mapped[str] = mapped_column(String(100), default=lambda: str(uuid.uuid4()))


class SourceChangeEvent(Base):
    __tablename__ = "source_change_events"
    __table_args__ = (UniqueConstraint("publication_id", name="uq_source_change_publication"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="RESTRICT"), index=True)
    publication_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("source_publications.id", ondelete="RESTRICT"))
    old_revision_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", ondelete="RESTRICT"))
    new_revision_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", ondelete="RESTRICT"))
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
