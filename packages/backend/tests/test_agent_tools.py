import asyncio
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.agent.contracts import RuntimeContext, ToolRequest
from app.agent.tools import ToolRegistry


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    limit: int = 5


def context() -> RuntimeContext:
    return RuntimeContext(owner_id="owner", task_id="task", source_versions={})


@pytest.mark.asyncio
async def test_valid_invoke_uses_trusted_context() -> None:
    observed: list[tuple[str, str]] = []

    async def search(ctx: RuntimeContext, args: SearchArgs) -> dict[str, Any]:
        observed.append((ctx.owner_id, args.query))
        return {"items": [args.query]}

    registry = ToolRegistry()
    registry.register("search", SearchArgs, search)
    result = await registry.invoke(context(), ToolRequest(call_id="1", name="search", arguments={"query": "rag"}))
    assert result.ok and result.data == {"items": ["rag"]} and result.call_id == "1"
    assert observed == [("owner", "rag")]


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [
    {"query": "rag", "owner_id": "another"},
    {"query": "rag", "is_admin": True},
    {"query": "rag", "nested": {"owner_id": "another"}},
    {"query": "rag", "limit": "3"},
    {"query": "rag", "extra": "private-value"},
])
async def test_invalid_arguments_cannot_call_handler(args: dict[str, Any]) -> None:
    calls: list[str] = []

    async def search(ctx: RuntimeContext, data: SearchArgs) -> dict[str, Any]:
        calls.append(data.query)
        return {}

    registry = ToolRegistry()
    registry.register("search", SearchArgs, search)
    result = await registry.invoke(context(), ToolRequest(call_id="1", name="search", arguments=args))
    assert not result.ok and result.error == "invalid_arguments" and not calls
    assert "private-value" not in str(result)


@pytest.mark.asyncio
async def test_unknown_tool_never_calls_handler() -> None:
    registry = ToolRegistry()
    result = await registry.invoke(context(), ToolRequest(call_id="1", name="unknown", arguments={}))
    assert not result.ok and result.error == "unknown_tool"


@pytest.mark.asyncio
async def test_mutated_arguments_are_revalidated_at_execution_boundary() -> None:
    called = False

    async def search(ctx: RuntimeContext, data: SearchArgs) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    registry = ToolRegistry()
    registry.register("search", SearchArgs, search)
    request = ToolRequest(call_id="1", name="search", arguments={"query": "rag"})
    request.arguments["limit"] = float("nan")
    result = await registry.invoke(context(), request)
    assert not result.ok and result.error == "invalid_arguments" and not called


@pytest.mark.asyncio
async def test_input_is_copied_before_handler_awaits() -> None:
    started, proceed = asyncio.Event(), asyncio.Event()

    async def search(ctx: RuntimeContext, data: SearchArgs) -> dict[str, Any]:
        started.set()
        await proceed.wait()
        return {"query": data.query}

    registry = ToolRegistry()
    registry.register("search", SearchArgs, search)
    request = ToolRequest(call_id="1", name="search", arguments={"query": "original"})
    task = asyncio.create_task(registry.invoke(context(), request))
    await started.wait()
    request.arguments["query"] = "changed"
    proceed.set()
    assert (await task).data == {"query": "original"}


@pytest.mark.asyncio
async def test_handler_exception_is_safe() -> None:
    async def failing(ctx: RuntimeContext, data: SearchArgs) -> dict[str, Any]:
        raise RuntimeError("private-exception")

    registry = ToolRegistry()
    registry.register("search", SearchArgs, failing)
    result = await registry.invoke(context(), ToolRequest(call_id="1", name="search", arguments={"query": "private-input"}))
    assert not result.ok and result.error == "tool_failed"
    assert "private" not in str(result)


def test_registration_rejects_non_forbid_schema_and_duplicate_name() -> None:
    class UnsafeArgs(BaseModel):
        query: str

    async def search(ctx: RuntimeContext, data: Any) -> dict[str, Any]:
        return {}

    registry = ToolRegistry()
    with pytest.raises(ValueError):
        registry.register("unsafe", UnsafeArgs, search)
    registry.register("search", SearchArgs, search)
    with pytest.raises(ValueError):
        registry.register("search", SearchArgs, search)


def test_registration_rejects_schema_exposing_owner_even_if_aliased() -> None:
    from pydantic import Field

    class UnsafeOwner(BaseModel):
        model_config = ConfigDict(extra="forbid")
        owner_id: str = Field(alias="who")

    async def search(ctx: RuntimeContext, data: UnsafeOwner) -> dict[str, Any]:
        return {}

    with pytest.raises(ValueError):
        ToolRegistry().register("unsafe", UnsafeOwner, search)


def test_registration_rejects_hidden_identity_in_nested_union_and_list() -> None:
    from pydantic import Field

    class Nested(BaseModel):
        model_config = ConfigDict(extra="forbid")
        owner_id: str = Field(alias="who", exclude=True)

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        nested: list[Nested] | None

    async def handler(ctx: RuntimeContext, data: Outer) -> dict[str, Any]:
        return {"seen": data.nested[0].owner_id if data.nested else ""}

    with pytest.raises(ValueError):
        ToolRegistry().register("unsafe", Outer, handler)


def test_registration_rejects_nested_model_that_allows_extra_fields() -> None:
    class Nested(BaseModel):
        name: str

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        nested: Nested

    async def handler(ctx: RuntimeContext, data: Outer) -> dict[str, Any]:
        return {}

    with pytest.raises(ValueError):
        ToolRegistry().register("unsafe", Outer, handler)


@pytest.mark.asyncio
async def test_safe_recursive_model_registration_and_invoke() -> None:
    class Node(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str
        children: list["Node"] = []

    Node.model_rebuild()

    async def handler(ctx: RuntimeContext, data: Node) -> dict[str, Any]:
        return {"child": data.children[0].name}

    registry = ToolRegistry()
    registry.register("recursive", Node, handler)
    result = await registry.invoke(
        context(), ToolRequest(call_id="1", name="recursive", arguments={"name": "root", "children": [{"name": "leaf"}]}),
    )
    assert result.ok and result.data == {"child": "leaf"}


def test_registration_rejects_identity_hidden_in_newtype() -> None:
    from typing import NewType

    from pydantic import Field

    class Nested(BaseModel):
        model_config = ConfigDict(extra="forbid")
        owner_id: str = Field(alias="who", exclude=True)

    Hidden = NewType("Hidden", Nested)

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        nested: Hidden

    async def handler(ctx: RuntimeContext, data: Outer) -> dict[str, Any]:
        return {"seen": data.nested.owner_id}

    with pytest.raises(ValueError):
        ToolRegistry().register("unsafe", Outer, handler)


@pytest.mark.asyncio
async def test_safe_newtype_model_remains_usable() -> None:
    from typing import NewType

    class Nested(BaseModel):
        model_config = ConfigDict(extra="forbid")
        query: str

    Safe = NewType("Safe", Nested)

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        nested: Safe

    async def handler(ctx: RuntimeContext, data: Outer) -> dict[str, Any]:
        return {"query": data.nested.query}

    registry = ToolRegistry()
    registry.register("safe", Outer, handler)
    result = await registry.invoke(
        context(), ToolRequest(call_id="1", name="safe", arguments={"nested": {"query": "rag"}}),
    )
    assert result.ok and result.data == {"query": "rag"}


def test_registration_rejects_uninspected_typed_dict_identity() -> None:
    from typing import Annotated

    from pydantic import Field
    from typing_extensions import TypedDict

    class Nested(TypedDict):
        owner_id: Annotated[str, Field(alias="who", exclude=True)]

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        nested: Nested

    async def handler(ctx: RuntimeContext, data: Outer) -> dict[str, Any]:
        return {}

    with pytest.raises(ValueError):
        ToolRegistry().register("unsafe", Outer, handler)


@pytest.mark.asyncio
async def test_validator_cannot_hide_identity_inside_excluded_model() -> None:
    from pydantic import Field, field_validator

    class Hidden(BaseModel):
        owner_id: str = Field(exclude=True)

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        nested: Any

        @field_validator("nested")
        @classmethod
        def to_hidden(cls, value: Any) -> Hidden:
            return Hidden(owner_id=value["who"])

    called = False

    async def handler(ctx: RuntimeContext, data: Outer) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    registry = ToolRegistry()
    registry.register("guarded", Outer, handler)
    result = await registry.invoke(
        context(), ToolRequest(call_id="1", name="guarded", arguments={"nested": {"who": "other"}}),
    )
    assert not result.ok and result.error == "invalid_arguments" and not called


@pytest.mark.asyncio
@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("origin", ["default", "validator"])
async def test_nonfinite_values_generated_by_schema_cannot_reach_handler(number: float, origin: str) -> None:
    from pydantic import field_validator

    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: float = number if origin == "default" else 1.0

        @field_validator("value")
        @classmethod
        def produce_invalid(cls, value: float) -> float:
            return number if origin == "validator" else value

    called = False

    async def handler(ctx: RuntimeContext, data: Args) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    registry = ToolRegistry()
    registry.register("numeric", Args, handler)
    arguments = {} if origin == "default" else {"value": 1.0}
    result = await registry.invoke(context(), ToolRequest(call_id="1", name="numeric", arguments=arguments))
    assert not result.ok and result.error == "invalid_arguments" and not called
