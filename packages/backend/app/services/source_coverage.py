"""Pure publication gate for extraction coverage and summarization batches."""

from dataclasses import dataclass
from typing import Literal

ExtractionState = Literal["complete", "partial", "unverified", "empty"]


@dataclass(frozen=True)
class Coverage:
    extraction: ExtractionState
    planned: int
    succeeded: int
    failed: int
    evidence_valid: bool


def publishable(coverage: Coverage) -> bool:
    """Allow publication only when coverage, batches and citations are verified."""
    extraction: object = coverage.extraction
    return (
        type(extraction) is str
        and extraction == "complete"
        and type(coverage.planned) is int
        and type(coverage.succeeded) is int
        and type(coverage.failed) is int
        and coverage.planned > 0
        and coverage.succeeded == coverage.planned
        and coverage.failed == 0
        and coverage.evidence_valid is True
    )
