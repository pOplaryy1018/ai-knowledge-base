"""file_driven_knowledge — source_metadata + cascade delete + source enum cleanup

Revision ID: 205ab45231f9
Revises: 87f192e74df0
Create Date: 2026-05-24 16:28:54.003245
"""
from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '205ab45231f9'
down_revision: Union[str, Sequence[str], None] = '87f192e74df0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 新增 source_metadata 列
    op.add_column(
        'knowledge_items',
        sa.Column(
            'source_metadata',
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    # 2. 统一 source 枚举值：import → file_import，删除 manual 条目
    op.execute("UPDATE knowledge_items SET source = 'file_import' WHERE source = 'import'")
    op.execute("DELETE FROM knowledge_items WHERE source = 'manual'")

    # 3. 修改 file_id 外键：DROP + ADD（PG 不支持 ALTER CONSTRAINT ON DELETE）
    op.execute("""
        DO $$
        DECLARE
            con_name text;
        BEGIN
            SELECT conname INTO con_name FROM pg_constraint
            WHERE conrelid = 'knowledge_items'::regclass
              AND confrelid = 'knowledge_files'::regclass;
            IF con_name IS NOT NULL THEN
                EXECUTE 'ALTER TABLE knowledge_items DROP CONSTRAINT ' || con_name;
            END IF;
        END $$;
    """)
    op.create_foreign_key(
        'fk_knowledge_items_file_id',
        'knowledge_items', 'knowledge_files',
        ['file_id'], ['id'],
        ondelete='CASCADE',
    )

    # 4. 创建复合索引
    op.create_index(
        'idx_knowledge_files_kb_status',
        'knowledge_files',
        ['knowledge_base_id', 'status'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_knowledge_files_kb_status')
    op.drop_constraint('fk_knowledge_items_file_id', 'knowledge_items', type_='foreignkey')
    op.create_foreign_key(
        None, 'knowledge_items', 'knowledge_files',
        ['file_id'], ['id'],
        ondelete='SET NULL',
    )
    op.drop_column('knowledge_items', 'source_metadata')
