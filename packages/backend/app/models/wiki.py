"""Owner-scoped Wiki pages with immutable draft and publication revisions."""
import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WikiPage(Base):
    __tablename__ = "wiki_pages"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_wiki_owner_slug"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(120))
    published_revision_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey(
        "wiki_revisions.id", use_alter=True, name="fk_wiki_published_revision", ondelete="SET NULL"))
    draft_revision_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey(
        "wiki_revisions.id", use_alter=True, name="fk_wiki_draft_revision", ondelete="SET NULL"))


class WikiRevision(Base):
    __tablename__ = "wiki_revisions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    page_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("wiki_pages.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source_versions: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    citations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    kind: Mapped[str] = mapped_column(String(20), default="generated")
