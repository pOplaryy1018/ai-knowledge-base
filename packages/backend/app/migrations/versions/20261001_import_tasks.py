"""Persist import state without modifying existing document data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261001_import_tasks"
down_revision = "205ab45231f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_files", sa.Column("active_task_id", UUID(as_uuid=False), nullable=True))
    op.create_table(
        "import_tasks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("file_id", UUID(as_uuid=False), sa.ForeignKey("knowledge_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("chunks_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_import_tasks_file_id", "import_tasks", ["file_id"])
    op.create_index("ix_import_tasks_user_id", "import_tasks", ["user_id"])
    op.execute("UPDATE knowledge_files SET status='failed', error_message='旧导入任务未持久化，请重试' WHERE status IN ('pending','processing') AND active_task_id IS NULL")


def downgrade() -> None:
    op.drop_table("import_tasks")
    op.drop_column("knowledge_files", "active_task_id")
