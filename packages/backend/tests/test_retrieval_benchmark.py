import pytest

from tools.retrieval_benchmark import run_benchmark, summarize_retrieval, validate_test_database


def test_benchmark_rejects_business_or_remote_databases():
    validate_test_database("postgresql+asyncpg://test:test@127.0.0.1:25432/akb_evidence_test")
    for url in (
        "postgresql+asyncpg://test:test@127.0.0.1:5432/akb_evidence_test",
        "postgresql+asyncpg://test:test@127.0.0.1:25432/business",
        "postgresql+asyncpg://test:test@remote:25432/akb_evidence_test",
    ):
        with pytest.raises(ValueError):
            validate_test_database(url)


def test_retrieval_metrics_exclude_errors_and_unanswerable_cases():
    expected = [{"source_id": "s1", "version": "v1", "quote": "correct"}]
    rows = [
        {"status": "completed", "expected": expected, "hits": [
            {"source_id": "s1", "version": "old", "content": "correct"},
            {"source_id": "s1", "version": "v1", "content": "the correct text"},
        ], "latency_ms": 20.0},
        {"status": "completed", "expected": [], "hits": [], "latency_ms": 40.0},
        {"status": "error", "expected": expected, "hits": [], "latency_ms": None},
    ]
    result = summarize_retrieval(rows)
    assert result["recall_at_5"] == {"value": 1.0, "numerator": 1.0, "denominator": 1}
    assert result["mrr"] == {"value": 0.5, "numerator": 0.5, "denominator": 1}
    assert result["latency_ms"]["count"] == 2
    assert result["counts"] == {"completed": 2, "error": 1}


async def test_benchmark_entrypoint_checks_test_database_before_loading_assets(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://test:test@remote:25432/akb_evidence_test")
    with pytest.raises(ValueError, match="isolated test URL|local akb_evidence_test"):
        await run_benchmark(tmp_path / "missing.jsonl", tmp_path / "model", 1)
