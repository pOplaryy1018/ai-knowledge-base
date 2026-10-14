"""Offline evaluation contracts; never call a model or a database."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "cases.jsonl"


def evaluation():
    assert importlib.util.find_spec("app.services.quality_evaluation") is not None, (
        "Offline quality evaluation implementation is missing"
    )
    from app.services import quality_evaluation

    return quality_evaluation


def copy_dataset(tmp_path):
    target = tmp_path / "evaluation"
    shutil.copytree(DATASET.parent, target, ignore=shutil.ignore_patterns("reports", "__pycache__"))
    return target / "cases.jsonl"


def rewrite(path, change):
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    change(cases)
    path.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n", encoding="utf-8"
    )


def test_dataset_has_sixty_group_isolated_cases_and_defaults_to_development():
    module = evaluation()
    dataset = module.load_dataset(DATASET)
    assert dataset.total_cases == 60
    assert len(dataset.cases) == 40
    all_cases = module.load_dataset(DATASET, split="all").cases
    for category in ("document", "code", "image_text", "mixed"):
        selected = [case for case in all_cases if case.category == category]
        assert len(selected) == 15
        assert sum(case.split == "dev" for case in selected) == 10
        assert sum(case.split == "holdout" for case in selected) == 5
        for split in ("dev", "holdout"):
            assert {case.scenario for case in selected if case.split == split} == {
                "positive",
                "no_evidence",
                "conflict",
                "update",
                "prompt_injection",
            }
    assert {case.group_id for case in all_cases if case.split == "dev"}.isdisjoint(
        {case.group_id for case in all_cases if case.split == "holdout"}
    )


@pytest.mark.parametrize(
    "mutation", ["duplicate", "extra", "strict_bool", "quote", "group_split", "escape", "hash"]
)
def test_dataset_rejects_invalid_contracts(tmp_path, mutation):
    module = evaluation()
    path = copy_dataset(tmp_path)

    def change(cases):
        first = cases[0]
        if mutation == "duplicate":
            cases[1]["id"] = first["id"]
        elif mutation == "extra":
            first["surprise"] = "not allowed"
        elif mutation == "strict_bool":
            first["should_refuse"] = "false"
        elif mutation == "quote":
            first["expected_evidence"][0]["quote"] = "An invented passage not in any asset"
        elif mutation == "group_split":
            next(case for case in cases if case["split"] == "holdout")["group_id"] = first[
                "group_id"
            ]
        elif mutation == "escape":
            first["sources"][0]["path"] = "../outside.md"
        elif mutation == "hash":
            asset = path.parent / first["sources"][0]["path"]
            asset.write_text("drifted content", encoding="utf-8")

    rewrite(path, change)
    with pytest.raises(module.EvaluationError):
        module.load_dataset(path)


def test_dataset_rejects_symlink_escape(tmp_path):
    module = evaluation()
    path = copy_dataset(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    link = path.parent / "assets" / "outside.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("OS does not grant symlink creation")
    rewrite(path, lambda cases: cases[0]["sources"][0].update(path="assets/outside.md"))
    with pytest.raises(module.EvaluationError, match="escape"):
        module.load_dataset(path)


def result_for(case, **updates):
    result = {
        "dataset_hash": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "case_id": case.id,
        "status": "completed",
        "execution_mode": "fixture",
        "answer": "A synthetic test answer",
        "refused": False,
        "retrieved": None,
        "citations": [],
        "ocr_text": None,
        "manual_support": None,
    }
    result.update(updates)
    return result


def reference(case, expected):
    source = next(source for source in case.sources if source.id == expected.source_id)
    return {"source_id": source.id, "version": source.version, "quote": expected.quote}


def test_summary_uses_observed_denominators_and_never_infers_statement_support():
    module = evaluation()
    dataset = module.load_dataset(DATASET)
    case = next(case for case in dataset.cases if case.scenario == "positive")
    evidence = reference(case, case.expected_evidence[0])
    result = result_for(case, retrieved=[evidence], citations=[evidence])
    report = module.summarize(dataset, [result], execution_mode="fixture")
    assert report["status"] == "offline_summary"
    assert report["metrics"]["recall_at_5"]["value"] == 1.0
    assert report["metrics"]["mrr"]["value"] == 1.0
    assert report["metrics"]["statement_support"]["value"] is None
    assert report["metrics"]["statement_support"]["denominator"] == 0
    assert report["metrics"]["invalid_citations"]["numerator"] == 0
    assert report["counts"]["missing_results"] == 39
    assert report["quality_gate"] == "not_assessed"


def test_summary_refusal_ocr_and_invalid_citation_metrics_are_independent():
    module = evaluation()
    dataset = module.load_dataset(DATASET)
    absent = next(case for case in dataset.cases if case.scenario == "no_evidence")
    image = next(
        case
        for case in dataset.cases
        if case.category == "image_text" and case.scenario == "positive"
    )
    source = image.sources[0]
    text = dataset.source_texts[source.id]
    results = [
        result_for(absent, refused=True),
        result_for(
            image,
            refused=True,
            citations=[
                {"source_id": source.id, "version": source.version, "quote": "invented quote"}
            ],
            ocr_text={source.id: text[:-1]},
            manual_support={"supported": 1, "total": 2},
        ),
    ]
    report = module.summarize(dataset, results, execution_mode="fixture")
    metrics = report["metrics"]
    assert metrics["correct_refusal"]["value"] == 1.0
    assert metrics["false_refusal"]["value"] == 1.0
    assert metrics["ocr_cer"]["numerator"] == 1
    assert metrics["ocr_cer"]["denominator"] == len(text)
    assert metrics["statement_support"]["value"] == 0.5
    assert metrics["invalid_citations"]["numerator"] == 1
    assert report["diagnostics"][0]["reason"] == "quote_not_in_source"


def test_empty_summary_has_null_metrics_not_fake_zero_accuracy():
    module = evaluation()
    report = module.summarize(module.load_dataset(DATASET), [])
    assert all(metric["value"] is None for metric in report["metrics"].values())
    assert report["not_run_reasons"]


def test_summary_refuses_results_from_a_different_dataset_snapshot():
    module = evaluation()
    dataset = module.load_dataset(DATASET)
    record = result_for(dataset.cases[0])
    changed = replace(dataset, dataset_hash="0" * 64)
    with pytest.raises(module.EvaluationError, match="dataset"):
        module.summarize(changed, [record], execution_mode="fixture")


def test_summary_requires_dataset_binding_even_for_an_excluded_execution_mode():
    module = evaluation()
    dataset = module.load_dataset(DATASET)
    record = result_for(dataset.cases[0])
    record.pop("dataset_hash")
    with pytest.raises(module.EvaluationError):
        module.summarize(dataset, [record], execution_mode="production")
    record["dataset_hash"] = "0" * 64
    with pytest.raises(module.EvaluationError, match="dataset"):
        module.summarize(dataset, [record], execution_mode="production")


def test_mrr_uses_full_ranking_while_recall_is_limited_to_five():
    module = evaluation()
    dataset = module.load_dataset(DATASET)
    case = next(case for case in dataset.cases if case.scenario == "positive")
    hit = reference(case, case.expected_evidence[0])
    bad = {**hit, "quote": "not a source quotation"}
    report = module.summarize(
        dataset, [result_for(case, retrieved=[bad] * 5 + [hit])], execution_mode="fixture"
    )
    assert report["metrics"]["recall_at_5"]["value"] == 0
    assert report["metrics"]["mrr"]["value"] == pytest.approx(1 / 6)


def test_summary_rejects_duplicates_unknown_cases_and_invalid_manual_labels():
    module = evaluation()
    dataset = module.load_dataset(DATASET)
    result = result_for(dataset.cases[0])
    for records in (
        [result, result],
        [{**result, "case_id": "unknown"}],
        [
            {**result, "manual_support": {"supported": 3, "total": 2}},
        ],
    ):
        with pytest.raises(module.EvaluationError):
            module.summarize(dataset, records, execution_mode="fixture")


def test_holdout_results_cannot_silently_enter_development_report():
    module = evaluation()
    holdout = module.load_dataset(DATASET, split="holdout").cases[0]
    with pytest.raises(module.EvaluationError, match="selected split"):
        module.summarize(
            module.load_dataset(DATASET), [result_for(holdout)], execution_mode="fixture"
        )


def test_preflight_reports_not_run_and_does_not_echo_credentials(monkeypatch):
    module = evaluation()
    monkeypatch.setenv("LLM_API_KEY", "private-sentinel-do-not-echo")
    report = module.preflight(module.load_dataset(DATASET))
    assert report["status"] == "not_run"
    assert "production_adapter_not_implemented" in report["not_run_reasons"]
    assert "private-sentinel-do-not-echo" not in json.dumps(report)
    assert report["metrics"] == {}


def test_cli_validation_is_standalone_without_core_db_or_model_imports():
    evaluation()
    code = """
import runpy, sys
sys.argv = ['evaluate_quality.py', 'validate']
runpy.run_path('tools/evaluate_quality.py', run_name='__main__')
assert 'app.core.db' not in sys.modules
assert 'app.core.config' not in sys.modules
assert 'sentence_transformers' not in sys.modules
"""
    process = subprocess.run(
        [sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["status"] == "validated"
    assert report["counts"]["selected_cases"] == 40
    assert len(report["dataset_hash"]) == 64
    assert report["code_commit"] and report["run_id"]
    assert isinstance(report["code_dirty"], bool)


def test_cli_reports_schema_errors_without_echoing_input(tmp_path):
    evaluation()
    path = copy_dataset(tmp_path)
    rewrite(path, lambda cases: cases[0].update(secret="private-input-sentinel"))
    process = subprocess.run(
        [sys.executable, "tools/evaluate_quality.py", "validate", "--dataset", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert "private-input-sentinel" not in process.stdout + process.stderr
    assert json.loads(process.stdout)["status"] == "invalid"
