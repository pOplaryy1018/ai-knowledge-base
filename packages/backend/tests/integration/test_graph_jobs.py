"""Published source revisions create independent, recoverable graph work."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.graph_task import GraphBuildTask, GraphCleanup
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceRevision
from app.models.user import User
from app.services.graph_extraction import ExtractedRelation, ExtractionResult
from app.services.source_cleanup import redact_source
from app.services.source_publication import publish_revision


@pytest.mark.asyncio
async def test_publication_creates_one_graph_task(db_session, owner_kb) -> None:
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                              pipeline_version="synthetic", state="ready")
    db_session.add(revision)
    await db_session.flush()

    await publish_revision(db_session, source.id, revision.id, None)
    await publish_revision(db_session, source.id, revision.id, revision.id)
    tasks = (await db_session.execute(select(GraphBuildTask).where(GraphBuildTask.revision_id == revision.id))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].status == "pending"
    assert source.current_revision_id == revision.id


@pytest.mark.asyncio
async def test_source_redaction_leaves_graph_cleanup_intent(db_session, owner_kb) -> None:
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    await redact_source(db_session, source.id)
    cleanup = (await db_session.execute(select(GraphCleanup).where(GraphCleanup.source_id == source.id))).scalar_one()
    assert cleanup.user_id == user.id
    assert cleanup.status == "pending"


@pytest.mark.asyncio
async def test_graph_task_claim_is_single_and_leased(db_session, owner_kb) -> None:
    from app.services.graph_jobs import claim_graph_task

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                              pipeline_version="synthetic", state="ready")
    db_session.add(revision)
    await db_session.flush()
    await publish_revision(db_session, source.id, revision.id, None)
    task = (await db_session.execute(select(GraphBuildTask).where(GraphBuildTask.revision_id == revision.id))).scalar_one()

    claimed = await claim_graph_task(db_session, task.id)
    assert claimed is not None
    assert task.status == "processing"
    assert task.attempts == 1
    assert task.lease_until is not None
    assert await claim_graph_task(db_session, task.id) is None


@pytest.mark.asyncio
async def test_graph_build_switches_pointer_only_after_projection(db_session, owner_kb, monkeypatch) -> None:
    from app.services import graph_jobs

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                              pipeline_version="synthetic", state="ready")
    db_session.add(revision)
    await db_session.flush()
    item = KnowledgeItem(knowledge_base_id=kb.id, revision_id=revision.id, title="synthetic",
                         content="甲公司收购乙公司。", source="source_revision", source_metadata={"source_id": source.id})
    db_session.add(item)
    await db_session.flush()
    await publish_revision(db_session, source.id, revision.id, None)
    task = (await db_session.execute(select(GraphBuildTask).where(GraphBuildTask.revision_id == revision.id))).scalar_one()
    monkeypatch.setattr(graph_jobs, "async_session", async_sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False, join_transaction_mode="create_savepoint"))
    observed: list[str] = []

    async def fake_extract(chunks):
        assert [chunk.id for chunk in chunks] == [item.id]
        return ExtractionResult([ExtractedRelation(id="relation-1", item_id=item.id,
            subject="甲公司", subject_type="组织", predicate="收购", object="乙公司",
            object_type="组织", quote_start=0, quote_end=len(item.content))], 0)

    async def fake_schema():
        observed.append("schema")

    async def fake_write(build_id, user_id, source_id, revision_id, relations):
        observed.append("write")
        await db_session.refresh(task)
        assert task.active_build_id is None
        assert len(relations) == 1

    monkeypatch.setattr(graph_jobs, "extract_relations", fake_extract)
    monkeypatch.setattr(graph_jobs, "setup_schema", fake_schema)
    monkeypatch.setattr(graph_jobs, "write_projection", fake_write)
    assert await graph_jobs.process_graph_build({}, task.id) == {"status": "completed"}
    await db_session.refresh(task)
    assert observed == ["schema", "write"]
    assert task.status == "completed"
    assert task.active_build_id is not None
    assert task.relation_count == 1


@pytest.mark.asyncio
async def test_graph_status_and_retry_are_owner_scoped(db_session, owner_kb, monkeypatch) -> None:
    from app.api import graph_api, import_api

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                              pipeline_version="synthetic", state="ready")
    db_session.add(revision)
    await db_session.flush()
    await publish_revision(db_session, source.id, revision.id, None)
    task = (await db_session.execute(select(GraphBuildTask).where(GraphBuildTask.revision_id == revision.id))).scalar_one()
    task.status, task.error_code = "failed", "llm_unavailable"
    await db_session.flush()
    monkeypatch.setattr(graph_api, "async_session", async_sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False, join_transaction_mode="create_savepoint"))

    async def queue_unavailable():
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(import_api, "get_arq", queue_unavailable)
    assert (await graph_api.graph_status(uuid.UUID(source.id), user))["status"] == "failed"
    other = User(id=str(uuid.uuid4()), username="foreign", hashed_password="test", role="user")
    with pytest.raises(HTTPException) as error:
        await graph_api.graph_status(uuid.UUID(source.id), other)
    assert error.value.status_code == 404
    assert (await graph_api.retry_graph(uuid.UUID(source.id), user))["status"] == "pending"
    with pytest.raises(HTTPException) as conflict:
        await graph_api.retry_graph(uuid.UUID(source.id), user)
    assert conflict.value.status_code == 409
