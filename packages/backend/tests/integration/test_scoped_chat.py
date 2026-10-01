"""Scoped ownership, readiness, frozen history and incomplete stream integration."""
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.agent import Conversation, Message
from app.models.source import Source, SourceRevision
from app.services import scoped_chat_service as service


@pytest.fixture
async def source(db_session, owner_kb, monkeypatch):
    user, kb = owner_kb
    source = Source(user_id=user.id, knowledge_base_id=kb.id, name="Scoped")
    db_session.add(source)
    await db_session.flush()
    revision = SourceRevision(source_id=source.id, raw_hash="hash", pipeline_version="v1", state="ready")
    db_session.add(revision)
    await db_session.flush()
    source.current_revision_id = revision.id
    await db_session.flush()

    @asynccontextmanager
    async def factory():
        yield db_session

    monkeypatch.setattr(service, "async_session", factory)
    return user, source, revision


async def test_owner_and_readiness(db_session, source):
    user, item, revision = source
    assert await service.resolve_scope(db_session, user.id, [item.id]) == {item.id: revision.id}
    with pytest.raises(HTTPException) as error:
        await service.resolve_scope(db_session, str(uuid4()), [item.id])
    assert error.value.status_code == 404
    revision.state = "staging"
    await db_session.flush()
    with pytest.raises(HTTPException) as error:
        await service.resolve_scope(db_session, user.id, [item.id])
    assert error.value.status_code == 422


async def test_frozen_source_scope_refreshes_versions_and_foreign_conversation(db_session, source):
    user, item, revision = source
    conv_id, versions, _ = await service.prepare_conversation("first", [item.id], user.id, None)
    await service.persist_answer(conv_id, "first", versions, "old answer[1]", [], True)
    next_revision = SourceRevision(source_id=item.id, raw_hash="next", pipeline_version="v1", state="ready")
    db_session.add(next_revision)
    await db_session.flush()
    item.current_revision_id = next_revision.id
    await db_session.flush()
    _, refreshed, history = await service.prepare_conversation("next", [item.id], user.id, conv_id)
    assert versions == {item.id: revision.id}
    assert refreshed == {item.id: next_revision.id}
    assert all(row["content"] != "old answer[1]" for row in history)
    with pytest.raises(HTTPException) as error:
        await service.prepare_conversation("wrong", [item.id], str(uuid4()), conv_id)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await service.prepare_conversation("wrong", [str(uuid4())], user.id, conv_id)
    assert error.value.status_code == 409
    assert (await db_session.get(Conversation, conv_id)).agent_id is None


async def test_interrupted_answer_is_incomplete(db_session, source, monkeypatch):
    user, item, revision = source
    conv_id, versions, history = await service.prepare_conversation("question", [item.id], user.id, None)

    async def evidence(*args):
        return [{"index": 1, "content": "fact", "knowledge_title": "title", "quote": "fact"}]

    async def generate(*args):
        yield "partial[1]"
        raise RuntimeError("provider failed")

    monkeypatch.setattr(service, "prepare_evidence", evidence)
    monkeypatch.setattr(service, "stream_generate", generate)
    events = [part async for part in service.run_scoped_stream(conv_id, "question", versions, history, user.id)]
    assert b"event: error" in events[-1]
    answer = (await db_session.execute(select(Message).where(Message.conversation_id == conv_id, Message.role == "assistant"))).scalar_one()
    assert answer.generation_complete is False
    assert answer.question == "question"
    assert answer.source_versions == {item.id: revision.id}


async def test_no_evidence_skips_provider(db_session, source, monkeypatch):
    user, item, _ = source
    conv_id, versions, history = await service.prepare_conversation("question", [item.id], user.id, None)

    async def evidence(*args):
        return []

    monkeypatch.setattr(service, "prepare_evidence", evidence)
    def forbidden(*args):
        raise AssertionError("LLM must not run")
    monkeypatch.setattr(service, "stream_generate", forbidden)
    events = [part async for part in service.run_scoped_stream(conv_id, "question", versions, history, user.id)]
    assert b"message_id" in events[-1]


async def test_version_search_authorized_document_pairs(db_session, source, monkeypatch):
    import numpy as np

    from app.models.knowledge import KnowledgeItem
    from app.models.source import SourceDocument
    from app.services import search_service

    user, item, revision = source
    document = SourceDocument(revision_id=revision.id, logical_path="notes/a.md", text="retrieval fact", content_hash="a")
    db_session.add(document)
    await db_session.flush()
    chunk = KnowledgeItem(knowledge_base_id=item.knowledge_base_id, revision_id=revision.id,
                          document_id=document.id, title="retrieval", content="retrieval fact", embedding=[1.0] * 1024)
    db_session.add(chunk)
    await db_session.flush()

    @asynccontextmanager
    async def factory():
        yield db_session

    async def encode(*args):
        return np.ones(1024)

    monkeypatch.setattr(search_service, "async_session", factory)
    monkeypatch.setattr(search_service, "encode_texts", encode)
    results = await search_service.hybrid_search_versions({item.id: revision.id}, "retrieval", user_id=user.id)
    assert [result.item.id for result in results] == [chunk.id]
    assert results[0].dense_score > 0
    assert results[0].sparse_score > 0
    assert await search_service.hybrid_search_versions({item.id: revision.id}, "retrieval", user_id=str(uuid4())) == []
    assert await search_service.hybrid_search_versions({item.id: str(uuid4())}, "retrieval", user_id=user.id) == []
    evidence = await service.prepare_evidence("retrieval", {item.id: revision.id}, user.id)
    assert evidence[0]["locator"]["logical_path"] == "notes/a.md"
    assert evidence[0]["quote"] == chunk.content


async def test_closed_stream_persists_incomplete(db_session, source, monkeypatch):
    user, item, _ = source
    conv_id, versions, history = await service.prepare_conversation("question", [item.id], user.id, None)

    async def evidence(*args):
        return [{"index": 1, "content": "fact", "knowledge_title": "title", "quote": "fact"}]

    async def generate(*args):
        yield "partial[1]"
        yield "more"

    monkeypatch.setattr(service, "prepare_evidence", evidence)
    monkeypatch.setattr(service, "stream_generate", generate)
    stream = service.run_scoped_stream(conv_id, "question", versions, history, user.id)
    assert b"event: meta" in await anext(stream)
    assert b"event: token" in await anext(stream)
    await stream.aclose()
    answer = (await db_session.execute(select(Message).where(Message.conversation_id == conv_id, Message.role == "assistant"))).scalar_one()
    assert answer.content == "partial[1]"
    assert answer.generation_complete is False


async def test_single_generation_keeps_resolved_revision_after_publish(db_session, source, monkeypatch):
    user, item, revision = source
    conv_id, versions, history = await service.prepare_conversation("question", [item.id], user.id, None)
    next_revision = SourceRevision(source_id=item.id, raw_hash="published-during-generation", pipeline_version="v1", state="ready")
    db_session.add(next_revision)
    await db_session.flush()
    item.current_revision_id = next_revision.id
    await db_session.flush()

    async def evidence(question, selected_versions, user_id):
        assert selected_versions == {item.id: revision.id}
        return []

    monkeypatch.setattr(service, "prepare_evidence", evidence)
    events = [part async for part in service.run_scoped_stream(conv_id, "question", versions, history, user.id)]
    assert b"event: done" in events[-1]
    answer = (await db_session.execute(select(Message).where(Message.conversation_id == conv_id, Message.role == "assistant"))).scalar_one()
    assert answer.source_versions == {item.id: revision.id}
