"""Bounded model/tool loop; durable event handling is supplied by the caller.

Do not register write tools until durable operation tracking, confirmation,
and cancellation recovery are integrated by the task execution layer.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.agent.contracts import ModelTurn, RuntimeContext, ToolRequest, ToolResult


class Provider(Protocol):
    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn: ...


class Registry(Protocol):
    def definitions(self) -> list[dict[str, Any]]: ...
    async def invoke(self, context: RuntimeContext, request: ToolRequest) -> ToolResult: ...


@dataclass(frozen=True)
class RuntimeEvent:
    """Safe progress only; consumers must persist before publishing externally."""

    type: str


@dataclass(frozen=True)
class RuntimeResult:
    status: Literal["completed", "failed", "limit_reached"]
    answer: str | None = None


class AgentRuntime:
    def __init__(
        self,
        *,
        provider: Provider,
        registry: Registry,
        max_model_calls: int = 12,
        max_tool_calls: int = 30,
        timeout_seconds: float = 600,
    ) -> None:
        if max_model_calls <= 0 or max_tool_calls <= 0 or timeout_seconds <= 0:
            raise ValueError("invalid runtime limits")
        self._provider = provider
        self._registry = registry
        self._max_model_calls = max_model_calls
        self._max_tool_calls = max_tool_calls
        self._timeout_seconds = timeout_seconds

    async def run(self, context: RuntimeContext, question: str, emit: Any = None) -> RuntimeResult:
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        model_calls = 0
        tool_calls = 0
        seen_ids: set[str] = set()

        async def progress(event: RuntimeEvent) -> None:
            if emit is not None:
                await emit(event)

        deadline = asyncio.timeout(self._timeout_seconds)
        try:
            async with deadline:
                while model_calls < self._max_model_calls:
                    model_calls += 1
                    turn = await self._provider.complete(messages, self._registry.definitions())
                    if not turn.tool_calls:
                        if not turn.text:
                            return RuntimeResult("failed")
                        await progress(RuntimeEvent("completed"))
                        return RuntimeResult("completed", turn.text)
                    if tool_calls + len(turn.tool_calls) > self._max_tool_calls:
                        return RuntimeResult("limit_reached")
                    ids = [call.call_id for call in turn.tool_calls]
                    if len(set(ids)) != len(ids) or any(not value or value in seen_ids for value in ids):
                        return RuntimeResult("failed")
                    seen_ids.update(ids)
                    messages.append({
                        "role": "assistant", "content": turn.text,
                        "tool_calls": [
                            {"id": call.call_id, "type": "function", "function": {
                                "name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False,
                                                                          allow_nan=False),
                            }} for call in turn.tool_calls
                        ],
                    })
                    for call in turn.tool_calls:
                        tool_calls += 1
                        await progress(RuntimeEvent("tool_started"))
                        result = await self._registry.invoke(context, call)
                        if result.call_id != call.call_id:
                            return RuntimeResult("failed")
                        messages.append({"role": "tool", "tool_call_id": call.call_id,
                                         "content": result.model_dump_json()})
                        await progress(RuntimeEvent("tool_finished"))
        except TimeoutError:
            return RuntimeResult("limit_reached" if deadline.expired() else "failed")
        except Exception:
            return RuntimeResult("failed")
        return RuntimeResult("limit_reached")
