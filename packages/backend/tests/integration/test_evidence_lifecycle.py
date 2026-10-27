"""Actual PG + HTTP + worker lifecycle; deterministic embeddings and provider."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_user
from app.main import app


@pytest.fixture
async def lifecycle_client(db_session, owner_kb, monkeypatch, tmp_path):
    from app.api import answer_api, source_api
    from app.services import (
        comparison_service,
        impact_service,
        scoped_chat_service,
        search_service,
        source_jobs,
    )

    user, kb = owner_kb

    @asynccontextmanager
    async def session_factory():
        yield db_session

    for module in [answer_api, source_api, impact_service, scoped_chat_service, search_service, source_jobs]:
        monkeypatch.setattr(module, "async_session", session_factory)
    monkeypatch.setattr(source_api, "SOURCE_ROOT", tmp_path / "sources")
    from app.api import import_api
    monkeypatch.setattr(import_api, "get_arq", AsyncMock(return_value=AsyncMock()))

    async def embedding(texts):
        return np.ones(1024) if isinstance(texts, str) else np.ones((len(texts), 1024))

    async def provider(prompt, history):
        yield "资料中的当前规定："
        yield prompt.split("\n")[-1] + " [1]"

    monkeypatch.setattr(source_jobs, "encode_texts", embedding)
    monkeypatch.setattr(search_service, "encode_texts", embedding)
    monkeypatch.setattr(comparison_service, "encode_texts", embedding)
    monkeypatch.setattr(scoped_chat_service, "stream_generate", provider)
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, user, kb
    app.dependency_overrides.pop(get_current_user, None)


async def test_document_update_answer_review_and_adoption(lifecycle_client, db_session):
    import json

    from app.services.source_jobs import process_source_import

    client, user, kb = lifecycle_client
    result = await client.post("/api/sources", json={"name": "policy", "knowledge_base_id": kb.id})
    assert result.status_code == 201, result.text
    source_id = result.json()["id"]
    upload = await client.post(f"/api/sources/{source_id}/revisions", files={"file": ("policy.txt", "最初的规定", "text/plain")})
    assert upload.status_code == 202, upload.text
    task = upload.json()
    assert (await process_source_import({}, task["task_id"]))["status"] == "completed"
    response = await client.post("/api/chat/scoped", json={"question": "规定是什么", "source_ids": [source_id]})
    assert response.status_code == 200, response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    message_id = events[-1]["message_id"]
    saved = await client.post("/api/answers", json={"message_id": message_id})
    assert saved.status_code == 201, saved.text
    answer = saved.json()
    assert answer["status"] == "unchanged"
    assert answer["evidence"][0]["old_text"] == "最初的规定"
    evidence_id = answer["evidence"][0]["evidence_id"]
    detail = await client.get(f"/api/evidence/{evidence_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["content"] == "最初的规定"
    original = await client.get(
        f'/api/sources/{source_id}/revisions/{detail.json()["revision_id"]}/original'
    )
    assert original.status_code == 200
    assert original.text == "最初的规定"
    assert "policy.txt" in original.headers["content-disposition"]
    upload2 = await client.post(f"/api/sources/{source_id}/revisions", files={"file": ("policy.txt", "更新后的规定", "text/plain")})
    assert upload2.status_code == 202, upload2.text
    assert (await process_source_import({}, upload2.json()["task_id"]))["status"] == "completed"
    updated = (await client.get(f'/api/answers/{answer["id"]}')).json()
    assert updated["status"] == "needs_review"
    assert updated["evidence"][0]["current_text"] == "更新后的规"
    reviews = (await client.get("/api/reviews")).json()["items"]
    assert reviews and reviews[0]["answer_id"] == answer["id"]
    candidate = await client.post(f'/api/answers/{answer["id"]}/candidates')
    assert candidate.status_code == 201, candidate.text
    payload = candidate.json()
    adopted = await client.post(f'/api/answers/{answer["id"]}/accept', json={"candidate_id": payload["id"],
               "expected_answer_revision_id": payload["expected_answer_revision_id"], "expected_source_versions": payload["source_versions"]})
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["status"] == "unchanged"
    assert len(adopted.json()["versions"]) == 2
    assert "最初的规定" in adopted.json()["versions"][0]["content"]
    duplicate = await client.post(f"/api/sources/{source_id}/revisions", files={"file": ("policy.txt", "更新后的规定", "text/plain")})
    assert duplicate.json()["status"] == "completed"


async def test_candidate_reports_unmatched_citation(lifecycle_client, monkeypatch):
    import json

    from app.services import scoped_chat_service
    from app.services.source_jobs import process_source_import

    client, _, kb = lifecycle_client
    source = (await client.post("/api/sources", json={"name": "policy", "knowledge_base_id": kb.id})).json()
    upload = await client.post(f'/api/sources/{source["id"]}/revisions', files={"file": ("policy.txt", "合成规定", "text/plain")})
    assert (await process_source_import({}, upload.json()["task_id"]))["status"] == "completed"
    response = await client.post("/api/chat/scoped", json={"question": "规定是什么", "source_ids": [source["id"]]})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    saved = await client.post("/api/answers", json={"message_id": events[-1]["message_id"]})
    assert saved.status_code == 201, saved.text
    monkeypatch.setattr(scoped_chat_service, "generate_scoped_answer", AsyncMock(return_value=("答案[99]", [])))
    candidate = await client.post(f'/api/answers/{saved.json()["id"]}/candidates')
    assert candidate.status_code == 201, candidate.text
    assert "未匹配" in candidate.json()["warning"]


async def test_failed_sync_keeps_previous_published_head(lifecycle_client, monkeypatch):
    from app.services import source_jobs

    client, _, kb = lifecycle_client
    source = (await client.post("/api/sources", json={"name": "policy", "knowledge_base_id": kb.id})).json()
    first = (await client.post(f'/api/sources/{source["id"]}/revisions', files={"file": ("p.txt", "版本一", "text/plain")})).json()
    assert (await source_jobs.process_source_import({}, first["task_id"]))["status"] == "completed"
    second = (await client.post(f'/api/sources/{source["id"]}/revisions', files={"file": ("p.txt", "版本二", "text/plain")})).json()
    monkeypatch.setattr(source_jobs, "encode_texts", AsyncMock(side_effect=RuntimeError("offline")))
    assert (await source_jobs.process_source_import({}, second["task_id"]))["status"] == "failed"
    items = (await client.get("/api/sources")).json()["items"]
    assert items[0]["current_revision_id"] == first["revision_id"]


async def test_document_history_rollback_creates_new_publication_and_rejects_stale_head(lifecycle_client, db_session):
    import json

    from sqlalchemy import select

    from app.models.source import SourceChangeEvent
    from app.services.impact_service import process_impact_events
    from app.services.source_jobs import process_source_import

    client, _, kb = lifecycle_client
    source = (await client.post("/api/sources", json={"name": "history", "knowledge_base_id": kb.id})).json()
    source_id = source["id"]
    first = (await client.post(f"/api/sources/{source_id}/revisions", files={"file": ("p.txt", "版本一", "text/plain")})).json()
    assert (await process_source_import({}, first["task_id"]))["status"] == "completed"
    second = (await client.post(f"/api/sources/{source_id}/revisions", files={"file": ("p.txt", "版本二", "text/plain")})).json()
    assert (await process_source_import({}, second["task_id"]))["status"] == "completed"
    chat = await client.post("/api/chat/scoped", json={"question": "版本是什么", "source_ids": [source_id]})
    events = [json.loads(line[6:]) for line in chat.text.splitlines() if line.startswith("data: ")]
    saved = await client.post("/api/answers", json={"message_id": events[-1]["message_id"]})
    assert saved.status_code == 201
    history_response = await client.get(f"/api/sources/{source_id}/publications")
    assert history_response.status_code == 200
    before = history_response.json()["items"]
    assert [row["revision_id"] for row in before] == [second["revision_id"], first["revision_id"]]
    rollback = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": first["revision_id"], "expected_publication_id": before[0]["id"]})
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["current_revision_id"] == first["revision_id"]
    history = (await client.get(f"/api/sources/{source_id}/publications")).json()["items"]
    assert [row["revision_id"] for row in history] == [first["revision_id"], second["revision_id"], first["revision_id"]]
    assert [row["sequence"] for row in history] == [3, 2, 1]
    event = (await db_session.execute(select(SourceChangeEvent).where(
        SourceChangeEvent.publication_id == history[0]["id"]))).scalar_one()
    assert event.old_revision_id == second["revision_id"] and event.new_revision_id == first["revision_id"]
    await process_impact_events()
    answer = await client.get(f"/api/answers/{saved.json()['id']}")
    assert answer.json()["status"] == "needs_review"
    stale = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": second["revision_id"], "expected_publication_id": before[0]["id"]})
    assert stale.status_code == 409
    assert (await client.get("/api/sources")).json()["items"][0]["current_revision_id"] == first["revision_id"]


async def test_graph_visualization_tracks_document_rollback(lifecycle_client, db_session, monkeypatch):
    import json
    import os

    from sqlalchemy import select

    from app.api import source_api
    from app.core.config import settings
    from app.models.graph_task import GraphBuildTask
    from app.services import graph_extraction, graph_jobs, graph_store, graph_visualization
    from app.services.source_jobs import process_source_import

    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        pytest.skip("TEST_NEO4J_URI missing; graph rollback integration not verified")
    assert uri in {"bolt://127.0.0.1:27687", "bolt://localhost:27687"}
    monkeypatch.setattr(settings, "neo4j_uri", uri)
    monkeypatch.setattr(settings, "neo4j_user", "neo4j")
    monkeypatch.setattr(settings, "neo4j_password", "evidence_test_only")
    monkeypatch.setattr(settings, "llm_api_key", "synthetic-test-only")
    monkeypatch.setattr(graph_jobs, "async_session", source_api.async_session)
    monkeypatch.setattr(graph_visualization, "async_session", source_api.async_session)

    async def synthetic_extraction(content):
        target = "乙公司" if "乙公司" in content else "丙公司"
        return json.dumps({"relations": [{"subject": "甲公司", "subject_type": "组织", "predicate": "收购",
                                          "object": target, "object_type": "组织", "quote": content}]}, ensure_ascii=False)

    monkeypatch.setattr(graph_extraction, "_generate_relation_json", synthetic_extraction)
    client, user, kb = lifecycle_client
    source = (await client.post("/api/sources", json={"name": "graph history", "knowledge_base_id": kb.id})).json()
    source_id = source["id"]
    revisions = []
    try:
        for target in ("乙公司", "丙公司"):
            task = (await client.post(f"/api/sources/{source_id}/revisions", files={
                "file": ("policy.txt", f"甲公司收购{target}。", "text/plain")})).json()
            assert (await process_source_import({}, task["task_id"]))["status"] == "completed"
            revisions.append(task["revision_id"])
            build = (await db_session.execute(select(GraphBuildTask).where(
                GraphBuildTask.revision_id == task["revision_id"]))).scalar_one()
            assert (await graph_jobs.process_graph_build({}, build.id))["status"] == "completed"
            graph = await client.get(f"/api/sources/{source_id}/graph/relations")
            assert graph.status_code == 200, graph.text
            assert graph.json()["items"][0]["object"] == target
        history = (await client.get(f"/api/sources/{source_id}/publications")).json()["items"]
        rollback = await client.post(f"/api/sources/{source_id}/rollback", json={
            "target_revision_id": revisions[0], "expected_publication_id": history[0]["id"]})
        assert rollback.status_code == 200, rollback.text
        graph = await client.get(f"/api/sources/{source_id}/graph/relations")
        assert graph.status_code == 200, graph.text
        assert [(row["revision_id"], row["object"], row["quote"]) for row in graph.json()["items"]] == [
            (revisions[0], "乙公司", "甲公司收购乙公司。")]
        assert len((await db_session.execute(select(GraphBuildTask).where(
            GraphBuildTask.source_id == source_id))).scalars().all()) == 2
    finally:
        await graph_store.delete_source(user.id, source_id)
        await graph_store.close_driver()


async def test_rollback_rejects_other_owner_source_and_unavailable_original(lifecycle_client, db_session, tmp_path):
    import uuid
    from datetime import datetime, timezone
    from pathlib import Path

    from app.models.source import Source, SourceRevision
    from app.models.user import User
    from app.services.source_jobs import process_source_import

    client, owner, kb = lifecycle_client
    source_id = (await client.post("/api/sources", json={"name": "first", "knowledge_base_id": kb.id})).json()["id"]
    revisions = []
    for text in ("版本一", "版本二"):
        task = (await client.post(f"/api/sources/{source_id}/revisions", files={"file": ("p.txt", text, "text/plain")})).json()
        assert (await process_source_import({}, task["task_id"]))["status"] == "completed"
        revisions.append(task["revision_id"])
    history = (await client.get(f"/api/sources/{source_id}/publications")).json()["items"]
    expected = history[0]["id"]
    current = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": revisions[1], "expected_publication_id": expected})
    assert current.status_code == 409

    other_source = (await client.post("/api/sources", json={"name": "other", "knowledge_base_id": kb.id})).json()["id"]
    other_task = (await client.post(f"/api/sources/{other_source}/revisions", files={"file": ("x.txt", "其他", "text/plain")})).json()
    assert (await process_source_import({}, other_task["task_id"]))["status"] == "completed"
    wrong = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": other_task["revision_id"], "expected_publication_id": expected})
    assert wrong.status_code == 404

    outsider = User(username=f"other_{uuid.uuid4().hex}", hashed_password="test", role="user")
    db_session.add(outsider)
    await db_session.flush()
    app.dependency_overrides[get_current_user] = lambda: outsider
    assert (await client.get(f"/api/sources/{source_id}/publications")).status_code == 404
    denied = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": revisions[0], "expected_publication_id": expected})
    assert denied.status_code == 404
    app.dependency_overrides[get_current_user] = lambda: owner

    other_history = (await client.get(f"/api/sources/{other_source}/publications")).json()["items"]
    source = await db_session.get(Source, source_id)
    source.current_publication_id = other_history[0]["id"]
    await db_session.flush()
    corrupt_head = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": revisions[0], "expected_publication_id": other_history[0]["id"]})
    assert corrupt_head.status_code == 409
    source.current_publication_id = expected
    await db_session.flush()

    source.active_task_id = str(uuid.uuid4())
    await db_session.flush()
    blocked_task = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": revisions[0], "expected_publication_id": expected})
    assert blocked_task.status_code == 409
    source.active_task_id = None
    source.archived_at = datetime.now(timezone.utc)
    await db_session.flush()
    blocked_archive = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": revisions[0], "expected_publication_id": expected})
    assert blocked_archive.status_code == 409
    source.archived_at = None
    await db_session.flush()

    revision = await db_session.get(SourceRevision, revisions[0])
    original = Path(revision.file_path).resolve()
    assert original.is_relative_to(tmp_path.resolve())
    original.unlink()
    missing = await client.post(f"/api/sources/{source_id}/rollback", json={
        "target_revision_id": revisions[0], "expected_publication_id": expected})
    assert missing.status_code == 409
    source = await db_session.get(Source, source_id)
    assert source.current_revision_id == revisions[1] and source.current_publication_id == expected
