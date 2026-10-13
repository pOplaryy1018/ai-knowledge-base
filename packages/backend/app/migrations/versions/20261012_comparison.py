"""Persist validated comparison presentations with message/answer history."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261012_comparison"
down_revision = "20261002_image_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("messages", "answer_revisions"):
        op.add_column(table, sa.Column("comparison", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM messages WHERE comparison IS NOT NULL)
           OR EXISTS (SELECT 1 FROM answer_revisions WHERE comparison IS NOT NULL) THEN
            RAISE EXCEPTION 'Comparison history must be preserved before downgrade';
        END IF;
    END $$""")
    for table in ("answer_revisions", "messages"):
        op.drop_column(table, "comparison")
