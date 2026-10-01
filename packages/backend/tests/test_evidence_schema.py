"""DDL checks complement actual PostgreSQL constraint integration tests."""

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def test_version_schema_retains_evidence_and_legacy_fields():
    from app.models import Base
    from app.models.agent import Conversation, Message
    from app.models.answer import AnswerEvidence
    from app.models.knowledge import KnowledgeItem
    from app.models.source import Source, SourceRevision

    assert KnowledgeItem.__table__.c.revision_id.nullable
    assert Conversation.__table__.c.agent_id.nullable
    assert "source_versions" in Message.__table__.c
    assert Source.__table__.c.knowledge_base_id.nullable
    assert next(iter(Source.__table__.c.knowledge_base_id.foreign_keys)).ondelete == "SET NULL"
    assert "current_revision_id" in Source.__table__.c
    assert "pipeline_version" in SourceRevision.__table__.c
    assert "quote" in AnswerEvidence.__table__.c
    for table in Base.metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_event_and_review_have_idempotency_constraints():
    from sqlalchemy import UniqueConstraint

    from app.models.answer import ImpactReview
    from app.models.source import SourceChangeEvent

    for model in (SourceChangeEvent, ImpactReview):
        assert any(isinstance(c, UniqueConstraint) for c in model.__table__.constraints)


def test_active_sync_index_and_history_delete_policy():
    from sqlalchemy.dialects.postgresql import UUID
    from sqlalchemy.schema import CreateIndex

    from app.models import Base
    from app.models.answer import AnswerEvidence
    from app.models.source import SourceSyncTask

    active_index = next(index for index in SourceSyncTask.__table__.indexes if index.name == "uq_source_active_sync")
    ddl = str(CreateIndex(active_index).compile(dialect=postgresql.dialect()))
    assert "UNIQUE" in ddl and "WHERE status IN ('pending', 'processing')" in ddl
    for field in ("source_id", "revision_id", "document_id"):
        foreign_key = next(iter(AnswerEvidence.__table__.c[field].foreign_keys))
        assert foreign_key.ondelete != "CASCADE"
    for table in Base.metadata.tables.values():
        if isinstance(table.c.id.type, UUID):
            assert table.c.id.type.as_uuid is False


def test_metadata_dependency_sort_has_no_cycle_warning():
    import warnings

    from sqlalchemy.exc import SAWarning

    from app.models import Base

    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        assert Base.metadata.sorted_tables


def test_migration_generates_explicit_postgresql_ddl():
    import importlib.util
    import io
    from pathlib import Path
    from unittest.mock import patch

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration_path = Path(__file__).parents[1] / "app/migrations/versions/20261001_evidence_lifecycle.py"
    spec = importlib.util.spec_from_file_location("evidence_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with patch.object(migration, "op", Operations(context)):
        migration.upgrade()
    ddl = output.getvalue()
    assert "DEFAULT '[]'::jsonb NOT NULL" in ddl
    assert "CREATE TABLE sources" in ddl
    assert "uq_source_active_sync" in ddl
    assert "ALTER TABLE conversations ALTER COLUMN agent_id DROP NOT NULL" in ddl
