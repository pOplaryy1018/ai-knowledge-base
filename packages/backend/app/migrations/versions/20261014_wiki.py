"""Add private Wiki pages and immutable evidence-backed revision history."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261014_wiki"
down_revision = "20261012_comparison"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("wiki_pages",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("published_revision_id", UUID(as_uuid=False)),
        sa.Column("draft_revision_id", UUID(as_uuid=False)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "slug", name="uq_wiki_owner_slug"))
    op.create_index("ix_wiki_pages_user_id", "wiki_pages", ["user_id"])
    op.create_table("wiki_revisions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("page_id", UUID(as_uuid=False), sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_versions", JSONB(), nullable=False),
        sa.Column("citations", JSONB(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_wiki_revisions_page_id", "wiki_revisions", ["page_id"])
    for field, constraint in (("published_revision_id", "fk_wiki_published_revision"),
                              ("draft_revision_id", "fk_wiki_draft_revision")):
        op.create_foreign_key(constraint, "wiki_pages", "wiki_revisions", [field], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM wiki_pages) OR EXISTS (SELECT 1 FROM wiki_revisions) THEN
            RAISE EXCEPTION 'Wiki history must be preserved before downgrade';
        END IF;
    END $$""")
    for constraint in ("fk_wiki_draft_revision", "fk_wiki_published_revision"):
        op.drop_constraint(constraint, "wiki_pages", type_="foreignkey")
    op.drop_table("wiki_revisions")
    op.drop_table("wiki_pages")
