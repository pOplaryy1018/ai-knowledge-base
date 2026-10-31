import pytest

from app.services.source_coverage import Coverage, publishable


@pytest.mark.parametrize(
    ("coverage", "expected"),
    [
        (Coverage("complete", 2, 2, 0, True), True),
        (Coverage("partial", 2, 2, 0, True), False),
        (Coverage("unverified", 2, 2, 0, True), False),
        (Coverage("empty", 0, 0, 0, False), False),
        (Coverage("complete", 3, 2, 1, True), False),
        (Coverage("complete", 2, 2, 0, False), False),
        (Coverage("complete", 2, 1, 0, True), False),
        (Coverage("complete", 0, 0, 0, True), False),
        (Coverage("complete", 2, 3, 0, True), False),
        (Coverage("complete", 2, 2, -1, True), False),
    ],
)
def test_only_complete_verifiable_evidence_is_publishable(coverage: Coverage, expected: bool) -> None:
    assert publishable(coverage) is expected


@pytest.mark.parametrize(
    "coverage",
    [
        Coverage("complete", True, 1, 0, True),
        Coverage("complete", 1, 1.0, 0, True),
        Coverage("complete", 1, 1, False, True),
        Coverage("complete", 1, 1, 0, 1),
    ],
)
def test_malformed_counts_or_evidence_fail_closed(coverage: Coverage) -> None:
    assert not publishable(coverage)


def test_non_string_extraction_with_spoofed_equality_fails_closed() -> None:
    class SpoofedExtraction:
        def __eq__(self, other: object) -> bool:
            return True

    coverage = Coverage(SpoofedExtraction(), 1, 1, 0, True)  # type: ignore[arg-type]
    assert publishable(coverage) is False
