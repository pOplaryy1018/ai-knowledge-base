"""Service-free CLI: validate assets, summarize existing results, or inspect prerequisites."""

import argparse
import json
import sys
from pathlib import Path

# Running a script under tools/ does not add the backend root to sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.quality_evaluation import (  # noqa: E402
    EvaluationError,
    load_dataset,
    preflight,
    read_results,
    summarize,
    validation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="合成资料质量评测：离线校验/汇总，真实运行显式未实现"
    )
    parser.add_argument("command", choices=("validate", "summarize", "preflight"))
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evaluation" / "cases.jsonl",
    )
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--mode", choices=("production", "fixture", "manual"), default="production")
    args = parser.parse_args()
    try:
        dataset = load_dataset(args.dataset, split=args.split)
        if args.command == "validate":
            report = validation_report(dataset)
        elif args.command == "preflight":
            report = preflight(dataset)
        elif args.results is None:
            raise EvaluationError("summarize requires --results")
        else:
            report = summarize(dataset, read_results(args.results), execution_mode=args.mode)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except EvaluationError as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    code = main()
    if code:
        raise SystemExit(code)
