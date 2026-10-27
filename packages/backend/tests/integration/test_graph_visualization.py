"""Visualization uses only current, authorized and source-verified graph rows."""

import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.graph_task import GraphBuildTask
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision
from app.services import graph_store, graph_visualization
from app.services.graph_extraction import ExtractedRelation
from app.services.source_publication import publish_revision


async def test_graph_visualization_validates_scope_and_original(db_session, owner_kb, monkeypatch):
    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        pytest.skip("TEST_NEO4J_URI missing; graph visualization integration not verified")
    assert uri in {"bolt://127.0.0.1:27687", "bolt://localhost:27687"}
    monkeypatch.setattr(settings, "neo4j_uri", uri)
    monkeypatch.setattr(settings, "neo4j_user", "neo4j")
    monkeypatch.setattr(settings, "neo4j_password", "evidence_test_only")
    monkeypatch.setattr(graph_visualization, "async_session", async_sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False, join_transaction_mode="create_savepoint"), raising=False)
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Synthetic", kind="document")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex, pipeline_version="test", state="ready")
    db_session.add(revision)
    await db_session.flush()
    quote = "甲公司收购乙公司。"
    content = "标题\n" + quote
    document = SourceDocument(revision_id=revision.id, logical_path="one.txt", text=content,
                              locator={}, content_hash=uuid.uuid4().hex)
    db_session.add(document)
    await db_session.flush()
    item = KnowledgeItem(knowledge_base_id=kb.id, revision_id=revision.id, document_id=document.id,
                         title="one", content=content, source="source_revision", source_metadata={},
                         status="available", locator={"char_start": 0, "char_end": len(content), "line_start": 1})
    db_session.add(item)
    await db_session.flush()
    await publish_revision(db_session, source.id, revision.id, None)
    task = (await db_session.execute(select(GraphBuildTask).where(GraphBuildTask.revision_id == revision.id))).scalar_one()
    build_id, stale_build = str(uuid.uuid4()), str(uuid.uuid4())
    task.status, task.active_build_id = "completed", build_id
    await db_session.flush()
    valid = ExtractedRelation(id="valid", item_id=item.id, subject="甲公司", subject_type="组织",
                              predicate="收购", object="乙公司", object_type="组织", quote_start=3, quote_end=len(content))
    invalid = ExtractedRelation(id="invalid", item_id=item.id, subject="甲公司", subject_type="组织",
                                predicate="收购", object="乙公司", object_type="组织", quote_start=0, quote_end=500)
    await graph_store.setup_schema()
    try:
        await graph_store.write_projection(build_id, user.id, source.id, revision.id, [valid, invalid])
        await graph_store.write_projection(stale_build, user.id, source.id, revision.id, [valid])
        result = await graph_visualization.list_source_relations(source.id, user.id)
        assert len(result["items"]) == 1
        row = result["items"][0]
        assert (row["subject"], row["predicate"], row["object"], row["quote"]) == ("甲公司", "收购", "乙公司", quote)
        assert row["document_id"] == document.id and row["revision_id"] == revision.id
        assert row["locator"]["line_start"] == 2 and row["locator"]["char_start"] == 3
        assert (await graph_visualization.list_source_relations(source.id, user.id, limit=1))["truncated"] is True
        from httpx import ASGITransport, AsyncClient

        from app.core.security import get_current_user
        from app.main import app
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(f"/api/sources/{source.id}/graph/relations")
                assert response.status_code == 200 and response.json()["items"][0]["quote"] == quote
                assert (await client.get(f"/api/sources/{source.id}/graph/relations?limit=51")).status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)
        with pytest.raises(HTTPException) as denied:
            await graph_visualization.list_source_relations(source.id, str(uuid.uuid4()))
        assert denied.value.status_code == 404

        async def unavailable(*_args, **_kwargs):
            raise RuntimeError("driver unavailable")

        monkeypatch.setattr(graph_visualization, "list_projection_relations", unavailable)
        with pytest.raises(HTTPException) as down:
            await graph_visualization.list_source_relations(source.id, user.id)
        assert down.value.status_code == 503

        next_revision = SourceRevision(source_id=source.id, raw_hash=uuid.uuid4().hex,
                                       pipeline_version="next", state="ready")
        db_session.add(next_revision)
        await db_session.flush()

        async def version_changes(*args, **kwargs):
            candidates = await graph_store.list_projection_relations(*args, **kwargs)
            await publish_revision(db_session, source.id, next_revision.id, revision.id)
            return candidates

        monkeypatch.setattr(graph_visualization, "list_projection_relations", version_changes)
        with pytest.raises(HTTPException) as stale:
            await graph_visualization.list_source_relations(source.id, user.id)
        assert stale.value.status_code == 409
    finally:
        await graph_store.delete_build(build_id)
        await graph_store.delete_build(stale_build)
        await graph_store.close_driver()
