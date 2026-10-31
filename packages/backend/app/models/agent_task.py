"""Durable Agent task identity and the source snapshot captured at creation."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_key", name="uq_agent_task_owner_request"),
        CheckConstraint("status IN ('queued', 'running', 'waiting_confirmation', 'completed', 'failed', "
                        "'cancelled', 'limit_reached')", name="ck_agent_task_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    request_key: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    source_versions: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(30), default="queued", server_default="queued")
