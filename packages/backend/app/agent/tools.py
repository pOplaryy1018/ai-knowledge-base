"""In-process registry with trusted runtime context and validated arguments."""

import copy
import math
import types
from collections.abc import Awaitable, Callable
from typing import Any, Literal, NewType, Union, get_args, get_origin

from pydantic import AliasChoices, AliasPath, BaseModel

from app.agent.contracts import RuntimeContext, ToolRequest, ToolResult

_RESERVED_ARGUMENTS = frozenset({"owner", "owner_id", "is_admin"})


def _contains_reserved(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in _RESERVED_ARGUMENTS or _contains_reserved(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_reserved(item) for item in value)
    return False


def _reserved_alias(alias: Any) -> bool:
    if isinstance(alias, str):
        return alias in _RESERVED_ARGUMENTS
    if isinstance(alias, AliasPath):
        return any(_reserved_alias(part) for part in alias.path)
    if isinstance(alias, AliasChoices):
        return any(_reserved_alias(choice) for choice in alias.choices)
    return False


def _schema_is_safe(annotation: Any, visited: set[type[BaseModel]]) -> bool:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in visited:
            return True
        visited.add(annotation)
        if not annotation.__pydantic_complete__ or annotation.model_config.get("extra") != "forbid":
            return False
        for name, field in annotation.model_fields.items():
            if (name in _RESERVED_ARGUMENTS or _reserved_alias(field.alias)
                    or _reserved_alias(field.validation_alias) or _reserved_alias(field.serialization_alias)):
                return False
            if not _schema_is_safe(field.annotation, visited):
                return False
        return True
    if isinstance(annotation, NewType):
        return _schema_is_safe(annotation.__supertype__, visited)
    if annotation in (Any, str, int, float, bool, type(None)):
        return True
    origin = get_origin(annotation)
    if origin is Literal:
        return all(type(value) in (str, int, float, bool, type(None)) for value in get_args(annotation))
    if origin in (Union, types.UnionType, list, dict, tuple):
        return all(arg is Ellipsis or _schema_is_safe(arg, visited) for arg in get_args(annotation))
    # Unsupported classes, unresolved references and uninspected wrappers fail closed.
    return False


def _validated_values_are_safe(value: Any) -> bool:
    """Inspect actual fields, including excluded ones, with bounded traversal."""
    remaining = 10_000
    active: set[int] = set()

    def check(item: Any, depth: int) -> bool:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 64:
            return False
        if type(item) is float:
            return math.isfinite(item)
        if item is None or type(item) in (str, int, bool):
            return True
        if not isinstance(item, (BaseModel, dict, list, tuple)):
            return False
        identity = id(item)
        if identity in active:
            return False
        active.add(identity)
        try:
            if isinstance(item, BaseModel):
                return all(
                    name not in _RESERVED_ARGUMENTS and check(getattr(item, name), depth + 1)
                    for name in type(item).model_fields
                )
            if isinstance(item, dict):
                return all(isinstance(key, str) and key not in _RESERVED_ARGUMENTS and check(child, depth + 1)
                           for key, child in item.items())
            return all(check(child, depth + 1) for child in item)
        finally:
            active.remove(identity)

    return check(value, 0)


class ToolRegistry:
    """Tools obtain authorization context only from their trusted caller."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[type[BaseModel], Callable[..., Awaitable[dict[str, Any]]]]] = {}

    def register(
        self,
        name: str,
        schema: type[BaseModel],
        handler: Callable[..., Awaitable[dict[str, Any]]],
    ) -> None:
        if not name or name in self._tools or not issubclass(schema, BaseModel):
            raise ValueError("invalid tool registration")
        if not callable(handler) or not _schema_is_safe(schema, set()):
            raise ValueError("invalid tool registration")
        self._tools[name] = (schema, handler)

    async def invoke(self, context: RuntimeContext, request: ToolRequest) -> ToolResult:
        call_id = request.call_id if isinstance(request.call_id, str) else ""
        try:
            checked = ToolRequest.model_validate({
                "call_id": request.call_id,
                "name": request.name,
                "arguments": copy.deepcopy(request.arguments),
            }, strict=True)
            call_id = checked.call_id
        except Exception:
            return ToolResult(call_id=call_id, ok=False, error="invalid_arguments")
        tool = self._tools.get(checked.name)
        if tool is None:
            return ToolResult(call_id=call_id, ok=False, error="unknown_tool")
        schema, handler = tool
        try:
            if _contains_reserved(checked.arguments):
                raise ValueError("reserved arguments")
            arguments = schema.model_validate(checked.arguments, strict=True)
            if not _validated_values_are_safe(arguments):
                raise ValueError("reserved arguments")
        except Exception:
            return ToolResult(call_id=call_id, ok=False, error="invalid_arguments")
        try:
            data = await handler(context, arguments)
            return ToolResult(call_id=call_id, ok=True, data=data)
        except Exception:
            return ToolResult(call_id=call_id, ok=False, error="tool_failed")
