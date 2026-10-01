"""Exact, whitespace-preserving evidence matching with explicit uncertainty."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.services.source_extraction import LocatedText


@dataclass(frozen=True)
class EvidenceMatch:
    state: Literal["unchanged", "relocated", "changed", "missing", "ambiguous", "unavailable"]
    locator: dict[str, object] | None = None
    current_text: str | None = None


def match_evidence(
    quote: str,
    document: LocatedText | Sequence[LocatedText] | str | None,
    original_locator: dict[str, object] | None = None,
) -> EvidenceMatch:
    """Match verbatim quotes only; overlapping occurrences also count as ambiguous."""
    if not quote:
        return EvidenceMatch("unavailable")
    if document is None:
        return EvidenceMatch("missing")
    documents: Sequence[LocatedText]
    if isinstance(document, str):
        documents = [LocatedText("text", document, {"type": "text"})]
    elif isinstance(document, LocatedText):
        documents = [document]
    else:
        documents = document
    if not documents:
        return EvidenceMatch("missing")
    matches: list[dict[str, object]] = []
    for item in documents:
        start = item.text.find(quote)
        while start >= 0:
            # A quote containing indentation must include all leading whitespace.
            # Mid-line excerpts still match normally when preceded by actual text.
            line_start = item.text.rfind("\n", 0, start) + 1
            prefix = item.text[line_start:start]
            if quote[0] in " \t" and prefix and not prefix.strip(" \t"):
                start = item.text.find(quote, start + 1)
                continue
            end = start + len(quote)
            matches.append({
                **item.locator, "logical_path": item.logical_path,
                "char_start": start, "char_end": end,
                "line_start": item.text.count("\n", 0, start) + 1,
                "line_end": item.text.count("\n", 0, end) + 1,
            })
            if len(matches) > 1:
                return EvidenceMatch("ambiguous")
            start = item.text.find(quote, start + 1)
    if not matches:
        return EvidenceMatch("changed")
    locator = matches[0]
    # Compare the supplied position fields; old locators may omit descriptive metadata.
    same_position = original_locator is None or all(
        locator.get(key) == value for key, value in original_locator.items()
    )
    return EvidenceMatch("unchanged" if same_position else "relocated", locator, quote)
