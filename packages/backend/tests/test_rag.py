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
