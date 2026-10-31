"""A bounded, injectable DeepSeek streaming provider for agent turns."""

import asyncio
import copy
from contextlib import suppress
from typing import Any

from app.agent.contracts import ModelTurn, ToolRequest
from app.agent.deepseek_stream import ToolCallAccumulator


class ProviderError(Exception):
    """Safe error that does not expose upstream data."""


class DeepSeekProvider:
    def __init__(
        self,
        client: Any,
        *,
        model: str,
        max_events: int = 4096,
        timeout_seconds: float = 120,
        max_text_bytes: int = 262144,
    ) -> None:
        if not model or max_events <= 0 or timeout_seconds <= 0 or max_text_bytes <= 0:
            raise ValueError("invalid provider configuration")
        self._client = client
        self._model = model
        self._max_events = max_events
        self._timeout_seconds = timeout_seconds
        self._max_text_bytes = max_text_bytes

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn:
        stream: Any = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                request: dict[str, Any] = {
                    "model": self._model,
                    "messages": copy.deepcopy(messages),
                    "stream": True,
                    "extra_body": {"thinking": {"type": "disabled"}},
                }
                if tools:
                    request["tools"] = copy.deepcopy(tools)
                stream = await self._client.chat.completions.create(**request)
                accumulator = ToolCallAccumulator()
                text_parts: list[str] = []
                text_bytes = 0
                terminal: str | None = None
                saw_calls = False
                event_count = 0
                async for raw in stream:
                    event_count += 1
                    if event_count > self._max_events:
                        raise ValueError("stream event limit")
                    event = raw if isinstance(raw, dict) else raw.model_dump(exclude_none=True)
                    choices = event.get("choices")
                    if not isinstance(choices, list):
                        raise ValueError("invalid choices")
                    if not choices:
                        continue
                    if len(choices) != 1 or terminal is not None:
                        raise ValueError("invalid choice count or terminal")
                    choice = choices[0]
                    if not isinstance(choice, dict) or type(choice.get("index")) is not int or choice["index"] != 0:
                        raise ValueError("invalid choice")
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        raise ValueError("invalid delta")
                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str):
                            raise ValueError("invalid content")
                        text_bytes += len(content.encode("utf-8"))
                        if text_bytes > self._max_text_bytes:
                            raise ValueError("stream text limit")
                        if content:
                            text_parts.append(content)
                    calls = delta.get("tool_calls")
                    if calls is not None:
                        if not isinstance(calls, list):
                            raise ValueError("invalid calls")
                        saw_calls = saw_calls or bool(calls)
                        accumulator.feed(calls)
                    reason = choice.get("finish_reason")
                    if reason is not None:
                        if reason not in ("stop", "tool_calls"):
                            raise ValueError("incomplete stream")
                        terminal = reason
                if terminal == "tool_calls" and saw_calls and tools:
                    calls_out = accumulator.finish()
                    if not calls_out:
                        raise ValueError("empty tool calls")
                    tool_requests = [ToolRequest(call_id=c.call_id, name=c.name, arguments=c.arguments) for c in calls_out]
                elif terminal == "stop" and not saw_calls and text_parts:
                    tool_requests = []
                else:
                    raise ValueError("incomplete stream")
                return ModelTurn(text="".join(text_parts) or None, tool_calls=tool_requests)
        except Exception:
            raise ProviderError("model stream could not be completed") from None
        finally:
            if stream is not None:
                with suppress(Exception):
                    await asyncio.wait_for(stream.close(), timeout=1)
