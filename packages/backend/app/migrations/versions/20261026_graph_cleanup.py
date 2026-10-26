"""Retain graph cleanup intent when source and user rows are removed."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261026_graph_cleanup"
down_revision = "20261026_graph_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("graph_build_tasks_source_id_fkey", "graph_build_tasks", type_="foreignkey")
    op.drop_constraint("graph_build_tasks_revision_id_fkey", "graph_build_tasks", type_="foreignkey")
    op.drop_constraint("graph_build_tasks_user_id_fkey", "graph_build_tasks", type_="foreignkey")
    for field, target in (("source_id", "sources"), ("revision_id", "source_revisions"), ("user_id", "users")):
        op.create_foreign_key(f"graph_build_tasks_{field}_fkey", "graph_build_tasks", target,
                              [field], ["id"], ondelete="CASCADE")
    op.create_table("graph_cleanup",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=False), nullable=False, unique=True),
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM graph_cleanup) THEN
            RAISE EXCEPTION 'Graph cleanup intents must be processed before downgrade';
        END IF;
    END $$""")
    op.drop_table("graph_cleanup")
    for field in ("source_id", "revision_id", "user_id"):
        op.drop_constraint(f"graph_build_tasks_{field}_fkey", "graph_build_tasks", type_="foreignkey")
    for field, target in (("source_id", "sources"), ("revision_id", "source_revisions"), ("user_id", "users")):
        op.create_foreign_key(f"graph_build_tasks_{field}_fkey", "graph_build_tasks", target,
                              [field], ["id"], ondelete="RESTRICT")
