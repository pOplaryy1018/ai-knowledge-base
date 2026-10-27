import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


async def test_hybrid_always_recalls_keywords_and_filters_owner(monkeypatch):
    from app.services import search_service as service

    dense = [(SimpleNamespace(id=str(i), title="dense", content="text"), 0.8) for i in range(5)]
    dense_result, sparse_result = MagicMock(), MagicMock()
    dense_result.all.return_value = dense
    sparse_result.scalars.return_value.all.return_value = [SimpleNamespace(id="keyword", title="ERROR42", content="exact")]
    session = AsyncMock()
    session.execute.side_effect = [dense_result, sparse_result]
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    monkeypatch.setattr(service, "encode_texts", AsyncMock(return_value=SimpleNamespace(tolist=lambda: [0.0] * 1024)))
    results = await service.hybrid_search([str(i) for i in range(5)] + ["keyword"], "ERROR42", user_id="alice")
    assert session.execute.await_count == 2
    assert any(result.item.id == "keyword" for result in results)
    for call in session.execute.await_args_list:
        sql = str(call.args[0])
        assert "knowledge_bases.user_id" in sql


async def test_scoped_keyword_hit_survives_embedding_failure(monkeypatch):
    from app.services import search_service as service

    item = SimpleNamespace(id="keyword", title="ERROR42", content="合成资料")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    session = AsyncMock()
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    monkeypatch.setattr(service, "encode_texts", AsyncMock(side_effect=RuntimeError("unavailable")))

    results = await service.hybrid_search_versions({"source": "revision"}, "ERROR42", user_id="alice")
    assert [result.item.id for result in results] == ["keyword"]
    sql = str(session.execute.await_args.args[0])
    assert "sources.user_id" in sql and "source_revisions.id" in sql


async def test_scoped_keyword_starts_while_embedding_is_running(monkeypatch):
    from app.services import search_service as service

    started, release = asyncio.Event(), asyncio.Event()

    async def encode(_query):
        await release.wait()
        return SimpleNamespace(tolist=lambda: [0.0] * 1024)

    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    session = AsyncMock()

    async def execute(_statement):
        started.set()
        return result

    session.execute.side_effect = execute
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    monkeypatch.setattr(service, "encode_texts", encode)
    task = asyncio.create_task(service.hybrid_search_versions({"source": "revision"}, "ERROR42", user_id="alice"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
    finally:
        release.set()
        await task


async def test_scoped_failure_and_empty_keyword_is_not_reported_as_no_evidence(monkeypatch):
    from app.services import search_service as service

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    monkeypatch.setattr(service, "encode_texts", AsyncMock(side_effect=RuntimeError("unavailable")))
    with pytest.raises(RuntimeError, match="without verified candidates"):
        await service.hybrid_search_versions({"source": "revision"}, "ERROR42", user_id="alice")


async def test_scoped_successful_empty_routes_return_no_results(monkeypatch):
    from app.services import search_service as service

    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    monkeypatch.setattr(service, "encode_texts", AsyncMock(return_value=SimpleNamespace(tolist=lambda: [0.0] * 1024)))
    assert await service.hybrid_search_versions({"source": "revision"}, "ERROR42", user_id="alice") == []


async def test_conversation_reuse_requires_matching_agent(monkeypatch):
    from app.services import chat_service as service

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    with pytest.raises(ValueError):
        await service.get_or_create_conversation("agent", "alice", conversation_id="other-agent-conv")
    assert "conversations.agent_id" in str(session.execute.call_args.args[0])
    session.commit.assert_not_awaited()


async def test_code_splitter_constructs_actual_chunks():
    from app.worker import split_import_text

    chunks = await split_import_text("def hello():\n    return 42\n", "sample.py")
    assert chunks and chunks[0].content
