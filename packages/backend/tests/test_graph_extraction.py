"""Only relationship candidates backed by the exact source text are indexed."""

import json

import pytest


def test_accepts_relation_with_exact_quote_and_stable_offset() -> None:
    from app.services.graph_extraction import parse_relations

    content = "甲公司收购了乙公司。"
    raw = json.dumps({"relations": [{"subject": "甲公司", "subject_type": "组织",
        "predicate": "收购", "object": "乙公司", "object_type": "组织",
        "quote": content}]}, ensure_ascii=False)
    result = parse_relations(raw, "item-1", content)
    assert len(result.relations) == 1
    assert result.relations[0].quote_start == 0
    assert result.relations[0].quote_end == len(content)
    assert result.relations[0].item_id == "item-1"


def test_rejects_fabricated_quote_without_accepting_partial_graph() -> None:
    from app.services.graph_extraction import ExtractionError, parse_relations

    raw = json.dumps({"relations": [{"subject": "甲公司", "subject_type": "组织",
        "predicate": "收购", "object": "乙公司", "object_type": "组织",
        "quote": "甲公司收购了丙公司。"}]}, ensure_ascii=False)
    with pytest.raises(ExtractionError, match="all_invalid"):
        parse_relations(raw, "item-1", "甲公司收购了乙公司。")


def test_valid_empty_result_is_distinct_from_invalid_json() -> None:
    from app.services.graph_extraction import ExtractionError, parse_relations

    assert parse_relations('{"relations": []}', "item-1", "没有实体关系的文本。").relations == []
    with pytest.raises(ExtractionError, match="invalid_json"):
        parse_relations("not JSON", "item-1", "甲公司收购乙公司。")
