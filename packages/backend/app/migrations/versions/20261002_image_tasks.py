"""Freeze image task inputs durably."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261002_image_tasks"
down_revision = "20261001_source_publications"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "source_sync_tasks",
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM source_sync_tasks WHERE payload <> '{}'::jsonb) THEN
            RAISE EXCEPTION 'Image task inputs must be safely cleaned before downgrade';
        END IF;
    END $$""")
    op.drop_column("source_sync_tasks", "payload")
