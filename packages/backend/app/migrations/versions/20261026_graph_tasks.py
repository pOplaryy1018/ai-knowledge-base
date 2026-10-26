"""Add durable Neo4j projection build state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261026_graph_tasks"
down_revision = "20261014_wiki"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graph_build_tasks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=False), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision_id", UUID(as_uuid=False), sa.ForeignKey("source_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("extractor_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("active_build_id", UUID(as_uuid=False)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("relation_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("revision_id", "extractor_version", name="uq_graph_revision_extractor"),
    )
    op.create_index("ix_graph_build_tasks_source_id", "graph_build_tasks", ["source_id"])
    op.create_index("ix_graph_build_status_lease", "graph_build_tasks", ["status", "lease_until"])


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM graph_build_tasks) THEN
            RAISE EXCEPTION 'Graph build history must be preserved before downgrade';
        END IF;
    END $$""")
    op.drop_table("graph_build_tasks")
