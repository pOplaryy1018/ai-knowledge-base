"""Measure scoped text retrieval on a selected synthetic split in the isolated test DB."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.engine import make_url


def validate_test_database(url: str) -> None:
    try:
        parsed = make_url(url)
    except Exception:
        raise ValueError("Retrieval benchmark requires a valid isolated test URL") from None
    if (parsed.drivername != "postgresql+asyncpg" or parsed.host not in {"localhost", "127.0.0.1"}
            or parsed.port != 25432 or parsed.database != "akb_evidence_test"):
        raise ValueError("Retrieval benchmark requires local akb_evidence_test on port 25432")


def summarize_retrieval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "completed"]
    recall_sum = 0.0
    mrr_sum = 0.0
    answerable = 0
    for row in completed:
        expected = row["expected"]
        if not expected:
            continue
        answerable += 1
        matches = [
            [index for index, hit in enumerate(row["hits"][:5], 1)
             if hit["source_id"] == gold["source_id"] and hit["version"] == gold["version"]
             and gold["quote"] in hit["content"]]
            for gold in expected
        ]
        recall_sum += sum(bool(match) for match in matches) / len(expected)
        ranks = [rank for match in matches for rank in match]
        if ranks:
            mrr_sum += 1 / min(ranks)
    durations = sorted(float(row["latency_ms"]) for row in completed if row["latency_ms"] is not None)
    return {
        "recall_at_5": {"value": recall_sum / answerable if answerable else None,
                        "numerator": recall_sum, "denominator": answerable},
        "mrr": {"value": mrr_sum / answerable if answerable else None,
                "numerator": mrr_sum, "denominator": answerable},
        "latency_ms": {"count": len(durations),
                       "p50": statistics.median(durations) if durations else None,
                       "p95": durations[math.ceil(len(durations) * .95) - 1] if durations else None},
        "counts": {"completed": len(completed), "error": len(rows) - len(completed)},
    }


def git_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def select_cases(cases: Any, limit: int, *, comparison: bool = False) -> list[Any]:
    return [case for case in cases if case.category in {"document", "code"}
            and (not comparison or case.scenario == "conflict")][:limit]


def validate_split(split: str) -> Literal["dev", "holdout"]:
    if split == "dev":
        return "dev"
    if split == "holdout":
        return "holdout"
    raise ValueError("Retrieval benchmark split must be dev or holdout")


async def run_benchmark(dataset_path: Path, model_path: Path, limit: int, *,
                        comparison: bool = False, repeats: int = 1, split: str = "dev") -> dict[str, Any]:
    test_url = os.environ.get("TEST_DATABASE_URL", "")
    validate_test_database(test_url)
    if os.environ.get("DATABASE_URL") != test_url:
        raise ValueError("DATABASE_URL must match the isolated test URL")
    if not 1 <= repeats <= 5:
        raise ValueError("Repeats must be between 1 and 5")
    from sentence_transformers import SentenceTransformer
    from sqlalchemy import delete

    from app.core.db import async_session, engine
    from app.models.knowledge import KnowledgeBase, KnowledgeItem
    from app.models.source import Source, SourceDocument, SourceRevision
    from app.models.user import User
    from app.services import vectorizer
    from app.services.comparison_service import prepare_comparison_evidence
    from app.services.quality_evaluation import load_dataset
    from app.services.search_service import hybrid_search_versions
    from app.services.source_extraction import LocatedText
    from app.services.source_publication import document_chunks

    validate_test_database(engine.url.render_as_string(hide_password=False))
    dataset = load_dataset(dataset_path, split=validate_split(split))
    cases = select_cases(dataset.cases, limit, comparison=comparison)
    if not cases:
        raise ValueError("No eligible cases for selected split")
    if not (model_path / "model.safetensors").is_file():
        raise ValueError("Local embedding model weights are unavailable")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    model = await asyncio.to_thread(SentenceTransformer, str(model_path), local_files_only=True)
    vectorizer._model = model
    run_id = uuid.uuid4().hex
    user_id = str(uuid.uuid4())
    kb_id = str(uuid.uuid4())
    source_ids: list[str] = []
    revision_ids: list[str] = []
    source_map: dict[str, tuple[str, str, str]] = {}
    chunk_rows: list[tuple[str, str, str, Any]] = []

    for case in cases:
        for source in case.sources:
            if not source.active:
                continue
            source_id, revision_id, document_id = (str(uuid.uuid4()) for _ in range(3))
            source_ids.append(source_id)
            revision_ids.append(revision_id)
            source_map[source.id] = (source_id, revision_id, document_id)
            for chunk in document_chunks([LocatedText(source.path, dataset.source_texts[source.id], {})]):
                chunk_rows.append((source.id, revision_id, document_id, chunk))
    vectors = await vectorizer.encode_texts([row[3].text for row in chunk_rows])
    vectors_list = vectors.tolist()
    if len(vectors_list) != len(chunk_rows) or any(len(vector) != 1024 for vector in vectors_list):
        raise ValueError("Embedding output has unexpected count or dimension")

    rows: list[dict[str, Any]] = []
    try:
        async with async_session() as session:
            session.add(User(id=user_id, username=f"benchmark_{run_id}", hashed_password="test-only", role="user"))
            session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="Synthetic retrieval benchmark"))
            await session.flush()
            for case in cases:
                for source in case.sources:
                    if not source.active:
                        continue
                    source_id, revision_id, document_id = source_map[source.id]
                    session.add(Source(id=source_id, user_id=user_id, knowledge_base_id=kb_id,
                                       name=source.id, kind="document"))
                    await session.flush()
                    session.add(SourceRevision(id=revision_id, source_id=source_id, raw_hash=source.sha256,
                                               pipeline_version=run_id, state="ready"))
                    await session.flush()
                    session.add(SourceDocument(id=document_id, revision_id=revision_id, logical_path=source.path,
                                               text=dataset.source_texts[source.id], locator={}, content_hash=source.sha256))
            await session.flush()
            for (source_label, revision_id, document_id, chunk), vector in zip(chunk_rows, vectors_list, strict=True):
                session.add(KnowledgeItem(knowledge_base_id=kb_id, revision_id=revision_id,
                                          document_id=document_id, title=f"{source_label} · {chunk.logical_path}",
                                          content=chunk.text, embedding=vector, locator=chunk.locator,
                                          source="source_revision", source_metadata={}))
            await session.commit()

        for case in cases:
            selected = {source_map[source.id][0]: source_map[source.id][1]
                        for source in case.sources if source.active}
            identity = {source_map[source.id][1]: (source.id, source.version)
                        for source in case.sources if source.active}
            expected = [{"source_id": gold.source_id,
                         "version": next(source.version for source in case.sources if source.id == gold.source_id),
                         "quote": gold.quote} for gold in case.expected_evidence]
            for repetition in range(repeats):
                started = time.perf_counter()
                try:
                    if comparison:
                        entries = await prepare_comparison_evidence(case.question, selected, user_id)
                        retrieved = [(entry["revision_id"], entry["content"]) for entry in entries]
                    else:
                        results = await hybrid_search_versions(selected, case.question, top_k=5, user_id=user_id)
                        retrieved = [(result.item.revision_id, result.item.content) for result in results]
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    hits = []
                    for hit_revision, content in retrieved:
                        if hit_revision is None or hit_revision not in identity:
                            raise ValueError("Retrieved item has an unexpected revision")
                        hits.append({"source_id": identity[hit_revision][0],
                                     "version": identity[hit_revision][1], "content": content})
                    rows.append({"case_id": case.id, "repetition": repetition + 1, "status": "completed",
                                 "expected": expected, "hits": hits, "latency_ms": elapsed_ms})
                except Exception:
                    rows.append({"case_id": case.id, "repetition": repetition + 1, "status": "error",
                                 "expected": expected, "hits": [], "latency_ms": None, "reason": "retrieval_failed"})
    finally:
        async with async_session() as session:
            await session.execute(delete(KnowledgeItem).where(KnowledgeItem.revision_id.in_(revision_ids)))
            await session.execute(delete(SourceDocument).where(SourceDocument.revision_id.in_(revision_ids)))
            await session.execute(delete(SourceRevision).where(SourceRevision.id.in_(revision_ids)))
            await session.execute(delete(Source).where(Source.id.in_(source_ids)))
            await session.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await engine.dispose()
        vectorizer._model = None

    config_digest = file_sha256(model_path / "config.json")
    return {"run_id": run_id, "dataset_hash": dataset.dataset_hash, "split": dataset.split,
            "scope": ("text-only per-source comparison evidence; no graph projection, OCR or generation" if comparison
                      else "text-only scoped vector and keyword retrieval; no graph, OCR or generation"),
            "model_path": str(model_path.resolve()), "model_config_sha256": config_digest,
            "model_weights_sha256": file_sha256(model_path / "model.safetensors"),
            "latency_scope": "retrieval call only; model loading and ingestion excluded; first request included",
            "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
                        "device": str(model.device)},
            "git": git_metadata(), "cases_selected": len(cases), "repeats": repeats,
            "metrics": summarize_retrieval(rows), "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=Path("models/models/Qwen--Qwen3-Embedding-0.6B/snapshots/master"))
    parser.add_argument("--limit", type=int, default=10, choices=range(1, 21))
    parser.add_argument("--comparison", action="store_true")
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--split", choices=("dev", "holdout"), default="dev")
    args = parser.parse_args()
    url = os.environ.get("TEST_DATABASE_URL", "")
    validate_test_database(url)
    os.environ["DATABASE_URL"] = url
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DEBUG"] = "false"
    report = asyncio.run(run_benchmark(Path("evaluation/cases.jsonl"), args.model_dir, args.limit,
                                       comparison=args.comparison, repeats=args.repeat, split=args.split))
    output_dir = Path("evaluation/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"retrieval-{report['run_id']}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "dataset_hash": report["dataset_hash"],
                      "split": report["split"], "scope": report["scope"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
