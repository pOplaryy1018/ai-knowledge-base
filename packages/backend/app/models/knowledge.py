"""知识库与知识条目模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User

# BGE-M3 向量维度
EMBEDDING_DIM = 1024


class KnowledgeBase(Base):
    """知识库表"""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="知识库唯一标识",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="知识库名称",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="知识库描述",
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # 关联的所有者
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="knowledge_bases",
    )
    # 关联的知识条目
    items: Mapped[list["KnowledgeItem"]] = relationship(
        "KnowledgeItem",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    # 关联的文件
    files: Mapped[list["KnowledgeFile"]] = relationship(
        "KnowledgeFile",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )


class KnowledgeFile(Base):
    """文件记录表 — 记录每个上传文件的处理状态"""

    __tablename__ = "knowledge_files"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="文件唯一标识",
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属知识库 ID",
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="上传者 ID",
    )
    filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="存储文件名",
    )
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="原始文件名",
    )
    file_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="文件存储路径",
    )
    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="文件类型: pdf/docx/md/txt/code/image",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="文件大小（字节）",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="processing",
        comment="处理状态: processing/completed/failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息",
    )
    chunks_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="生成的知识片段数",
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # 关联的知识库
    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase",
        back_populates="files",
    )
    # 关联的知识条目
    items: Mapped[list["KnowledgeItem"]] = relationship(
        "KnowledgeItem",
        back_populates="file",
    )


class KnowledgeItem(Base):
    """知识条目表"""

    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="条目唯一标识",
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属知识库 ID",
    )
    file_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("knowledge_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="来源文件 ID",
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="条目标题",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="条目内容（Markdown）",
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="document",
        comment="类型：document / qa / code / other",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="available",
        comment="状态：available / unavailable",
    )
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        default=list,
        comment="标签列表",
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="file_import",
        comment="来源：file_import / feishu_import / agent_extract",
    )
    source_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="来源元数据: file_import {filename, file_type, chunk_index} / feishu_import {feishu_doc_id, doc_url, ...}",
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM),
        nullable=True,
        comment="BGE-M3 向量 (1024 维)",
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # 反向关联
    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase",
        back_populates="items",
    )
    file: Mapped["KnowledgeFile | None"] = relationship(
        "KnowledgeFile",
        back_populates="items",
    )
