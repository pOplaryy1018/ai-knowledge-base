"""Offline quality datasets and measurements, without application configuration or DB imports."""

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Category = Literal["document", "code", "image_text", "mixed"]
Split = Literal["dev", "holdout", "all"]
ExecutionMode = Literal["production", "fixture", "manual"]
Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_-]+$")]
Text = Annotated[str, Field(min_length=1, max_length=20_000)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class EvaluationError(ValueError):
    """A sanitized evaluation contract failure; never contains input values."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceAsset(StrictModel):
    id: Identifier
    kind: Literal["document", "code", "image"]
    path: Text
    sha256: Digest
    version: Version
    active: bool
    transcript_path: Text | None = None
    transcript_sha256: Digest | None = None

    @model_validator(mode="after")
    def validate_asset(self) -> Self:
        if self.version != f"sha256:{self.sha256}":
            raise ValueError("synthetic version must match asset digest")
        if self.kind == "image":
            if not self.transcript_path or not self.transcript_sha256:
                raise ValueError("image requires human transcription and digest")
        elif self.transcript_path is not None or self.transcript_sha256 is not None:
            raise ValueError("transcription belongs only to images")
        return self


class ExpectedEvidence(StrictModel):
    source_id: Identifier
    quote: Text


class EvaluationCase(StrictModel):
    schema_version: Literal[1]
    id: Identifier
    group_id: Identifier
    category: Category
    split: Literal["dev", "holdout"]
    scenario: Literal["positive", "no_evidence", "conflict", "update", "prompt_injection"]
    question: Text
    sources: Annotated[list[SourceAsset], Field(min_length=1, max_length=8)]
    expected_facts: list[Text]
    expected_evidence: list[ExpectedEvidence]
    should_refuse: bool

    @model_validator(mode="after")
    def validate_expectations(self) -> Self:
        if self.should_refuse != (self.scenario == "no_evidence"):
            raise ValueError("refusal label does not match scenario")
        if self.should_refuse:
            if self.expected_facts or self.expected_evidence:
                raise ValueError("no-evidence case cannot have gold facts or citations")
        elif not self.expected_facts or not self.expected_evidence:
            raise ValueError("answerable case requires facts and evidence")
        kinds = {source.kind for source in self.sources if source.active}
        required = {
            "document": {"document"},
            "code": {"code"},
            "image_text": {"image"},
            "mixed": {"document", "code", "image"},
        }[self.category]
        if kinds != required:
            raise ValueError("source kinds do not match category")
        if self.scenario == "conflict" and sum(source.active for source in self.sources) < 2:
            raise ValueError("conflict requires multiple current sources")
        if self.scenario == "update" and not any(not source.active for source in self.sources):
            raise ValueError("update requires an explicit previous version")
        return self


class Citation(StrictModel):
    source_id: Identifier
    version: Version
    quote: Text


class ManualSupport(StrictModel):
    supported: Annotated[int, Field(ge=0)]
    total: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.supported > self.total:
            raise ValueError("supported count exceeds checked statements")
        return self


class EvaluationResult(StrictModel):
    dataset_hash: Digest
    case_id: Identifier
    status: Literal["completed", "error", "not_run"]
    execution_mode: ExecutionMode
    answer: str | None = None
    refused: bool | None = None
    retrieved: list[Citation] | None = None
    citations: list[Citation] = Field(default_factory=list)
    ocr_text: dict[Identifier, str] | None = None
    manual_support: ManualSupport | None = None
    reason_code: (
        Literal["dependency_missing", "timeout", "provider_error", "not_implemented"] | None
    ) = None

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        if self.status == "completed" and (self.answer is None or self.refused is None):
            raise ValueError("completed result requires answer and refusal observation")
        if self.status != "completed" and (
            self.retrieved is not None
            or self.citations
            or self.ocr_text is not None
            or self.manual_support is not None
            or self.refused is not None
            or self.answer is not None
        ):
            raise ValueError("unfinished result cannot contribute observations")
        return self


@dataclass(frozen=True)
class Dataset:
    path: Path
    cases: tuple[EvaluationCase, ...]
    total_cases: int
    dataset_hash: str
    split: Split
    source_texts: dict[str, str]


def _read_jsonl(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    try:
        raw = path.read_bytes()
        if len(raw) > 20 * 1024 * 1024:
            raise EvaluationError("JSONL exceeds 20 MiB")
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        raise EvaluationError("JSONL is missing or is not UTF-8") from None
    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            raise EvaluationError(f"blank JSONL row at line {number}")
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            raise EvaluationError(f"invalid JSON at line {number}") from None
        if not isinstance(record, dict):
            raise EvaluationError(f"JSON object required at line {number}")
        records.append(record)
    return raw, records


def _parse(model: type[StrictModel], record: dict[str, Any], line: int) -> Any:
    try:
        return model.model_validate(record)
    except ValidationError:
        # Pydantic errors may contain secret input values: expose no raw errors.
        raise EvaluationError(f"schema validation failed at line {line}") from None


def _asset_bytes(root: Path, relative: str, expected_hash: str) -> bytes:
    if (
        not re.fullmatch(r"[A-Za-z0-9_./-]+", relative)
        or PurePosixPath(relative).is_absolute()
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise EvaluationError("asset path escape or unsupported path")
    try:
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root):
            raise EvaluationError("asset symlink escape")
        if not target.is_file() or target.stat().st_size > 10 * 1024 * 1024:
            raise EvaluationError("asset missing, not a file, or exceeds 10 MiB")
        raw = target.read_bytes()
    except (OSError, RuntimeError):
        raise EvaluationError("asset unavailable") from None
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise EvaluationError("asset SHA256 drift")
    return raw


def load_dataset(path: str | Path, *, split: Split = "dev") -> Dataset:
    """Validate all 60 cases and assets before selecting a split; dev is the default."""
    if split not in {"dev", "holdout", "all"}:
        raise EvaluationError("unknown split")
    path = Path(path).resolve()
    raw, records = _read_jsonl(path)
    cases: list[EvaluationCase] = [
        _parse(EvaluationCase, row, i) for i, row in enumerate(records, 1)
    ]
    if len(cases) != 60:
        raise EvaluationError("dataset requires exactly 60 cases")
    ids: set[str] = set()
    groups: dict[str, str] = {}
    resources: dict[str, str] = {}
    source_texts: dict[str, str] = {}
    for case in cases:
        if case.id in ids:
            raise EvaluationError("duplicate case ID")
        ids.add(case.id)
        if groups.setdefault(case.group_id, case.split) != case.split:
            raise EvaluationError("group crosses development and holdout splits")
        for source in case.sources:
            if source.id in source_texts:
                raise EvaluationError("duplicate source ID")
            for digest in (source.sha256, source.transcript_sha256):
                if digest is not None and resources.setdefault(digest, case.split) != case.split:
                    raise EvaluationError("identical asset crosses dataset splits")
            content = _asset_bytes(path.parent, source.path, source.sha256)
            if source.kind == "image":
                content = _asset_bytes(
                    path.parent, source.transcript_path or "", source.transcript_sha256 or ""
                )
            try:
                source_texts[source.id] = content.decode("utf-8")
            except UnicodeError:
                raise EvaluationError("source text is not UTF-8") from None
        active = {source.id for source in case.sources if source.active}
        seen_evidence: set[tuple[str, str]] = set()
        for evidence in case.expected_evidence:
            key = evidence.source_id, evidence.quote
            if evidence.source_id not in active or evidence.quote not in source_texts.get(
                evidence.source_id, ""
            ):
                raise EvaluationError("expected quote does not exist in active source")
            if key in seen_evidence:
                raise EvaluationError("duplicate expected evidence")
            seen_evidence.add(key)
    expected_scenarios = {"positive", "no_evidence", "conflict", "update", "prompt_injection"}
    for category in ("document", "code", "image_text", "mixed"):
        for part, count in (("dev", 10), ("holdout", 5)):
            selected = [case for case in cases if case.category == category and case.split == part]
            if len(selected) != count or {case.scenario for case in selected} != expected_scenarios:
                raise EvaluationError("category/split count or scenario coverage is invalid")
    selected_cases = tuple(case for case in cases if split == "all" or case.split == split)
    return Dataset(
        path, selected_cases, len(cases), hashlib.sha256(raw).hexdigest(), split, source_texts
    )


def read_results(path: str | Path) -> list[dict[str, Any]]:
    """Read records for summarize; input is validated before any metrics are counted."""
    return _read_jsonl(Path(path))[1]


def _metric(numerator: int | float, denominator: int) -> dict[str, Any]:
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
    }


def _distance(reference: str, observed: str) -> int:
    previous = list(range(len(observed) + 1))
    for i, expected in enumerate(reference, 1):
        row = [i]
        for j, actual in enumerate(observed, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != actual)))
        previous = row
    return previous[-1]


def _citation_reason(case: EvaluationCase, citation: Citation, texts: dict[str, str]) -> str | None:
    source = next((source for source in case.sources if source.id == citation.source_id), None)
    if source is None:
        return "source_out_of_scope"
    if not source.active or source.version != citation.version:
        return "wrong_source_version"
    if citation.quote not in texts[source.id]:
        return "quote_not_in_source"
    return None


def _provenance(
    dataset: Dataset, status: str, models: dict[str, str | None] | None = None
) -> dict[str, Any]:
    dirty: bool | None = None
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        state = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if state.returncode == 0:
            dirty = bool(state.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        commit = ""
    return {
        "schema_version": 1,
        "run_id": uuid.uuid4().hex,
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_hash": dataset.dataset_hash,
        "code_commit": commit if re.fullmatch(r"[0-9a-f]{40,64}", commit) else None,
        "code_dirty": dirty,
        "models": models or {"embedding": None, "llm": None, "ocr": None},
        "parameters": {"split": dataset.split, "retrieval_k": 5, "cer_normalization": "none"},
        "quality_gate": "not_assessed",
        "not_run_reasons": [],
    }


def validation_report(dataset: Dataset) -> dict[str, Any]:
    report = _provenance(dataset, "validated")
    report.update(
        counts={"total_cases": dataset.total_cases, "selected_cases": len(dataset.cases)},
        metrics={},
    )
    report["not_run_reasons"] = ["validation_only_no_models_called"]
    return report


def summarize(
    dataset: Dataset,
    records: list[dict[str, Any]],
    *,
    execution_mode: ExecutionMode = "production",
    models: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Summarize observed results only; legal quotations never imply factual support."""
    report = _provenance(dataset, "offline_summary", models)
    case_map = {case.id: case for case in dataset.cases}
    results: list[EvaluationResult] = [
        _parse(EvaluationResult, row, i) for i, row in enumerate(records, 1)
    ]
    seen: set[str] = set()
    for result in results:
        if result.dataset_hash != dataset.dataset_hash:
            raise EvaluationError("result dataset hash does not match selected dataset")
        if result.case_id in seen:
            raise EvaluationError("duplicate result case ID")
        if result.case_id not in case_map:
            raise EvaluationError("result case is not in selected split")
        seen.add(result.case_id)
    selected = [result for result in results if result.execution_mode == execution_mode]
    completed = [result for result in selected if result.status == "completed"]
    counts = Counter(result.status for result in selected)
    report["counts"] = {
        "selected_cases": len(dataset.cases),
        "provided_results": len(results),
        "matching_mode": len(selected),
        "completed": counts["completed"],
        "error": counts["error"],
        "not_run": counts["not_run"],
        "missing_results": len(dataset.cases) - len(selected),
        "excluded_other_mode": len(results) - len(selected),
    }
    report["execution_mode"] = execution_mode
    totals: dict[str, list[int | float]] = {
        name: [0, 0]
        for name in (
            "recall_at_5",
            "mrr",
            "correct_refusal",
            "false_refusal",
            "ocr_cer",
            "invalid_citations",
            "statement_support",
        )
    }
    diagnostics: list[dict[str, str]] = []
    for result in completed:
        case = case_map[result.case_id]
        refusal = "correct_refusal" if case.should_refuse else "false_refusal"
        totals[refusal][0] += int(result.refused is True)
        totals[refusal][1] += 1
        if result.retrieved is not None and case.expected_evidence:
            relevant: set[int] = set()
            first_rank = 0
            for rank, hit in enumerate(result.retrieved, 1):
                reason = _citation_reason(case, hit, dataset.source_texts)
                if reason:
                    diagnostics.append({"case_id": case.id, "kind": "retrieval", "reason": reason})
                    continue
                matches = {
                    i
                    for i, gold in enumerate(case.expected_evidence)
                    if gold.source_id == hit.source_id and gold.quote in hit.quote
                }
                if matches and not first_rank:
                    first_rank = rank
                if rank <= 5:
                    relevant.update(matches)
            totals["recall_at_5"][0] += len(relevant) / len(case.expected_evidence)
            totals["recall_at_5"][1] += 1
            totals["mrr"][0] += 1 / first_rank if first_rank else 0
            totals["mrr"][1] += 1
        for citation in result.citations:
            reason = _citation_reason(case, citation, dataset.source_texts)
            totals["invalid_citations"][0] += int(reason is not None)
            totals["invalid_citations"][1] += 1
            if reason:
                diagnostics.append({"case_id": case.id, "kind": "citation", "reason": reason})
        if not case.should_refuse and not result.refused and not result.citations:
            diagnostics.append(
                {"case_id": case.id, "kind": "citation", "reason": "missing_citations"}
            )
        if result.manual_support is not None:
            totals["statement_support"][0] += result.manual_support.supported
            totals["statement_support"][1] += result.manual_support.total
        for source_id, observed in (result.ocr_text or {}).items():
            source = next((source for source in case.sources if source.id == source_id), None)
            if source is None or source.kind != "image" or not source.active:
                raise EvaluationError("OCR observation is not an active image source")
            expected_text = dataset.source_texts[source_id]
            totals["ocr_cer"][0] += _distance(expected_text, observed)
            totals["ocr_cer"][1] += len(expected_text)
    report["metrics"] = {
        name: _metric(values[0], int(values[1])) for name, values in totals.items()
    }
    report["diagnostics"] = diagnostics
    report["metric_definitions"] = {
        "recall_at_5": "macro gold-passage recall among answerable cases with retrieval observations",
        "mrr": "first valid gold-passage hit in the supplied ranking; macro mean on observed answerable cases",
        "refusal": "completed observations only; missing/error/not_run excluded and separately counted",
        "ocr_cer": "sum Unicode edit distances / human-transcribed characters; whitespace preserved",
        "statement_support": "human checked supported statements / human checked statements only",
        "invalid_citations": "invalid scope/version/verbatim quote / supplied citations; not semantic support",
    }
    report["not_run_reasons"] = ["summary_only_no_models_called"]
    if execution_mode != "production":
        report["not_run_reasons"].append("fixture_or_manual_observations_not_real_model_baseline")
    if len(completed) < len(dataset.cases):
        report["not_run_reasons"].append("selected_cases_have_missing_or_unfinished_observations")
    return report


def preflight(dataset: Dataset) -> dict[str, Any]:
    """Inspect local prerequisites without model loading, downloads, HTTP or business DB access."""
    report = _provenance(dataset, "not_run")
    dependencies: dict[str, str | None] = {}
    for name in ("sentence-transformers", "pytesseract", "openai"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    executable = shutil.which("tesseract")
    languages: list[str] = []
    if executable:
        try:
            probe = subprocess.run(
                [executable, "--list-langs"], capture_output=True, text=True, timeout=5, check=False
            )
            if probe.returncode == 0:
                languages = [
                    lang
                    for lang in probe.stdout.splitlines()
                    if lang in {"eng", "chi_sim", "chi_tra"}
                ]
        except (OSError, subprocess.TimeoutExpired):
            pass
    report["checks"] = {
        "python_312": sys.version_info[:2] == (3, 12),
        "dependencies": dependencies,
        "ocr": {"executable_found": executable is not None, "languages": languages},
        "embedding": {"status": "not_probed", "required_dimension": 1024},
        "llm": {"status": "not_probed", "credential_present": bool(os.environ.get("LLM_API_KEY"))},
    }
    report["metrics"] = {}
    report["not_run_reasons"] = [
        "production_adapter_not_implemented",
        "embedding_and_llm_not_probed",
    ]
    if not executable or not {"eng", "chi_sim"}.issubset(languages):
        report["not_run_reasons"].append("tesseract_or_required_languages_unavailable")
    return report
