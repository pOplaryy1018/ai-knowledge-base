"""Add immutable evidence history. Downgrade destroys all new history; back up first."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261001_evidence_lifecycle"
down_revision = "20261001_import_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sources',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('knowledge_base_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('knowledge_bases.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('current_revision_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('active_task_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_sources_knowledge_base_id', 'sources', ['knowledge_base_id'], unique=False)
    op.create_index('ix_sources_user_id', 'sources', ['user_id'], unique=False)
    op.create_table('saved_answers',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('source_ids', postgresql.JSONB(), nullable=False),
        sa.Column('accepted_revision_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('origin_message_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('origin_message_id'),
    )
    op.create_index('ix_saved_answers_user_id', 'saved_answers', ['user_id'], unique=False)
    op.create_table('source_revisions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('raw_hash', sa.String(128), nullable=False),
        sa.Column('pipeline_version', sa.String(100), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('file_path', sa.String(1000), nullable=True),
        sa.Column('filename', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('source_id', 'raw_hash', 'pipeline_version', name='uq_source_revision_content'),
    )
    op.create_index('ix_source_revisions_source_id', 'source_revisions', ['source_id'], unique=False)
    op.create_table('answer_revisions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('saved_answer_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('saved_answers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source_versions', postgresql.JSONB(), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('origin_message_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_answer_revisions_saved_answer_id', 'answer_revisions', ['saved_answer_id'], unique=False)
    op.create_table('source_change_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('old_revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_revisions.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('new_revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_revisions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('source_id', 'new_revision_id', name='uq_source_change_revision'),
    )
    op.create_index('ix_source_change_events_source_id', 'source_change_events', ['source_id'], unique=False)
    op.create_index('ix_source_change_events_state', 'source_change_events', ['state'], unique=False)
    op.create_table('source_documents',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_revisions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('logical_path', sa.String(1000), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('locator', postgresql.JSONB(), nullable=False),
        sa.Column('content_hash', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('revision_id', 'logical_path', name='uq_source_document_path'),
    )
    op.create_index('ix_source_documents_revision_id', 'source_documents', ['revision_id'], unique=False)
    op.create_table('source_sync_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_revisions.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('stage', sa.String(30), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('active_token', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_source_sync_tasks_source_id', 'source_sync_tasks', ['source_id'], unique=False)
    op.create_index('ix_source_sync_tasks_user_id', 'source_sync_tasks', ['user_id'], unique=False)
    op.create_index('uq_source_active_sync', 'source_sync_tasks', ['source_id'], unique=True, postgresql_where=sa.text("status IN ('pending', 'processing')"))
    op.create_table('answer_evidence',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('answer_revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('answer_revisions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_revisions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('quote', sa.Text(), nullable=True),
        sa.Column('locator', postgresql.JSONB(), nullable=False),
        sa.Column('citation_index', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_answer_evidence_answer_revision_id', 'answer_evidence', ['answer_revision_id'], unique=False)
    op.create_index('ix_answer_evidence_document_id', 'answer_evidence', ['document_id'], unique=False)
    op.create_index('ix_answer_evidence_revision_id', 'answer_evidence', ['revision_id'], unique=False)
    op.create_index('ix_answer_evidence_source_id', 'answer_evidence', ['source_id'], unique=False)
    op.create_table('impact_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column('event_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_change_events.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('saved_answer_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('saved_answers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('answer_revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('answer_revisions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('evidence_results', postgresql.JSONB(), nullable=False),
        sa.Column('decision', sa.String(20), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('event_id', 'saved_answer_id', 'answer_revision_id', name='uq_impact_review_target'),
    )
    op.create_index('ix_impact_reviews_event_id', 'impact_reviews', ['event_id'], unique=False)
    op.create_index('ix_impact_reviews_saved_answer_id', 'impact_reviews', ['saved_answer_id'], unique=False)
    op.create_foreign_key('fk_sources_current_revision', 'sources', 'source_revisions', ['current_revision_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_saved_answers_accepted_revision', 'saved_answers', 'answer_revisions', ['accepted_revision_id'], ['id'], ondelete='SET NULL')
    op.add_column('knowledge_items', sa.Column('revision_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_revisions.id', ondelete='CASCADE'), nullable=True))
    op.create_index("ix_knowledge_items_revision_id", 'knowledge_items', ['revision_id'])
    op.add_column('knowledge_items', sa.Column('document_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('source_documents.id', ondelete='CASCADE'), nullable=True))
    op.create_index("ix_knowledge_items_document_id", 'knowledge_items', ['document_id'])
    op.add_column('knowledge_items', sa.Column('locator', postgresql.JSONB(), nullable=True))
    op.add_column('conversations', sa.Column('source_ids', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column('messages', sa.Column('source_versions', postgresql.JSONB(), nullable=True))
    op.add_column('messages', sa.Column('question', sa.Text(), nullable=True))
    op.add_column('messages', sa.Column('generation_complete', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.alter_column("conversations", "agent_id", existing_type=postgresql.UUID(as_uuid=False), nullable=True)


def downgrade() -> None:
    # Only run after backup: this irreversibly removes evidence and answer history.
    if op.get_bind().execute(sa.text("SELECT 1 FROM conversations WHERE agent_id IS NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade scoped conversations without an Agent; restore a backup instead")
    op.alter_column("conversations", "agent_id", existing_type=postgresql.UUID(as_uuid=False), nullable=False)
    op.drop_column('knowledge_items', 'revision_id')
    op.drop_column('knowledge_items', 'document_id')
    op.drop_column('knowledge_items', 'locator')
    op.drop_column('conversations', 'source_ids')
    op.drop_column('messages', 'source_versions')
    op.drop_column('messages', 'question')
    op.drop_column('messages', 'generation_complete')
    op.drop_constraint('fk_sources_current_revision', 'sources', type_="foreignkey")
    op.drop_constraint('fk_saved_answers_accepted_revision', 'saved_answers', type_="foreignkey")
    op.drop_table('impact_reviews')
    op.drop_table('answer_evidence')
    op.drop_table('source_sync_tasks')
    op.drop_table('source_documents')
    op.drop_table('source_change_events')
    op.drop_table('answer_revisions')
    op.drop_table('source_revisions')
    op.drop_table('saved_answers')
    op.drop_table('sources')
