from deal_screener.models import Memo
from deal_screener.render_md import esc, render_markdown
from deal_screener.render_pdf import render_pdf


def test_markdown_has_all_seven_sections(memo_dict):
    md = render_markdown(Memo.model_validate(memo_dict))
    for heading in [
        "## 1. Company Snapshot", "## 2. Market and Competition", "## 3. Investment Thesis",
        "## 4. Risks and Red Flags", "## 5. Potential Acquirers", "## 6. Open Questions", "## 7. Sources",
    ]:
        assert heading in md


def test_citations_link_to_source_urls(memo_dict):
    md = render_markdown(Memo.model_validate(memo_dict))
    assert "[[2]](https://news.example/acme)" in md
    assert "1. [Acme homepage](https://acme.example)" in md


def test_uncited_claims_are_flagged_unknowns_are_not(memo_dict):
    md = render_markdown(Memo.model_validate(memo_dict))
    assert "Hardware margins are thin. *(unverified)*" in md
    assert "| **Funding** | Unknown |" in md


def test_dollar_signs_escaped_for_markdown_math(memo_dict):
    md = render_markdown(Memo.model_validate(memo_dict))
    assert r"\$2k/month" in md
    assert esc(r"\$5") == r"\$5"  # idempotent


def test_empty_sections_say_unknown(memo_dict):
    memo_dict.update(market=[], thesis=[], competitors=[], acquirers=[])
    md = render_markdown(Memo.model_validate(memo_dict))
    assert md.count("Unknown: no reliable public information found.") == 2
    assert "no obvious strategic buyers" in md


def test_table_cells_cannot_break_on_pipes(memo_dict):
    memo_dict["snapshot"]["customers"]["text"] = "SMB | Enterprise"
    md = render_markdown(Memo.model_validate(memo_dict))
    assert "SMB / Enterprise" in md


def test_pdf_renders_and_is_deterministic(memo_dict):
    memo = Memo.model_validate(memo_dict)
    pdf = render_pdf(memo)
    assert pdf.startswith(b"%PDF")
    assert pdf == render_pdf(memo)


def test_pdf_escapes_markup(memo_dict):
    memo_dict["risks"][0]["text"] = "Margins <b>& stuff</b> unclear"
    assert render_pdf(Memo.model_validate(memo_dict)).startswith(b"%PDF")
