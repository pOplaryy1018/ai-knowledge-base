"""Internal MCP bridge for one already authenticated, immutable task context.

No network route is registered here. The caller must authenticate the user,
construct the task snapshot and connect the client to this specific server.
The binding digest prevents accidental task/session mixups; it is not a token
or a replacement for JWT authentication and transport access controls.
"""

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from copy import deepcopy
from typing import Any

from mcp import ClientSession, types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.contracts import RuntimeContext, ToolRequest, ToolResult
from app.agent.source_tools import register_source_tools
from app.agent.tools import ToolRegistry


def _binding(context: RuntimeContext) -> str:
    payload = json.dumps(context.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_source_mcp_server(
    context: RuntimeContext, session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> Server[Any]:
    if not isinstance(context, RuntimeContext) or not callable(session_factory):
        raise ValueError("trusted task context required")
    registry = ToolRegistry()
    register_source_tools(registry, session_factory)
    binding = _binding(context)

    async def list_tools(_ctx: ServerRequestContext[Any], _params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        tools = [types.Tool(name=definition["function"]["name"],
                            input_schema=definition["function"]["parameters"],
                            annotations=types.ToolAnnotations(read_only_hint=True, destructive_hint=False))
                 for definition in registry.definitions()]
        return types.ListToolsResult(tools=tools, _meta={"task_binding": binding})

    async def call_tool(_ctx: ServerRequestContext[Any], params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            request = ToolRequest(call_id="mcp", name=params.name, arguments=params.arguments or {})
            result = await registry.invoke(context, request)
            payload = result.model_dump(mode="json", exclude={"call_id"})
        except Exception:
            payload = {"ok": False, "data": None, "error": "tool_failed"}
        return types.CallToolResult(content=[types.TextContent(text=json.dumps(payload, ensure_ascii=False))],
                                    structured_content=payload, is_error=not payload["ok"])

    return Server("knowledge-source-tools", on_list_tools=list_tools, on_call_tool=call_tool)


class MCPRegistry:
    """Adapt an already connected internal MCP client to the Agent runtime."""

    def __init__(self, client: ClientSession, context: RuntimeContext, tools: list[types.Tool]) -> None:
        self._client = client
        self._binding = _binding(context)
        self._definitions = [{"type": "function", "function": {"name": tool.name,
                               "parameters": tool.input_schema}} for tool in tools]

    @classmethod
    async def create(cls, client: ClientSession, context: RuntimeContext) -> "MCPRegistry":
        tools = await client.list_tools()
        if tools.meta is None or tools.meta.get("task_binding") != _binding(context) or tools.next_cursor is not None:
            raise ValueError("MCP task context mismatch")
        return cls(client, context, tools.tools)

    def definitions(self) -> list[dict[str, Any]]:
        return deepcopy(self._definitions)

    async def invoke(self, context: RuntimeContext, request: ToolRequest) -> ToolResult:
        if _binding(context) != self._binding:
            return ToolResult(call_id=request.call_id, ok=False, error="invalid_context")
        try:
            result = await self._client.call_tool(request.name, request.arguments)
            if not isinstance(result, types.CallToolResult) or not isinstance(result.structured_content, dict):
                raise ValueError("invalid MCP result")
            payload = dict(result.structured_content)
            payload["call_id"] = request.call_id
            parsed = ToolResult.model_validate(payload, strict=True)
            if parsed.ok == result.is_error:
                raise ValueError("inconsistent MCP result")
            return parsed
        except Exception:
            return ToolResult(call_id=request.call_id, ok=False, error="tool_failed")
