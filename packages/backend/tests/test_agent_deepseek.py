import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.agent.deepseek import DeepSeekProvider, ProviderError


def chunk(*, content: str | None = None, calls: list[dict[str, Any]] | None = None,
          finish: str | None = None) -> dict[str, Any]:
    return {"choices": [{"index": 0, "delta": {"content": content, "tool_calls": calls}, "finish_reason": finish}]}


class FakeStream:
    def __init__(self, items: list[Any], *, delay: float = 0) -> None:
        self.items = items
        self.delay = delay
        self.closed = False

    def __aiter__(self) -> Any:
        return self._iterate()

    async def _iterate(self) -> Any:
        for item in self.items:
            if self.delay:
                await asyncio.sleep(self.delay)
            if isinstance(item, Exception):
                raise item
            yield item

    async def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, stream: FakeStream) -> None:
        self.stream = stream
        self.kwargs: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs: Any) -> FakeStream:
        self.kwargs = kwargs
        return self.stream


@pytest.mark.asyncio
async def test_non_thinking_and_interleaved_tool_calls() -> None:
    stream = FakeStream([
        {"choices": []},
        chunk(content="thinking ", calls=[
            {"index": 0, "id": "a", "function": {"name": "search", "arguments": '{"q":'}},
            {"index": 1, "id": "b", "function": {"name": "read", "arguments": '{"id":'}},
        ]),
        chunk(content="done", calls=[
            {"index": 1, "function": {"arguments": '"w"}'}},
            {"index": 0, "function": {"arguments": '"x"}'}},
        ]),
        chunk(finish="tool_calls"),
    ])
    client = FakeClient(stream)
    tools = [{"type": "function", "function": {"name": "search", "parameters": {"type": "object"}}}]
    turn = await DeepSeekProvider(client, model="synthetic-model").complete([{"role": "user", "content": "question"}], tools)
    assert client.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert client.kwargs["tools"] == tools
    assert client.kwargs["stream"] is True
    assert turn.text == "thinking done"
    assert [(c.call_id, c.name, c.arguments) for c in turn.tool_calls] == [
        ("a", "search", {"q": "x"}), ("b", "read", {"id": "w"})
    ]
    assert stream.closed


@pytest.mark.asyncio
async def test_text_only_stop_returns_no_tools() -> None:
    stream = FakeStream([chunk(content="hello"), chunk(finish="stop")])
    turn = await DeepSeekProvider(FakeClient(stream), model="synthetic").complete([], [])
    assert turn.text == "hello" and turn.tool_calls == []
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", [None, "length", "stop"])
async def test_incomplete_or_wrong_finish_reason_never_returns_calls(ending: str | None) -> None:
    items = [chunk(calls=[{"index": 0, "id": "a", "function": {"name": "read", "arguments": "{}"}}])]
    if ending is not None:
        items.append(chunk(finish=ending))
    stream = FakeStream(items)
    with pytest.raises(ProviderError):
        await DeepSeekProvider(FakeClient(stream), model="synthetic").complete([], [])
    assert stream.closed


@pytest.mark.asyncio
async def test_upstream_error_is_safe_and_closes_stream() -> None:
    stream = FakeStream([RuntimeError("synthetic-private-provider-error")])
    with pytest.raises(ProviderError) as error:
        await DeepSeekProvider(FakeClient(stream), model="synthetic").complete([], [])
    assert "synthetic-private-provider-error" not in str(error.value)
    assert stream.closed


@pytest.mark.asyncio
async def test_limits_reject_event_flood_and_timeout() -> None:
    stream = FakeStream([{"choices": []}] * 3)
    with pytest.raises(ProviderError):
        await DeepSeekProvider(FakeClient(stream), model="synthetic", max_events=2).complete([], [])
    assert stream.closed
    slow = FakeStream([chunk(finish="stop")], delay=0.1)
    with pytest.raises(ProviderError):
        await DeepSeekProvider(FakeClient(slow), model="synthetic", timeout_seconds=0.01).complete([], [])
    assert slow.closed


@pytest.mark.asyncio
async def test_sdk_chunk_objects_and_post_finish_usage_event() -> None:
    from openai.types.chat import ChatCompletionChunk

    data = {
        "id": "synthetic", "object": "chat.completion.chunk", "created": 1,
        "model": "synthetic", "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
    }
    done = {**data, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
    stream = FakeStream([ChatCompletionChunk.model_validate(data), ChatCompletionChunk.model_validate(done), {"choices": []}])
    turn = await DeepSeekProvider(FakeClient(stream), model="synthetic").complete([], [])
    assert turn.text == "ok" and stream.closed


@pytest.mark.asyncio
async def test_error_after_terminal_never_returns_a_tool_call() -> None:
    stream = FakeStream([
        chunk(calls=[{"index": 0, "id": "a", "function": {"name": "read", "arguments": "{}"}}]),
        chunk(finish="tool_calls"), RuntimeError("simulated private error"),
    ])
    with pytest.raises(ProviderError) as error:
        await DeepSeekProvider(FakeClient(stream), model="synthetic").complete([], [{"type": "function"}])
    assert "simulated private error" not in str(error.value)
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", [
    {"index": False, "delta": {"content": "reply"}, "finish_reason": "stop"},
    {"index": 0, "delta": [], "finish_reason": "stop"},
    {"index": 0, "delta": {}, "finish_reason": "stop"},
])
async def test_rejects_invalid_choice_types_and_empty_stop(choice: dict[str, Any]) -> None:
    stream = FakeStream([{"choices": [choice]}])
    with pytest.raises(ProviderError):
        await DeepSeekProvider(FakeClient(stream), model="synthetic").complete([], [])
    assert stream.closed
