"""Render a Memo as a compact PDF (reportlab, no system dependencies)."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from deal_screener.models import Claim, Memo
from deal_screener.parsing import is_uncited
from deal_screener.render_md import DISCLAIMER

ACCENT = colors.HexColor("#1f3a5f")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=8.5, leading=11)
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=16, leading=19, alignment=0, textColor=ACCENT, spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=10.5, leading=13, textColor=ACCENT, spaceBefore=7, spaceAfter=3),
        "body": body,
        "small": ParagraphStyle("small", parent=body, fontSize=7, leading=9, textColor=colors.HexColor("#555555")),
    }


def _cite(ids: list[int], memo: Memo) -> str:
    by_id = {s.id: s for s in memo.sources}
    return "".join(
        f' <link href="{escape(by_id[i].url)}" color="#1f5fa8">[{i}]</link>' for i in ids if i in by_id
    )


def _claim(claim: Claim, memo: Memo, bold_prefix: str = "") -> str:
    prefix = f"<b>{escape(bold_prefix)}</b> " if bold_prefix else ""
    flag = ' <font color="#b00020"><i>(unverified)</i></font>' if is_uncited(claim) else ""
    return f"{prefix}{escape(claim.text.strip())}{_cite(claim.sources, memo)}{flag}"


def _bullets(items: list[str], st: dict[str, ParagraphStyle], numbered: bool = False) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(t, st["body"]), leftIndent=10) for t in items],
        bulletType="1" if numbered else "bullet",
        start="1" if numbered else None,
        bulletFontSize=7 if not numbered else 8,
        leftIndent=10,
    )


def render_pdf(memo: Memo) -> bytes:
    """Return the memo as PDF bytes."""
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Screening memo: {memo.company_name}", author="Deal Screener",
    )
    s = memo.snapshot
    flow: list = [
        Paragraph(f"Investment Screening Memo: {escape(memo.company_name)}", st["title"]),
        Paragraph(f"{escape(memo.website)} · as of {escape(memo.as_of)}", st["small"]),
    ]
    if memo.one_liner:
        flow.append(Paragraph(f"<i>{escape(memo.one_liner)}</i>", st["body"]))
    flow += [Paragraph(escape(DISCLAIMER), st["small"]), Spacer(1, 3)]

    flow.append(Paragraph("1. Company Snapshot", st["h2"]))
    rows = [
        [Paragraph(f"<b>{label}</b>", st["body"]), Paragraph(_claim(c, memo), st["body"])]
        for label, c in [
            ("What they do", s.what_they_do), ("Business model", s.business_model),
            ("Customers", s.customers), ("Stage", s.stage), ("Funding", s.funding), ("Location", s.location),
        ]
    ]
    table = Table(rows, colWidths=[32 * mm, None])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#dddddd")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    flow.append(table)

    flow.append(Paragraph("2. Market and Competition", st["h2"]))
    items = [_claim(c, memo) for c in memo.market]
    items += [_claim(Claim(text=c.note, sources=c.sources), memo, f"{c.name}:") for c in memo.competitors]
    flow.append(_bullets(items or ["Unknown"], st))

    flow.append(Paragraph("3. Investment Thesis", st["h2"]))
    flow.append(_bullets([_claim(c, memo) for c in memo.thesis] or ["Unknown"], st))
    flow.append(Paragraph("4. Risks and Red Flags", st["h2"]))
    flow.append(_bullets([_claim(c, memo) for c in memo.risks] or ["Unknown"], st))

    flow.append(Paragraph("5. Potential Acquirers and Strategic Investors", st["h2"]))
    acq = [f"<b>{escape(a.name)}:</b> {escape(a.reason)}{_cite(a.sources, memo)}" for a in memo.acquirers]
    flow.append(_bullets(acq or ["Unknown"], st))

    flow.append(Paragraph("6. Open Questions for Management", st["h2"]))
    flow.append(_bullets([escape(q) for q in memo.open_questions] or ["(none)"], st, numbered=True))

    flow.append(Paragraph("7. Sources", st["h2"]))
    for src in sorted(memo.sources, key=lambda x: x.id):
        flow.append(Paragraph(
            f'[{src.id}] {escape(src.title)} <link href="{escape(src.url)}" color="#1f5fa8">{escape(src.url)}</link>',
            st["small"],
        ))
    doc.build(flow)
    return buf.getvalue()
