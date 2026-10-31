import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agent.contracts import ModelTurn, RuntimeContext, TaskEvent, ToolRequest, ToolResult


@pytest.mark.parametrize("extra", [{"owner_id": "other"}, {"is_admin": True}, {"unknown": 1}])
def test_tool_request_rejects_untrusted_identity_and_extra_fields(extra: dict) -> None:
    with pytest.raises(ValidationError):
        ToolRequest.model_validate({"call_id": "c1", "name": "search", "arguments": {}, **extra})


def test_runtime_context_holds_server_supplied_snapshot() -> None:
    context = RuntimeContext(owner_id="owner", task_id="task", source_versions={"source": "v1"})
    assert context.owner_id == "owner"
    assert context.task_id == "task"
    assert context.source_versions == {"source": "v1"}


def test_tool_result_and_model_turn_are_serializable() -> None:
    call = ToolRequest(call_id="c1", name="search", arguments={"query": "RAG"})
    turn = ModelTurn(text="hello", tool_calls=[call])
    result = ToolResult(call_id="c1", ok=True, data={"items": ["a"]})
    assert json.loads(turn.model_dump_json())["tool_calls"][0]["call_id"] == "c1"
    assert json.loads(result.model_dump_json())["data"] == {"items": ["a"]}


def test_model_turn_default_tool_calls_are_independent() -> None:
    first = ModelTurn(text="first")
    second = ModelTurn(text="second")
    first.tool_calls.append(ToolRequest(call_id="c1", name="search", arguments={}))
    assert second.tool_calls == []


def test_task_event_has_positive_sequence_and_json_payload() -> None:
    event = TaskEvent(
        task_id="task", seq=1, type="started", payload={"step": 1},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert json.loads(event.model_dump_json())["payload"] == {"step": 1}
    with pytest.raises(ValidationError):
        TaskEvent(task_id="task", seq=0, type="started", payload={}, created_at=event.created_at)
    with pytest.raises(ValidationError):
        TaskEvent(task_id="task", seq=2, type="started", payload={"bad": object()}, created_at=event.created_at)


def test_runtime_context_snapshot_cannot_be_mutated_and_serializes() -> None:
    original = {"source": "v1"}
    context = RuntimeContext(owner_id="owner", task_id="task", source_versions=original)
    original["source"] = "v2"
    assert context.source_versions["source"] == "v1"
    with pytest.raises(TypeError):
        context.source_versions["source"] = "v3"
    with pytest.raises(ValidationError):
        context.source_versions = {"source": "v4"}
    assert json.loads(context.model_dump_json())["source_versions"] == {"source": "v1"}


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("kind", ["request", "result", "event"])
def test_nested_json_rejects_nonfinite_numbers(kind: str, number: float) -> None:
    nested = {"nested": [{"bad": number}]}
    with pytest.raises(ValidationError):
        if kind == "request":
            ToolRequest(call_id="c", name="search", arguments=nested)
        elif kind == "result":
            ToolResult(call_id="c", ok=True, data=nested)
        else:
            TaskEvent(task_id="task", seq=1, type="started", payload=nested,
                      created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize("kind", ["request", "result", "event"])
@pytest.mark.parametrize("as_json", [False, True])
def test_mutated_nested_json_rejects_nonfinite_at_serialization(kind: str, as_json: bool) -> None:
    nested = {"nested": [{"value": 1.0}]}
    if kind == "request":
        model = ToolRequest(call_id="c", name="search", arguments=nested)
        target = model.arguments
    elif kind == "result":
        model = ToolResult(call_id="c", ok=True, data=nested)
        assert model.data is not None
        target = model.data
    else:
        model = TaskEvent(task_id="task", seq=1, type="started", payload=nested,
                          created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        target = model.payload
    target["nested"][0]["value"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        if as_json:
            model.model_dump_json()
        else:
            model.model_dump()
