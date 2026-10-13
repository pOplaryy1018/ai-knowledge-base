"""Saved answer history and immutable direct evidence."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SavedAnswer(Base):
    __tablename__ = "saved_answers"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    question: Mapped[str] = mapped_column(Text)
    source_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    accepted_revision_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("answer_revisions.id", use_alter=True, name="fk_saved_answers_accepted_revision", ondelete="SET NULL"))
    origin_message_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("messages.id", ondelete="SET NULL"), unique=True)


class AnswerRevision(Base):
    __tablename__ = "answer_revisions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    saved_answer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("saved_answers.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    source_versions: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    kind: Mapped[str] = mapped_column(String(20), default="original")
    comparison: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    origin_message_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("messages.id", ondelete="SET NULL"))


class AnswerEvidence(Base):
    __tablename__ = "answer_evidence"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    answer_revision_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("answer_revisions.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="RESTRICT"), index=True)
    revision_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("source_revisions.id", ondelete="SET NULL"), index=True)
    document_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("source_documents.id", ondelete="SET NULL"), index=True)
    quote: Mapped[str | None] = mapped_column(Text)
    locator: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    citation_index: Mapped[int] = mapped_column(Integer)


class ImpactReview(Base):
    __tablename__ = "impact_reviews"
    __table_args__ = (UniqueConstraint("event_id", "saved_answer_id", "answer_revision_id", name="uq_impact_review_target"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("source_change_events.id", ondelete="RESTRICT"), index=True)
    saved_answer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("saved_answers.id", ondelete="CASCADE"), index=True)
    answer_revision_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("answer_revisions.id", ondelete="CASCADE"))
    evidence_results: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    decision: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
