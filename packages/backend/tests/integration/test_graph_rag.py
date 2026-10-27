"""Synthetic end-to-end graph recall with real PostgreSQL and Neo4j."""

import json
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.graph_task import GraphBuildTask
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision
from app.services import (
    graph_extraction,
    graph_jobs,
    graph_search,
    graph_store,
    scoped_chat_service,
)
from app.services.search_service import SearchResult
from app.services.source_cleanup import redact_source
from app.services.source_publication import publish_revision


@pytest.mark.asyncio
async def test_graph_recall_yields_original_citation_and_ignores_old_version(db_session, owner_kb, monkeypatch) -> None:
    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        pytest.skip("TEST_NEO4J_URI missing; graph RAG integration not verified")
    assert uri in {"bolt://127.0.0.1:27687", "bolt://localhost:27687"}
    monkeypatch.setattr(settings, "neo4j_uri", uri)
    monkeypatch.setattr(settings, "neo4j_user", "neo4j")
    monkeypatch.setattr(settings, "neo4j_password", "evidence_test_only")
    monkeypatch.setattr(settings, "llm_api_key", "synthetic-test-only")
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                              pipeline_version="synthetic", state="ready")
    db_session.add(revision)
    await db_session.flush()
    quote = "甲公司收购乙公司。"
    document = SourceDocument(revision_id=revision.id, logical_path="one.txt",
                              text=quote, locator={}, content_hash=uuid.uuid4().hex)
    db_session.add(document)
    await db_session.flush()
    item = KnowledgeItem(knowledge_base_id=kb.id, revision_id=revision.id, document_id=document.id,
                         title="one", content=quote, source="source_revision",
                         source_metadata={"source_id": source.id}, status="available",
                         locator={"logical_path": "one.txt", "char_start": 0, "char_end": len(quote)})
    db_session.add(item)
    await db_session.flush()
    await publish_revision(db_session, source.id, revision.id, None)
    factory = async_sessionmaker(bind=db_session.bind, class_=AsyncSession,
                                 expire_on_commit=False, join_transaction_mode="create_savepoint")
    monkeypatch.setattr(graph_jobs, "async_session", factory)
    monkeypatch.setattr(graph_search, "async_session", factory)
    monkeypatch.setattr(scoped_chat_service, "async_session", factory)

    async def synthetic_extraction(content: str) -> str:
        assert content == quote
        return json.dumps({"relations": [{"subject": "甲公司", "subject_type": "组织",
            "predicate": "收购", "object": "乙公司", "object_type": "组织", "quote": quote}]}, ensure_ascii=False)

    async def vector_miss(*args, **kwargs):
        return []

    monkeypatch.setattr(graph_extraction, "_generate_relation_json", synthetic_extraction)
    monkeypatch.setattr(graph_search, "hybrid_search_versions", vector_miss)
    task = (await db_session.execute(select(GraphBuildTask).where(GraphBuildTask.revision_id == revision.id))).scalar_one()
    try:
        assert await graph_jobs.process_graph_build({}, task.id) == {"status": "completed"}
        await db_session.refresh(task)
        evidence = await scoped_chat_service.prepare_evidence("甲公司收购了谁？", {source.id: revision.id}, user.id)
        assert len(evidence) == 1
        assert evidence[0]["content"] == quote
        assert evidence[0]["source_id"] == source.id
        assert evidence[0]["revision_id"] == revision.id
        assert evidence[0]["document_id"] == document.id
        assert evidence[0]["locator"]["logical_path"] == "one.txt"
        item.content = "不属于原文的伪造内容"
        await db_session.flush()
        assert await scoped_chat_service.prepare_evidence("甲公司收购了谁？", {source.id: revision.id}, user.id) == []
        item.content = quote
        await db_session.flush()
        assert await graph_search.retrieve_version_evidence(
            {source.id: revision.id}, "甲公司", str(uuid.uuid4())) == []
        next_revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                                       pipeline_version="synthetic", state="ready")
        db_session.add(next_revision)
        await db_session.flush()
        await publish_revision(db_session, source.id, next_revision.id, revision.id)
        assert await graph_search.retrieve_version_evidence(
            {source.id: next_revision.id}, "甲公司", user.id) == []

        async def graph_down(*args, **kwargs):
            raise RuntimeError("graph unavailable")

        async def vector_hit(*args, **kwargs):
            return [SearchResult(item, 1 / 61)]

        monkeypatch.setattr(graph_search, "find_candidate_chunk_ids", graph_down)
        monkeypatch.setattr(graph_search, "hybrid_search_versions", vector_hit)
        assert [row.item.id for row in await graph_search.retrieve_version_evidence(
            {source.id: revision.id}, "甲公司", user.id)] == [item.id]
        await redact_source(db_session, source.id)
        await graph_jobs.process_graph_cleanup(db_session)
        await db_session.flush()
        assert await graph_store.find_candidate_chunk_ids(user.id, {revision.id: task.active_build_id},
                                                          "甲公司", 5) == []
    finally:
        await graph_store.delete_source(user.id, source.id)
        await graph_store.close_driver()
