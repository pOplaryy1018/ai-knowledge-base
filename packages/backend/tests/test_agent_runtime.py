import asyncio
import json

import pytest
from pydantic import BaseModel, ConfigDict

from app.agent.contracts import ModelTurn, RuntimeContext, ToolRequest
from app.agent.runtime import AgentRuntime
from app.agent.tools import ToolRegistry


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str


def context() -> RuntimeContext:
    return RuntimeContext(owner_id="owner", task_id="task", source_versions={})


async def test_model_tool_result_model_final() -> None:
    calls = []

    async def search(ctx: RuntimeContext, args: SearchArgs) -> dict:
        calls.append((ctx.owner_id, args.query))
        return {"items": ["evidence"]}

    registry = ToolRegistry()
    registry.register("search_sources", SearchArgs, search)

    class Provider:
        async def complete(self, messages, tools):
            assert tools[0]["function"]["name"] == "search_sources"
            if len(messages) == 1:
                return ModelTurn(tool_calls=[ToolRequest(call_id="c1", name="search_sources", arguments={"query": "rag"})])
            assert messages[-2]["role"] == "assistant"
            assert messages[-2]["tool_calls"][0]["id"] == "c1"
            assert messages[-1]["role"] == "tool"
            assert messages[-1]["tool_call_id"] == "c1"
            assert json.loads(messages[-1]["content"])["data"] == {"items": ["evidence"]}
            return ModelTurn(text="answer")

    events = []

    async def emit(event):
        events.append(event)

    result = await AgentRuntime(provider=Provider(), registry=registry).run(context(), "what?", emit)
    assert (result.status, result.answer) == ("completed", "answer")
    assert calls == [("owner", "rag")]
    assert [event.type for event in events] == ["tool_started", "tool_finished", "completed"]
    assert "evidence" not in repr(events)


async def test_model_limit_stops_before_extra_call() -> None:
    class Provider:
        calls = 0

        async def complete(self, messages, tools):
            self.calls += 1
            return ModelTurn(tool_calls=[ToolRequest(call_id=f"c{self.calls}", name="x", arguments={})])

    class Registry:
        def definitions(self):
            return []

        async def invoke(self, ctx, request):
            from app.agent.contracts import ToolResult
            return ToolResult(call_id=request.call_id, ok=True, data={})

    provider = Provider()
    result = await AgentRuntime(provider=provider, registry=Registry(), max_model_calls=1).run(context(), "q")
    assert result.status == "limit_reached"
    assert provider.calls == 1


async def test_tool_limit_prevents_partial_batch() -> None:
    class Provider:
        async def complete(self, messages, tools):
            return ModelTurn(tool_calls=[
                ToolRequest(call_id="a", name="x", arguments={}),
                ToolRequest(call_id="b", name="x", arguments={}),
            ])

    class Registry:
        count = 0

        def definitions(self):
            return []

        async def invoke(self, ctx, request):
            self.count += 1

    registry = Registry()
    result = await AgentRuntime(provider=Provider(), registry=registry, max_tool_calls=1).run(context(), "q")
    assert result.status == "limit_reached"
    assert registry.count == 0


async def test_timeout_and_provider_error_are_safe() -> None:
    class Provider:
        async def complete(self, messages, tools):
            await asyncio.sleep(1)
            raise RuntimeError("private details")

    result = await AgentRuntime(provider=Provider(), registry=ToolRegistry(), timeout_seconds=0.01).run(context(), "q")
    assert result.status == "limit_reached"
    assert "private details" not in repr(result)


async def test_cancellation_propagates() -> None:
    class Provider:
        async def complete(self, messages, tools):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await AgentRuntime(provider=Provider(), registry=ToolRegistry()).run(context(), "q")


async def test_multiple_calls_preserve_ids_without_exposing_them_in_events() -> None:
    class Provider:
        async def complete(self, messages, tools):
            if len(messages) == 1:
                return ModelTurn(tool_calls=[
                    ToolRequest(call_id="private-id-1", name="x", arguments={}),
                    ToolRequest(call_id="private-id-2", name="x", arguments={}),
                ])
            assert [m["tool_call_id"] for m in messages[-2:]] == ["private-id-1", "private-id-2"]
            return ModelTurn(text="done")

    class Registry:
        def definitions(self):
            return []

        async def invoke(self, ctx, request):
            from app.agent.contracts import ToolResult
            return ToolResult(call_id=request.call_id, ok=True, data={})

    events = []

    async def emit(event):
        events.append(event)

    result = await AgentRuntime(provider=Provider(), registry=Registry()).run(context(), "q", emit)
    assert result.status == "completed"
    assert "private-id" not in repr(events)


async def test_provider_error_and_its_timeout_are_not_runtime_budget_exhaustion() -> None:
    class Provider:
        async def complete(self, messages, tools):
            raise TimeoutError("secret")

    result = await AgentRuntime(provider=Provider(), registry=ToolRegistry()).run(context(), "q")
    assert result.status == "failed"
    assert "secret" not in repr(result)


async def test_untrusted_identity_argument_is_rejected_by_real_registry() -> None:
    calls = []

    async def search(ctx: RuntimeContext, args: SearchArgs) -> dict:
        calls.append(ctx.owner_id)
        return {}

    registry = ToolRegistry()
    registry.register("search", SearchArgs, search)

    class Provider:
        async def complete(self, messages, tools):
            if len(messages) == 1:
                return ModelTurn(tool_calls=[ToolRequest(
                    call_id="c1", name="search", arguments={"query": "q", "owner_id": "other"},
                )])
            assert json.loads(messages[-1]["content"])["error"] == "invalid_arguments"
            return ModelTurn(text="cannot search")

    result = await AgentRuntime(provider=Provider(), registry=registry).run(context(), "q")
    assert result.status == "completed"
    assert calls == []


async def test_event_sink_failure_is_not_reported_as_completed() -> None:
    class Provider:
        async def complete(self, messages, tools):
            return ModelTurn(text="answer")

    async def emit(event):
        raise RuntimeError("sensitive exception")

    result = await AgentRuntime(provider=Provider(), registry=ToolRegistry()).run(context(), "q", emit)
    assert result.status == "failed"
    assert result.answer is None
    assert "sensitive exception" not in repr(result)
