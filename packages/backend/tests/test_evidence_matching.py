from app.services.evidence_matching import match_evidence
from app.services.source_extraction import LocatedText


def test_match_preserves_indentation_and_detects_movement():
    quote = "    return 1"
    original = match_evidence(quote, "def run():\n    return 1\n")
    assert original.locator is not None
    assert match_evidence(quote, "def run():\n    return 1\n", original.locator).state == "unchanged"
    moved = match_evidence(quote, "# added\ndef run():\n    return 1\n", original.locator)
    assert moved.state == "relocated"
    assert moved.current_text == quote
    assert moved.locator is not None and moved.locator["line_start"] == 3


def test_deleted_changed_missing_and_duplicate():
    assert match_evidence("old", "new").state == "changed"
    assert match_evidence("old", []).state == "missing"
    assert match_evidence("old", None).state == "missing"
    assert match_evidence("old", "old old").state == "ambiguous"
    assert match_evidence("", "anything").state == "unavailable"
    assert match_evidence("    value", "value").state == "changed"


def test_page_location_and_cross_document_duplicates():
    pages = [LocatedText("page/1", "", {"page": 1}),
             LocatedText("page/2", "quote", {"page": 2})]
    found = match_evidence("quote", pages)
    assert found.locator is not None
    assert found.locator["page"] == 2
    assert found.locator["logical_path"] == "page/2"
    assert match_evidence("quote", pages + [LocatedText("page/3", "quote", {})]).state == "ambiguous"


def test_single_document_and_overlapping_matches():
    item = LocatedText("paragraph/4", "  citation", {"paragraph": 4})
    result = match_evidence("citation", item, {
        "logical_path": "paragraph/4", "char_start": 2, "char_end": 10,
    })
    assert result.state == "unchanged"
    assert match_evidence("aa", LocatedText("text", "aaa", {})).state == "ambiguous"


def test_changed_indentation_is_not_a_relocated_quote():
    quote = "    return 1"
    original = match_evidence(quote, "def run():\n    return 1\n")
    assert match_evidence(
        quote, "def run():\n        return 1\n", original.locator,
    ).state == "changed"
    assert match_evidence("return 1", "def run():\n        return 1\n").state == "unchanged"
    assert match_evidence(" suffix", "prefix suffix").state == "unchanged"
