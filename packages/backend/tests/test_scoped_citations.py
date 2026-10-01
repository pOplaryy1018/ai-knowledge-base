from app.services.scoped_chat_service import cited_evidence


def test_only_exact_valid_reference_and_full_quote():
    evidence = [{"index": 1, "quote": "x" * 900}, {"index": 2, "quote": "unused"}]
    assert cited_evidence("事实[1]。错误[99]。", evidence) == [evidence[0]]
    assert cited_evidence("事实[01]。[1,2]", evidence) == []
