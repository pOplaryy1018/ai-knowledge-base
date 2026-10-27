from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.scoped_chat_service import cited_evidence


def test_only_exact_valid_reference_and_full_quote():
    evidence = [{"index": 1, "quote": "x" * 900}, {"index": 2, "quote": "unused"}]
    assert cited_evidence("事实[1]。错误[99]。", evidence) == [evidence[0]]
    assert cited_evidence("事实[01]。[1,2]", evidence) == []


async def test_evidence_documents_are_loaded_once_and_mismatched_revision_is_rejected(monkeypatch):
    from app.services import scoped_chat_service as service

    items = [
        SimpleNamespace(document_id="doc-a", revision_id="rev-a", content="first", title="A", locator={"char_start": 0, "char_end": 5}),
        SimpleNamespace(document_id="doc-b", revision_id="rev-a", content="wrong", title="B", locator={}),
    ]
    documents = [
        SimpleNamespace(id="doc-a", revision_id="rev-a", text="first", locator={}, logical_path="a.txt"),
        SimpleNamespace(id="doc-b", revision_id="rev-other", locator={}, logical_path="b.txt"),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = documents
    session = AsyncMock()
    session.execute.return_value = result
    session.get.side_effect = lambda _model, document_id: next((doc for doc in documents if doc.id == document_id), None)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    monkeypatch.setattr(service, "retrieve_version_evidence", AsyncMock(return_value=[SimpleNamespace(item=item) for item in items]))

    evidence = await service.prepare_evidence("question", {"source-a": "rev-a"}, "user-a")
    assert [entry["quote"] for entry in evidence] == ["first"]
    assert evidence[0]["locator"]["logical_path"] == "a.txt"
    session.execute.assert_awaited_once()


@pytest.mark.parametrize(("content", "locator", "valid"), [
    ("原文", {"char_start": 1, "char_end": 3}, True),
    ("伪造", {"char_start": 1, "char_end": 3}, False),
    ("原文", {"char_start": 1, "char_end": 4}, False),
    ("原文", {"char_start": True, "char_end": 3}, False),
    ("原文", {"char_start": -1, "char_end": 1}, False),
    ("", {"char_start": 1, "char_end": 1}, False),
    ("原文", {}, False),
    ("原文", [1, 3], False),
])
async def test_retrieval_chunk_must_match_original_and_trusted_origin(monkeypatch, content, locator, valid):
    from app.services import scoped_chat_service as service

    item = SimpleNamespace(document_id="doc", revision_id="rev", content=content, title="A",
                           locator={**locator, "origin": "image_ocr"} if isinstance(locator, dict) else locator)
    document = SimpleNamespace(id="doc", revision_id="rev", text="前原文后", logical_path="manual_description",
                               locator={"origin": "manual_description"})
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [document]
    session = AsyncMock()
    session.execute.return_value = rows
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "async_session", lambda: context)
    monkeypatch.setattr(service, "retrieve_version_evidence", AsyncMock(return_value=[SimpleNamespace(item=item)]))
    evidence = await service.prepare_evidence("question", {"source": "rev"}, "owner")
    assert bool(evidence) is valid
    if valid:
        assert evidence[0]["quote"] == "原文"
        assert evidence[0]["locator"]["origin"] == "manual_description"


@pytest.mark.parametrize(("answer", "citations", "expected"), [
    ("有依据[1]", [{"index": 1}], None),
    ("有依据[1]，但另有[99]", [{"index": 1}], "未匹配"),
    ("组合标记[1,2]", [], "未匹配"),
    ("未提供标记", [], "未附"),
    ("所选资料中没有足够的相关证据，无法据此回答。", [], None),
])
def test_citation_diagnostics_are_cautious(answer, citations, expected):
    from app.services import scoped_chat_service as service

    assert hasattr(service, "citation_warning")
    warning = service.citation_warning(answer, citations)
    assert (expected in warning) if expected else warning is None


async def test_scoped_stream_emits_warning_for_unmatched_reference(monkeypatch):
    import json

    from app.services import scoped_chat_service as service

    async def generate(_prompt, _history):
        yield "有依据[1]，另一个标记[99]"

    monkeypatch.setattr(service, "prepare_evidence", AsyncMock(return_value=[{"index": 1, "knowledge_title": "测试", "content": "原文"}]))
    monkeypatch.setattr(service, "stream_generate", generate)
    monkeypatch.setattr(service, "persist_answer", AsyncMock(return_value="message"))
    events = [chunk.decode() async for chunk in service.run_scoped_stream("conversation", "问题", {"a": "v"}, [], "owner")]
    warning = next(event for event in events if event.startswith("event: warning"))
    assert "未匹配" in json.loads(warning.split("data: ", 1)[1])["message"]
    assert events[-1].startswith("event: done")


async def test_interrupted_stream_emits_error_without_citation_diagnostic(monkeypatch):
    from app.services import scoped_chat_service as service

    async def generate(_prompt, _history):
        yield "尚未完成[99]"
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(service, "prepare_evidence", AsyncMock(return_value=[{"index": 1, "knowledge_title": "测试", "content": "原文"}]))
    monkeypatch.setattr(service, "stream_generate", generate)
    persist = AsyncMock(return_value="message")
    monkeypatch.setattr(service, "persist_answer", persist)
    events = [chunk.decode() async for chunk in service.run_scoped_stream("conversation", "问题", {"a": "v"}, [], "owner")]
    assert events[-1].startswith("event: error")
    assert not any(event.startswith("event: warning") for event in events)
    assert persist.await_args.args[-1] is False


async def test_comparison_fallback_reports_invalid_citations_with_original_warning(monkeypatch):
    import json

    from app.services import comparison_service
    from app.services import scoped_chat_service as service

    monkeypatch.setattr(comparison_service, "generate_comparison", AsyncMock(
        return_value=("普通回答[99]", [], None, "对比格式未通过校验，已改为普通问答。")))
    monkeypatch.setattr(service, "persist_answer", AsyncMock(return_value="message"))
    events = [chunk.decode() async for chunk in service.run_comparison_stream(
        "conversation", "问题", {"source-a": "rev-a", "source-b": "rev-b"}, "owner")]
    warnings = [json.loads(event.split("data: ", 1)[1])["message"]
                for event in events if event.startswith("event: warning")]
    assert len(warnings) == 1
    assert "对比格式" in warnings[0] and "未匹配" in warnings[0]
    assert events[-1].startswith("event: done")
