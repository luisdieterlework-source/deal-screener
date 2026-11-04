"""Command line entry point: `python -m deal_screener https://example.com`."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from deal_screener.agent import AgentRunError, ProgressEvent, screen
from deal_screener.config import ConfigError, Settings
from deal_screener.envfile import load_dotenv
from deal_screener.guardrails import BudgetExceededError
from deal_screener.models import Memo
from deal_screener.parsing import audit_citations
from deal_screener.render_md import render_markdown
from deal_screener.render_pdf import render_pdf
from deal_screener.tools import FetchError

ICONS = {"search": "🔎", "fetch": "📄", "blocked": "⛔", "parse": "🛠", "done": "✅", "start": "▶", "note": "•"}


def slugify(text: str) -> str:
    """Filesystem-safe slug, e.g. 'https://www.Stripe.com/' -> 'stripe-com'."""
    text = re.sub(r"^https?://(www\.)?", "", text.strip().lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "memo"


def write_outputs(memo: Memo, markdown: str, out_dir: Path, pdf: bool) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / slugify(memo.company_name or memo.website)
    paths = [stem.with_suffix(".md"), stem.with_suffix(".json")]
    paths[0].write_text(markdown, encoding="utf-8")
    paths[1].write_text(memo.model_dump_json(indent=2), encoding="utf-8")
    if pdf:
        paths.append(stem.with_suffix(".pdf"))
        paths[-1].write_bytes(render_pdf(memo))
    return paths


def _print_event(event: ProgressEvent) -> None:
    print(f"{ICONS.get(event.kind, '•')} {event.message}", file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deal_screener", description="Screen a company and write a sourced investment memo.")
    p.add_argument("url", nargs="?", help="company website, e.g. https://stripe.com")
    p.add_argument("--name", help="company name (optional, helps disambiguate)")
    p.add_argument("--out", default="memos", type=Path, help="output directory (default: memos/)")
    p.add_argument("--no-pdf", action="store_true", help="skip PDF output")
    p.add_argument("--render", type=Path, metavar="MEMO_JSON", help="re-render an existing memo JSON, no API call")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.render:
            memo = Memo.model_validate_json(args.render.read_text(encoding="utf-8"))
            for w in audit_citations(memo).warnings:
                print(f"• {w}", file=sys.stderr)
            markdown = render_markdown(memo)
        elif args.url:
            load_dotenv()
            result = asyncio.run(screen(args.url, args.name, Settings.from_env(), on_event=_print_event))
            memo, markdown = result.memo, result.markdown
        else:
            build_parser().print_usage(sys.stderr)
            return 2
    except (ConfigError, AgentRunError, BudgetExceededError, FetchError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for path in write_outputs(memo, markdown, args.out, pdf=not args.no_pdf):
        print(path)
    return 0
