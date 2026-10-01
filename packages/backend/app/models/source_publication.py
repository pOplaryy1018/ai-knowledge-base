"""Immutable release history independent of revision content identity."""
import uuid

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SourcePublication(Base):
    __tablename__ = "source_publications"
    __table_args__ = (UniqueConstraint("source_id", "sequence", name="uq_source_publication_sequence"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="RESTRICT"), index=True)
    revision_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", ondelete="RESTRICT"))
    previous_publication_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("source_publications.id", ondelete="RESTRICT"))
    sequence: Mapped[int] = mapped_column(Integer)
