"""Agent、对话、消息模型"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

EMBEDDING_DIM = 1024


class Agent(Base):
    """专家 Agent 表 ── 绑定知识条目范围与系统提示词"""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Agent 唯一标识",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Agent 名称",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Agent 描述",
    )
    knowledge_ids: Mapped[list[str]] = mapped_column(
        ARRAY(UUID(as_uuid=False)),
        nullable=False,
        default=list,
        comment="关联的知识条目 ID 列表",
    )
    prompt_template: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="系统提示词模板，为空则自动生成",
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Conversation(Base):
    """对话会话表"""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="对话唯一标识",
    )
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联 Agent ID",
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户 ID",
    )
    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="对话标题（默认取自第一条用户消息）",
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """对话消息表"""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="消息唯一标识",
    )
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属对话 ID",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="角色: user / assistant",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息内容",
    )
    citations: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="引用来源列表 [{index, content, knowledge_title, score}]",
    )
    created_at: Mapped[datetime]

    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )
