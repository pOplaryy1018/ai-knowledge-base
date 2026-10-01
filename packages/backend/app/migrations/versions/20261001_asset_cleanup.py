"""Keep durable asset deletion intent independent of source ownership."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261001_asset_cleanup"
down_revision = "20261001_evidence_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("asset_cleanup", sa.Column("id", UUID(as_uuid=False), primary_key=True),
                    sa.Column("file_path", sa.String(1000), nullable=False, unique=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_table("asset_cleanup")
