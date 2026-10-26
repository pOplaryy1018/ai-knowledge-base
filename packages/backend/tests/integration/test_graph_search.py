"""Graph IDs must be resolved through current PostgreSQL access and version rules."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.graph_task import GraphBuildTask
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision
from app.services.graph_store import GraphCandidate


@pytest.mark.asyncio
async def test_graph_only_candidate_is_authorized_and_old_version_is_rejected(db_session, owner_kb, monkeypatch) -> None:
    from app.services import graph_search

    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                              pipeline_version="synthetic", state="ready")
    db_session.add(revision)
    await db_session.flush()
    document = SourceDocument(revision_id=revision.id, logical_path="one.txt",
                              text="甲公司收购乙公司。", locator={}, content_hash=uuid.uuid4().hex)
    db_session.add(document)
    await db_session.flush()
    item = KnowledgeItem(knowledge_base_id=kb.id, revision_id=revision.id, document_id=document.id,
                         title="one", content=document.text, source="source_revision",
                         source_metadata={"source_id": source.id}, status="available")
    db_session.add(item)
    build_id = str(uuid.uuid4())
    db_session.add(GraphBuildTask(source_id=source.id, revision_id=revision.id, user_id=user.id,
                                  extractor_version="graph-v1", status="completed", active_build_id=build_id))
    await db_session.flush()
    monkeypatch.setattr(graph_search, "async_session", async_sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False, join_transaction_mode="create_savepoint"))

    async def vector_empty(*args, **kwargs):
        return []

    async def graph_hits(*args, **kwargs):
        return [GraphCandidate(item.id, source.id, revision.id, build_id, 1)]

    monkeypatch.setattr(graph_search, "hybrid_search_versions", vector_empty)
    monkeypatch.setattr(graph_search, "find_candidate_chunk_ids", graph_hits)
    found = await graph_search.retrieve_version_evidence({source.id: revision.id}, "甲公司", user.id)
    assert [row.item.id for row in found] == [item.id]
    assert await graph_search.retrieve_version_evidence({source.id: revision.id}, "甲公司", str(uuid.uuid4())) == []
    assert await graph_search.retrieve_version_evidence({source.id: str(uuid.uuid4())}, "甲公司", user.id) == []
