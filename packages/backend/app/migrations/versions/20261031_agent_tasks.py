"""Create durable Agent task identities and immutable source snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261031_agent_tasks"
down_revision = "20261026_graph_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_key", sa.String(200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("source_versions", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(30), server_default="queued", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "request_key", name="uq_agent_task_owner_request"),
        sa.CheckConstraint("status IN ('queued', 'running', 'waiting_confirmation', 'completed', 'failed', "
                           "'cancelled', 'limit_reached')", name="ck_agent_task_status"),
    )
    op.create_index("ix_agent_tasks_owner_id", "agent_tasks", ["owner_id"])


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM agent_tasks) THEN
            RAISE EXCEPTION 'Agent tasks must be retained before downgrade';
        END IF;
    END $$""")
    op.drop_index("ix_agent_tasks_owner_id", table_name="agent_tasks")
    op.drop_table("agent_tasks")
