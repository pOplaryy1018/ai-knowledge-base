import tracemalloc

import pytest

from app.agent.deepseek_stream import ToolCallAccumulator


def test_interleaved_tool_calls_are_assembled_by_index() -> None:
    accumulator = ToolCallAccumulator()
    accumulator.feed([
        {"index": 0, "id": "call0", "function": {"name": "search", "arguments": '{"query":'}},
        {"index": 1, "id": "call1", "function": {"name": "read", "arguments": '{"id":'}},
    ])
    accumulator.feed([
        {"index": 1, "function": {"arguments": '"w1"}'}},
        {"index": 0, "function": {"arguments": '"rag"}'}},
    ])
    calls = accumulator.finish()
    assert [(c.call_id, c.name, c.arguments) for c in calls] == [
        ("call0", "search", {"query": "rag"}),
        ("call1", "read", {"id": "w1"}),
    ]


@pytest.mark.parametrize(
    "fragment",
    [
        {"index": 0, "id": "x", "function": {"name": "search", "arguments": '{"x":'}},
        {"index": 0, "function": {"name": "search", "arguments": "{}"}},
        {"index": 0, "id": "x", "function": {"arguments": "{}"}},
        {"index": 0, "id": "x", "function": {"name": "search", "arguments": "[]"}},
        {"index": 0, "id": "x", "function": {"name": "search", "arguments": b"\xff"}},
        {"index": 0, "id": "x", "function": {"name": "search", "arguments": '{"a":NaN}'}},
        {"index": 0, "id": "x", "function": {"name": "search", "arguments": '{"a":1,"a":2}'}},
        {"index": 0, "id": "x", "function": {"name": "search", "arguments": '{"a":1e999}'}},
        {"index": 0, "id": "x", "type": "image", "function": {"name": "search", "arguments": "{}"}},
        {"index": 0, "id": "\ud800", "function": {"name": "search", "arguments": "{}"}},
    ],
)
def test_incomplete_invalid_or_non_object_arguments_are_rejected(fragment: dict) -> None:
    accumulator = ToolCallAccumulator()
    with pytest.raises(ValueError):
        accumulator.feed([fragment])
        accumulator.finish()


def test_conflicting_id_for_same_index_rejects_entire_batch() -> None:
    accumulator = ToolCallAccumulator()
    accumulator.feed([{"index": 0, "id": "first", "function": {"name": "search", "arguments": "{}"}}])
    with pytest.raises(ValueError):
        accumulator.feed([{"index": 0, "id": "different"}])
    with pytest.raises(ValueError):
        accumulator.finish()


def test_oversize_arguments_are_rejected_without_exposing_payload() -> None:
    accumulator = ToolCallAccumulator(max_argument_bytes=8)
    with pytest.raises(ValueError) as error:
        accumulator.feed([{"index": 0, "id": "x", "function": {"name": "search", "arguments": '{"x":"private"}'}}])
    assert "private" not in str(error.value)
    with pytest.raises(ValueError):
        accumulator.finish()


def test_empty_delta_has_no_calls() -> None:
    accumulator = ToolCallAccumulator()
    accumulator.feed([])
    assert accumulator.finish() == []


def test_empty_argument_fragments_do_not_cause_unbounded_storage() -> None:
    accumulator = ToolCallAccumulator()
    accumulator.feed([{"index": 0, "id": "x", "function": {"name": "search", "arguments": "{}"}}])
    empty = [{"index": 0, "function": {"arguments": ""}}]
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(50_000):
            accumulator.feed(empty)
        growth = tracemalloc.get_traced_memory()[0] - before
        assert growth < 150_000
    finally:
        tracemalloc.stop()
    assert accumulator.finish()[0].arguments == {}
