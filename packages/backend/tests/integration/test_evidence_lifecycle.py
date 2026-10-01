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
    from app.services import impact_service, scoped_chat_service, search_service, source_jobs

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
