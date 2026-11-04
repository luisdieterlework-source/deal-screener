import json

import pytest

from deal_screener.parsing import MemoParseError, audit_citations, extract_json, parse_memo
from deal_screener.models import Memo


def test_extracts_fenced_json(memo_json_text):
    data = extract_json(memo_json_text)
    assert data["company_name"] == "Acme Robotics"


def test_prefers_last_valid_fenced_block(memo_dict):
    text = '```json\n{"draft": true}\n```\nrevised:\n```json\n' + json.dumps(memo_dict) + "\n```"
    assert extract_json(text)["company_name"] == "Acme Robotics"


def test_extracts_unfenced_json_with_braces_in_strings(memo_dict):
    memo_dict["one_liner"] = "Uses {curly} braces in text"
    data = extract_json("Sure! " + json.dumps(memo_dict) + " Hope this helps.")
    assert data["one_liner"] == "Uses {curly} braces in text"


@pytest.mark.parametrize("text", ["no json here", "```json\n{not valid}\n```", "{ unbalanced"])
def test_raises_on_garbage(text):
    with pytest.raises(MemoParseError):
        extract_json(text)


def test_schema_errors_are_parse_errors(memo_dict):
    del memo_dict["snapshot"]
    with pytest.raises(MemoParseError, match="schema"):
        parse_memo(json.dumps(memo_dict))


def test_rejects_non_http_source_urls(memo_dict):
    memo_dict["sources"][0]["url"] = "javascript:alert(1)"
    with pytest.raises(MemoParseError):
        parse_memo(json.dumps(memo_dict))


def test_audit_removes_dangling_citations(memo_dict):
    memo_dict["thesis"][0]["sources"] = [1, 99]
    memo, report = parse_memo(json.dumps(memo_dict))
    assert memo.thesis[0].sources == [1]
    assert any("99" in d for d in report.dangling)


def test_audit_flags_uncited_claims_but_not_unknowns(memo_dict):
    memo, report = parse_memo(json.dumps(memo_dict))
    assert "risks" in report.uncited                   # factual claim, no source
    assert "snapshot.funding" not in report.uncited    # "Unknown" is allowed without source


def test_audit_reports_unused_sources(memo_dict):
    memo_dict["sources"].append({"id": 3, "title": "Unused", "url": "https://x.example"})
    _, report = parse_memo(json.dumps(memo_dict))
    assert report.unused_sources == [3]


def test_duplicate_source_ids_rejected(memo_dict):
    memo_dict["sources"][1]["id"] = 1
    with pytest.raises(MemoParseError):
        parse_memo(json.dumps(memo_dict))


@pytest.mark.parametrize("name", ["stripe", "notion", "perplexity"])
def test_example_memos_are_valid_and_fully_linked(name):
    from conftest import EXAMPLES

    memo = Memo.model_validate_json((EXAMPLES / f"{name}.json").read_text())
    report = audit_citations(memo)
    assert not report.dangling
    assert not report.unused_sources
    assert len(memo.sources) >= 10
