import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import chat_service


@pytest.fixture
def chat_mocks(monkeypatch):
    agent = SimpleNamespace(id="agent", knowledge_ids=["item"], name="Agent", prompt_template=None)
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = agent
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(chat_service, "async_session", lambda: context)
    mocks = {
        "get_or_create_conversation": AsyncMock(return_value=SimpleNamespace(id="conversation")),
        "save_message": AsyncMock(),
        "hybrid_search": AsyncMock(return_value=[]),
        "generate_system_prompt": AsyncMock(return_value="prompt"),
        "get_conversation_history": AsyncMock(return_value=[]),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(chat_service, name, mock)
    return mocks


@pytest.mark.parametrize("stage", ["hybrid_search", "generate_system_prompt", "get_conversation_history"])
async def test_context_failure_emits_safe_error(chat_mocks, stage):
    chat_mocks[stage].side_effect = RuntimeError("secret database password")
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", "question")]
    assert b"event: error" in events[-1]
    assert b"secret" not in b"".join(events)
    assert chat_mocks["save_message"].await_count == 1


async def test_generation_failure_saves_partial_once(monkeypatch, chat_mocks):
    async def generate(*args):
        yield "已生成"
        yield "部分"
        raise RuntimeError("secret provider credential")

    monkeypatch.setattr(chat_service, "stream_generate", generate)
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", "question")]
    assert b"event: error" in events[-1]
    assert b"secret" not in b"".join(events)
    assert not any(b"event: done" in event for event in events)
    assert chat_mocks["save_message"].await_count == 2
    chat_mocks["save_message"].assert_awaited_with("conversation", "assistant", "已生成部分", [])
    chat_mocks["hybrid_search"].assert_awaited_once_with(
        knowledge_ids=["item"], query="question", top_k=5, user_id="owner", is_admin=False,
    )


async def test_client_cancellation_saves_partial(monkeypatch, chat_mocks):
    generating = asyncio.Event()

    async def generate(*args):
        yield "部分回答"
        generating.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(chat_service, "stream_generate", generate)

    async def consume():
        return [event async for event in chat_service.run_chat_stream("agent", "owner", "question")]

    task = asyncio.create_task(consume())
    await asyncio.wait_for(generating.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    chat_mocks["save_message"].assert_awaited_with("conversation", "assistant", "部分回答", [])
    assert chat_mocks["save_message"].await_count == 2


async def test_generator_close_saves_partial(monkeypatch, chat_mocks):
    async def generate(*args):
        yield "部分回答"
        yield "继续回答"

    monkeypatch.setattr(chat_service, "stream_generate", generate)
    stream = chat_service.run_chat_stream("agent", "owner", "question")
    assert b"event: meta" in await anext(stream)
    assert b"event: token" in await anext(stream)
    await stream.aclose()
    chat_mocks["save_message"].assert_awaited_with("conversation", "assistant", "部分回答", [])
    assert chat_mocks["save_message"].await_count == 2


async def test_success_saves_answer_once(monkeypatch, chat_mocks):
    async def generate(*args):
        yield "完整回答"

    monkeypatch.setattr(chat_service, "stream_generate", generate)
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", "question")]
    assert b"event: done" in events[-1]
    assert chat_mocks["save_message"].await_count == 2
    chat_mocks["save_message"].assert_awaited_with("conversation", "assistant", "完整回答", [])


async def test_save_failure_emits_safe_error_without_duplicate(monkeypatch, chat_mocks):
    async def generate(*args):
        yield "完整回答"

    monkeypatch.setattr(chat_service, "stream_generate", generate)
    chat_mocks["save_message"].side_effect = [None, RuntimeError("secret database credential")]
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", "question")]
    assert b"event: error" in events[-1]
    assert b"secret" not in b"".join(events)
    assert not any(b"event: done" in event for event in events)
    assert chat_mocks["save_message"].await_count == 2


async def test_generation_failure_without_tokens_does_not_save_empty_answer(monkeypatch, chat_mocks):
    async def generate(*args):
        raise RuntimeError("secret provider credential")
        yield "unreachable"

    monkeypatch.setattr(chat_service, "stream_generate", generate)
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", "question")]
    assert b"event: error" in events[-1]
    assert b"secret" not in b"".join(events)
    assert chat_mocks["save_message"].await_count == 1


async def test_invalid_conversation_stops_before_retrieval(chat_mocks):
    chat_mocks["get_or_create_conversation"].side_effect = ValueError("对话不存在或不属于当前 Agent")
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", "question", "other")]
    assert len(events) == 1
    assert b"event: error" in events[0]
    chat_mocks["hybrid_search"].assert_not_awaited()
    chat_mocks["save_message"].assert_not_awaited()


async def test_empty_retrieval_passes_explicit_context_and_empty_citations(monkeypatch, chat_mocks):
    """Verify the context contract, without claiming a real model refuses to answer."""
    received_prompts = []

    async def generate(prompt, history):
        received_prompts.append(prompt)
        yield "mock answer"

    async def capture_prompt(**kwargs):
        return kwargs["context_text"]

    chat_mocks["generate_system_prompt"].side_effect = capture_prompt
    monkeypatch.setattr(chat_service, "stream_generate", generate)
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", "没有对应资料的问题")]
    chat_mocks["generate_system_prompt"].assert_awaited_once_with(
        agent_name="Agent", context_text="暂无相关知识条目。", custom_template=None,
    )
    assert received_prompts == ["暂无相关知识条目。"]
    citation_event = next(event for event in events if event.startswith(b"event: citations\n"))
    assert json.loads(citation_event.decode().split("data: ", 1)[1]) == []
    chat_mocks["save_message"].assert_awaited_with("conversation", "assistant", "mock answer", [])
    assert events[-1].startswith(b"event: done\n")


@pytest.mark.parametrize(
    ("query", "title", "content", "other_error"),
    [
        ("Qwen3-Embedding 向量维度", "Qwen3-Embedding", "Qwen3-Embedding-0.6B 输出 1024 维。", ""),
        ("E_AUTH_401 如何处理", "E_AUTH_401", "E_AUTH_401 表示认证失败，请检查令牌。", "E_CONN_503"),
        ("E_CONN_503 如何处理", "E_CONN_503", "E_CONN_503 表示连接不可用，请检查服务。", "E_AUTH_401"),
    ],
)
async def test_retrieved_terms_keep_context_and_saved_sse_citations_aligned(
    monkeypatch, chat_mocks, query, title, content, other_error,
):
    """Mock retrieval fixtures; exercise context/citation assembly, not search accuracy."""
    chat_mocks["hybrid_search"].return_value = [
        SimpleNamespace(item=SimpleNamespace(title=title, content=content), score=0.812345),
        SimpleNamespace(item=SimpleNamespace(title="补充说明", content="请确认当前配置。"), score=0.654321),
    ]
    received_prompts = []

    async def capture_prompt(**kwargs):
        return kwargs["context_text"]

    async def generate(prompt, history):
        received_prompts.append(prompt)
        yield "mock answer [1][2]"

    chat_mocks["generate_system_prompt"].side_effect = capture_prompt
    monkeypatch.setattr(chat_service, "stream_generate", generate)
    events = [event async for event in chat_service.run_chat_stream("agent", "owner", query)]
    expected_context = f"[1] 标题: {title}\n内容: {content}\n\n[2] 标题: 补充说明\n内容: 请确认当前配置。\n"
    assert received_prompts == [expected_context]
    if other_error:
        assert other_error not in received_prompts[0]
    chat_mocks["hybrid_search"].assert_awaited_once_with(
        knowledge_ids=["item"], query=query, top_k=5, user_id="owner", is_admin=False,
    )
    expected_citations = [
        {"index": 1, "content": content, "knowledge_title": title, "score": 0.8123},
        {"index": 2, "content": "请确认当前配置。", "knowledge_title": "补充说明", "score": 0.6543},
    ]
    citation_event = next(event for event in events if event.startswith(b"event: citations\n"))
    ui_citations = json.loads(citation_event.decode().split("data: ", 1)[1])
    assert ui_citations == expected_citations
    chat_mocks["save_message"].assert_awaited_with(
        "conversation", "assistant", "mock answer [1][2]", ui_citations,
    )
    assert events[-1].startswith(b"event: done\n")
