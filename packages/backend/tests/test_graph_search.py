"""Either retrieval route may provide verified source evidence."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import graph_search
from app.services.search_service import SearchResult


@pytest.mark.asyncio
async def test_graph_evidence_survives_vector_failure(monkeypatch) -> None:
    item = SimpleNamespace(id="item-1", revision_id="revision-1")

    async def vector_failure(*args, **kwargs):
        raise RuntimeError("vector unavailable")

    async def graph_hit(*args, **kwargs):
        return [SearchResult(item, 1 / 61)]

    monkeypatch.setattr(graph_search, "hybrid_search_versions", vector_failure)
    monkeypatch.setattr(graph_search, "_graph_results", graph_hit)
    rows = await graph_search.retrieve_version_evidence({"source-1": "revision-1"}, "甲公司", "user-1")
    assert [row.item.id for row in rows] == ["item-1"]


@pytest.mark.asyncio
async def test_vector_evidence_survives_graph_failure(monkeypatch) -> None:
    item = SimpleNamespace(id="item-1", revision_id="revision-1")

    async def vector_hit(*args, **kwargs):
        return [SearchResult(item, 1 / 61)]

    async def graph_failure(*args, **kwargs):
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(graph_search, "hybrid_search_versions", vector_hit)
    monkeypatch.setattr(graph_search, "_graph_results", graph_failure)
    rows = await graph_search.retrieve_version_evidence({"source-1": "revision-1"}, "甲公司", "user-1")
    assert [row.item.id for row in rows] == ["item-1"]


@pytest.mark.asyncio
async def test_both_routes_failed_is_service_error(monkeypatch) -> None:
    async def failure(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(graph_search, "hybrid_search_versions", failure)
    monkeypatch.setattr(graph_search, "_graph_results", failure)
    with pytest.raises(HTTPException) as error:
        await graph_search.retrieve_version_evidence({"source-1": "revision-1"}, "甲公司", "user-1")
    assert error.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(("revisions", "expected"), [
    (["revision-1"] * 6, ["item-0", "item-1", "item-2", "item-3", "item-4"]),
    (["revision-1"] * 5 + ["revision-2"], ["item-0", "item-1", "item-2", "item-3", "item-5"]),
    (["revision-1"] * 4 + ["revision-2"] * 4, ["item-0", "item-1", "item-2", "item-4", "item-5"]),
])
async def test_diversity_backfills_unused_slots_in_rank_order(monkeypatch, revisions, expected) -> None:
    items = [SimpleNamespace(id=f"item-{index}", revision_id=revision) for index, revision in enumerate(revisions)]

    async def vector_hits(*args, **kwargs):
        return [SearchResult(item, 1 / (61 + rank)) for rank, item in enumerate(items)]

    async def graph_empty(*args, **kwargs):
        return []

    monkeypatch.setattr(graph_search, "hybrid_search_versions", vector_hits)
    monkeypatch.setattr(graph_search, "_graph_results", graph_empty)
    rows = await graph_search.retrieve_version_evidence({"source-1": "revision-1", "source-2": "revision-2"}, "问题", "user-1")
    assert [row.item.id for row in rows] == expected
