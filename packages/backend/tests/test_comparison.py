"""Grounded comparison contract and retrieval tests."""
import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.schemas.comparison import ComparisonDraft
from app.services.comparison_service import (
    build_comparison,
    generate_comparison,
    prepare_comparison_evidence,
)


def evidence():
    return [
        {"index": 1, "source_id": "a", "revision_id": "va", "content": "A支持事务", "knowledge_title": "A"},
        {"index": 2, "source_id": "b", "revision_id": "vb", "content": "B不支持事务", "knowledge_title": "B"},
    ]


def draft():
    return {"rows": [{"dimension": "事务", "cells": [
        {"source_id": "a", "text": "支持事务", "citation_indices": [1]},
        {"source_id": "b", "text": "不支持事务", "citation_indices": [2]},
    ]}]}


def test_build_grounded_comparison_and_readable_fallback():
    artifact, content, citations = build_comparison(json.dumps(draft()), {"a": "A", "b": "B"}, evidence())
    assert artifact["kind"] == "source_comparison"
    assert artifact["rows"][0]["cells"][0]["citation_indices"] == [1]
    assert "支持事务[1]" in content
    assert citations == evidence()
    assert "content" not in artifact["sources"][0]


@pytest.mark.parametrize("mutation", ["foreign_reference", "unknown_reference", "unknown_source", "duplicate_cell", "duplicate_dimension", "extra_field", "boolean_reference"])
def test_rejects_untrusted_comparison(mutation):
    data = draft()
    cell = data["rows"][0]["cells"][0]
    if mutation == "foreign_reference":
        cell["citation_indices"] = [2]
    elif mutation == "unknown_reference":
        cell["citation_indices"] = [99]
    elif mutation == "unknown_source":
        cell["source_id"] = "foreign"
    elif mutation == "duplicate_cell":
        data["rows"][0]["cells"].append(dict(cell))
    elif mutation == "duplicate_dimension":
        data["rows"].append(data["rows"][0])
    elif mutation == "extra_field":
        data["html"] = "<script>alert(1)</script>"
    else:
        cell["citation_indices"] = [True]
    with pytest.raises(ValueError):
        build_comparison(json.dumps(data), {"a": "A", "b": "B"}, evidence())


def test_missing_or_uncited_cell_becomes_explicit_insufficient():
    data = draft()
    data["rows"][0]["cells"] = [{"source_id": "a", "text": "模型无依据结论", "citation_indices": []}]
    artifact, content, citations = build_comparison(json.dumps(data), {"a": "A", "b": "B"}, evidence())
    assert all(cell["text"] == "未找到依据" for cell in artifact["rows"][0]["cells"])
    assert "模型无依据" not in content
    assert citations == []


def test_protocol_bounds():
    with pytest.raises(ValidationError):
        ComparisonDraft.model_validate({"rows": []})
    with pytest.raises(ValueError):
        build_comparison("x" * 40001, {"a": "A", "b": "B"}, evidence())


async def test_retrieves_each_source_and_reindexes(monkeypatch):
    from app.services import comparison_service as service
    retrieve = AsyncMock(side_effect=[[evidence()[0]], [], [evidence()[1]]])
    monkeypatch.setattr(service, "prepare_evidence", retrieve)
    monkeypatch.setattr(service, "encode_texts", AsyncMock(return_value=[0.0]), raising=False)
    result = await prepare_comparison_evidence("事务", {"a": "va", "c": "vc", "b": "vb"}, "owner")
    assert [entry["index"] for entry in result] == [1, 2]
    assert [call.args[1] for call in retrieve.call_args_list] == [{"a": "va"}, {"c": "vc"}, {"b": "vb"}]


async def test_comparison_shares_one_embedding_and_runs_sources_concurrently(monkeypatch):
    import asyncio

    from app.services import comparison_service as service

    started = []
    both_started = asyncio.Event()
    calls = 0

    async def encode(_question):
        nonlocal calls
        calls += 1
        await asyncio.wait_for(both_started.wait(), timeout=2)
        return [0.0]

    async def retrieve(_question, versions, _user, *, embedding_task=None):
        assert embedding_task is not None
        started.append(next(iter(versions)))
        if len(started) == 2:
            both_started.set()
        await embedding_task
        return [{"source_id": next(iter(versions)), "index": 99}]

    monkeypatch.setattr(service, "encode_texts", encode, raising=False)
    monkeypatch.setattr(service, "prepare_evidence", retrieve)
    result = await asyncio.wait_for(prepare_comparison_evidence("问题", {"a": "va", "b": "vb"}, "owner"), timeout=3)
    assert calls == 1
    assert [(entry["source_id"], entry["index"]) for entry in result] == [("a", 1), ("b", 2)]


async def test_comparison_cancellation_drains_shared_embedding_and_sources(monkeypatch):
    import asyncio

    from app.services import comparison_service as service

    both_started = asyncio.Event()
    embedding_done = asyncio.Event()
    source_done = []
    started = []

    async def encode(_question):
        try:
            await asyncio.Event().wait()
        finally:
            embedding_done.set()

    async def retrieve(_question, versions, _user, *, embedding_task=None):
        source_id = next(iter(versions))
        started.append(source_id)
        if len(started) == 2:
            both_started.set()
        try:
            await asyncio.shield(embedding_task)
        finally:
            source_done.append(source_id)
        return []

    monkeypatch.setattr(service, "encode_texts", encode)
    monkeypatch.setattr(service, "prepare_evidence", retrieve)
    task = asyncio.create_task(prepare_comparison_evidence("问题", {"a": "va", "b": "vb"}, "owner"))
    await asyncio.wait_for(both_started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert embedding_done.is_set() and set(source_done) == {"a", "b"}


async def test_comparison_bounds_concurrent_source_retrieval(monkeypatch):
    import asyncio

    from app.services import comparison_service as service

    active = 0
    maximum = 0

    async def retrieve(_question, versions, _user, *, embedding_task=None):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.01)
            return [{"source_id": next(iter(versions)), "index": 99}]
        finally:
            active -= 1

    monkeypatch.setattr(service, "encode_texts", AsyncMock(return_value=[0.0]))
    monkeypatch.setattr(service, "prepare_evidence", retrieve)
    result = await prepare_comparison_evidence("问题", {"a": "va", "b": "vb", "c": "vc", "d": "vd"}, "owner")
    assert maximum == 2
    assert [entry["source_id"] for entry in result] == ["a", "b", "c", "d"]


async def test_generation_without_evidence_skips_provider(monkeypatch):
    from app.services import comparison_service as service
    monkeypatch.setattr(service, "prepare_comparison_evidence", AsyncMock(return_value=[]))
    provider = AsyncMock()
    monkeypatch.setattr(service, "stream_generate", provider)
    content, citations, artifact, warning = await generate_comparison("事务", {"a": "va", "b": "vb"}, "owner", {"a": "A", "b": "B"})
    assert artifact["rows"][0]["cells"][0]["text"] == "未找到依据"
    assert citations == []
    assert "未找到依据" in content
    assert warning is None
    provider.assert_not_called()


async def test_invalid_json_falls_back_to_scoped_text(monkeypatch):
    from app.services import comparison_service as service
    from app.services import scoped_chat_service as scoped
    retrieval = AsyncMock(return_value=evidence())
    monkeypatch.setattr(service, "prepare_comparison_evidence", retrieval)
    access_check = AsyncMock(return_value={"a": "A", "b": "B"})
    monkeypatch.setattr(service, "source_names", access_check)
    async def generate(*args, **kwargs):
        yield "invalid JSON"
    async def ordinary(system, history):
        assert "[1]" in system
        assert history == [{"role": "user", "content": "事务"}]
        yield "普通回答[1]"
    monkeypatch.setattr(service, "stream_generate", generate)
    monkeypatch.setattr(scoped, "stream_generate", ordinary)
    second_retrieval = AsyncMock(side_effect=AssertionError("must reuse existing evidence"))
    monkeypatch.setattr(scoped, "prepare_evidence", second_retrieval)
    content, citations, artifact, warning = await generate_comparison("事务", {"a": "va", "b": "vb"}, "owner", {"a": "A", "b": "B"})
    assert content == "普通回答[1]"
    assert artifact is None and warning
    assert citations == [evidence()[0]]
    retrieval.assert_awaited_once()
    second_retrieval.assert_not_awaited()
    access_check.assert_awaited_once_with({"a": "va", "b": "vb"}, "owner")


async def test_provider_failure_is_not_relabelled_as_valid_comparison(monkeypatch):
    from app.services import comparison_service as service
    monkeypatch.setattr(service, "prepare_comparison_evidence", AsyncMock(return_value=evidence()))
    monkeypatch.setattr(service, "source_names", AsyncMock(return_value={"a": "A", "b": "B"}))
    async def generate(*args, **kwargs):
        yield '{"rows":'
        raise RuntimeError("provider interrupted")
    monkeypatch.setattr(service, "stream_generate", generate)
    with pytest.raises(RuntimeError):
        await generate_comparison("事务", {"a": "va", "b": "vb"}, "owner", {"a": "A", "b": "B"})


async def test_fallback_provider_failure_does_not_become_a_complete_answer(monkeypatch):
    from app.services import comparison_service as service
    from app.services import scoped_chat_service as scoped

    monkeypatch.setattr(service, "prepare_comparison_evidence", AsyncMock(return_value=evidence()))
    monkeypatch.setattr(service, "source_names", AsyncMock(return_value={"a": "A", "b": "B"}))
    async def invalid(*args, **kwargs):
        yield "invalid JSON"
    async def interrupted(*args, **kwargs):
        yield "部分回答"
        raise RuntimeError("provider interrupted")
    monkeypatch.setattr(service, "stream_generate", invalid)
    monkeypatch.setattr(scoped, "stream_generate", interrupted)
    with pytest.raises(RuntimeError, match="provider interrupted"):
        await generate_comparison("事务", {"a": "va", "b": "vb"}, "owner", {"a": "A", "b": "B"})


async def test_fallback_does_not_resend_evidence_if_source_access_is_lost(monkeypatch):
    from app.services import comparison_service as service
    from app.services import scoped_chat_service as scoped

    monkeypatch.setattr(service, "prepare_comparison_evidence", AsyncMock(return_value=evidence()))
    monkeypatch.setattr(service, "source_names", AsyncMock(side_effect=ValueError("资料来源不可用")))
    async def invalid(*args, **kwargs):
        yield "invalid JSON"
    second_call = AsyncMock()
    monkeypatch.setattr(service, "stream_generate", invalid)
    monkeypatch.setattr(scoped, "stream_generate", second_call)
    with pytest.raises(ValueError, match="资料来源不可用"):
        await generate_comparison("事务", {"a": "va", "b": "vb"}, "owner", {"a": "A", "b": "B"})
    second_call.assert_not_called()
