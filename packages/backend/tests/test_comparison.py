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
    result = await prepare_comparison_evidence("事务", {"a": "va", "c": "vc", "b": "vb"}, "owner")
    assert [entry["index"] for entry in result] == [1, 2]
    assert [call.args[1] for call in retrieve.call_args_list] == [{"a": "va"}, {"c": "vc"}, {"b": "vb"}]


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
    monkeypatch.setattr(service, "prepare_comparison_evidence", AsyncMock(return_value=evidence()))
    async def generate(*args, **kwargs):
        yield "invalid JSON"
    monkeypatch.setattr(service, "stream_generate", generate)
    fallback = AsyncMock(return_value=("普通回答[1]", [evidence()[0]]))
    monkeypatch.setattr(service, "generate_scoped_answer", fallback)
    content, citations, artifact, warning = await generate_comparison("事务", {"a": "va", "b": "vb"}, "owner", {"a": "A", "b": "B"})
    assert content == "普通回答[1]"
    assert artifact is None and warning
    assert citations == [evidence()[0]]


async def test_provider_failure_is_not_relabelled_as_valid_comparison(monkeypatch):
    from app.services import comparison_service as service
    monkeypatch.setattr(service, "prepare_comparison_evidence", AsyncMock(return_value=evidence()))
    async def generate(*args, **kwargs):
        yield '{"rows":'
        raise RuntimeError("provider interrupted")
    monkeypatch.setattr(service, "stream_generate", generate)
    with pytest.raises(RuntimeError):
        await generate_comparison("事务", {"a": "va", "b": "vb"}, "owner", {"a": "A", "b": "B"})
