"""PostgreSQL/HTTP comparison lifecycle, permissions and cancellation."""
import asyncio
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import numpy as np
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import get_current_user
from app.main import app
from app.models.agent import Message
from app.models.knowledge import KnowledgeItem
from app.models.source import Source, SourceDocument, SourceRevision
from app.services import comparison_service, scoped_chat_service, search_service
from app.services.answer_service import answer_payload, owned_answer, save_answer


@pytest.fixture
async def comparison_scope(db_session, owner_kb, monkeypatch):
    from app.api import answer_api
    user, kb = owner_kb
    versions = {}
    for name, text in (("资料A", "A支持事务，使用B树索引。"), ("资料B", "B不支持事务，使用哈希索引。")):
        source = Source(user_id=user.id, knowledge_base_id=kb.id, name=name)
        db_session.add(source)
        await db_session.flush()
        revision = SourceRevision(source_id=source.id, raw_hash=uuid4().hex, pipeline_version="test", state="ready")
        db_session.add(revision)
        await db_session.flush()
        source.current_revision_id = revision.id
        document = SourceDocument(revision_id=revision.id, logical_path="notes.md", text=text, content_hash=uuid4().hex)
        db_session.add(document)
        await db_session.flush()
        db_session.add(KnowledgeItem(knowledge_base_id=kb.id, revision_id=revision.id, document_id=document.id,
                                     title=name, content=text, embedding=[1.0] * 1024))
        versions[source.id] = revision.id
    await db_session.flush()
    @asynccontextmanager
    async def factory():
        yield db_session
    for module in (comparison_service, scoped_chat_service, search_service, answer_api):
        monkeypatch.setattr(module, "async_session", factory)
    async def encode(*args):
        return np.ones(1024)
    monkeypatch.setattr(search_service, "encode_texts", encode)
    async def generate(system, history, **kwargs):
        assignments = json.loads(system.split("编号到来源ID：")[-1])
        yield json.dumps({"rows": [{"dimension": "事务", "cells": [
            {"source_id": sid, "text": "按资料描述", "citation_indices": [int(index)]}
            for index, sid in assignments.items()
        ]}]}, ensure_ascii=False)
    monkeypatch.setattr(comparison_service, "stream_generate", generate)
    app.dependency_overrides[get_current_user] = lambda: user
    yield user, versions
    app.dependency_overrides.pop(get_current_user, None)


def decode_events(content):
    return [(part.split("\n", 1)[0][7:], json.loads(part.split("data: ", 1)[1]))
            for part in content.split("\n\n") if part.startswith("event: ")]


async def create_comparison(client, versions):
    response = await client.post("/api/chat/scoped", json={"question": "比较事务", "source_ids": list(versions), "response_mode": "comparison"})
    assert response.status_code == 200
    events = decode_events(response.text)
    assert events[-1][0] == "done", response.text
    return events[-1][1]["message_id"], next(data for event, data in events if event == "comparison"), next(data for event, data in events if event == "citations")


async def test_http_save_reload_candidate_and_adoption(client, db_session, comparison_scope):
    user, versions = comparison_scope
    message_id, artifact, citations = await create_comparison(client, versions)
    assert len(citations) == 2
    assert {item["source_id"]: item["revision_id"] for item in citations} == versions
    message = await db_session.get(Message, message_id)
    assert message.comparison == artifact and message.generation_complete
    response = await client.post("/api/answers", json={"message_id": message_id})
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["comparison"] == artifact
    assert {row["citation_index"] for row in saved["evidence"]} == {1, 2}
    assert (await client.get("/api/answers/" + saved["id"])).json()["comparison"] == artifact
    candidate = await client.post("/api/answers/" + saved["id"] + "/candidates")
    assert candidate.status_code == 201, candidate.text
    chosen = candidate.json()
    assert chosen["comparison"] == artifact
    adopted = await client.post("/api/answers/" + saved["id"] + "/accept", json={
        "candidate_id": chosen["id"], "expected_answer_revision_id": chosen["expected_answer_revision_id"],
        "expected_source_versions": chosen["source_versions"],
    })
    assert adopted.status_code == 200, adopted.text
    assert len(adopted.json()["versions"]) == 2
    assert all(row["comparison"] == artifact for row in adopted.json()["versions"])
    assert all(len(row["citations"]) == 2 for row in adopted.json()["versions"])


async def test_foreign_scope_invalid_count_and_unpublished_source(client, db_session, comparison_scope):
    user, versions = comparison_scope
    with pytest.raises(ValueError, match="不可用"):
        await comparison_service.source_names(versions, str(uuid4()))
    response = await client.post("/api/chat/scoped", json={"question": "比较", "source_ids": [*versions, str(uuid4())], "response_mode": "comparison"})
    assert response.status_code == 404
    sid = next(iter(versions))
    for ids in ([sid], [sid, sid], [str(uuid4()) for _ in range(5)]):
        response = await client.post("/api/chat/scoped", json={"question": "比较", "source_ids": ids, "response_mode": "comparison"})
        assert response.status_code == 422
    source = await db_session.get(Source, sid)
    source.current_revision_id = None
    await db_session.flush()
    response = await client.post("/api/chat/scoped", json={"question": "比较", "source_ids": list(versions), "response_mode": "comparison"})
    assert response.status_code == 422


async def test_deleted_quotes_unavailable_and_other_user_cannot_read(client, db_session, comparison_scope):
    from app.services.source_cleanup import redact_source
    user, versions = comparison_scope
    mid, artifact, _ = await create_comparison(client, versions)
    saved = await save_answer(db_session, user.id, mid)
    await redact_source(db_session, next(iter(versions)))
    payload = await answer_payload(db_session, saved)
    assert payload["comparison"] == artifact and payload["status"] == "unavailable"
    unavailable = [row for row in payload["evidence"] if row["state"] == "unavailable"]
    assert len(unavailable) == 1 and unavailable[0]["old_text"] is None
    with pytest.raises(HTTPException):
        await owned_answer(db_session, str(uuid4()), saved.id)


async def test_provider_interruption_has_no_complete_assistant(client, db_session, comparison_scope, monkeypatch):
    async def interrupted(*args, **kwargs):
        yield '{"rows":'
        raise RuntimeError("provider failure")
    monkeypatch.setattr(comparison_service, "stream_generate", interrupted)
    _, versions = comparison_scope
    response = await client.post("/api/chat/scoped", json={"question": "比较", "source_ids": list(versions), "response_mode": "comparison"})
    assert "event: error" in response.text and "event: done" not in response.text
    assert "event: comparison" not in response.text
    assert not (await db_session.execute(select(Message).where(Message.role == "assistant"))).scalars().all()


async def test_cancelled_comparison_has_no_assistant(db_session, comparison_scope, monkeypatch):
    user, versions = comparison_scope
    conv, resolved, _ = await scoped_chat_service.prepare_conversation("比较", list(versions), user.id, None)
    started = asyncio.Event()
    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
        yield ""
    monkeypatch.setattr(comparison_service, "stream_generate", blocked)
    stream = scoped_chat_service.run_comparison_stream(conv, "比较", resolved, user.id)
    await anext(stream)
    await anext(stream)
    task = asyncio.create_task(anext(stream))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await stream.aclose()
    assert not (await db_session.execute(select(Message).where(Message.conversation_id == conv, Message.role == "assistant"))).scalars().all()


async def test_migration_refuses_history_loss(db_session, comparison_scope):
    import importlib.util
    from pathlib import Path
    from unittest.mock import patch

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import DBAPIError
    path = Path(__file__).parents[2] / "app/migrations/versions/20261012_comparison.py"
    spec = importlib.util.spec_from_file_location("comparison_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    user, versions = comparison_scope
    conv, resolved, _ = await scoped_chat_service.prepare_conversation("比较", list(versions), user.id, None)
    await scoped_chat_service.persist_answer(conv, "比较", resolved, "内容", [], True, comparison={"kind": "source_comparison"})
    def downgrade(sync_session):
        with patch.object(module, "op", Operations(MigrationContext.configure(sync_session.connection()))):
            module.downgrade()
    with pytest.raises(DBAPIError, match="Comparison history"):
        async with db_session.begin_nested():
            await db_session.run_sync(downgrade)
