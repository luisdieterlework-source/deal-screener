"""Streamlit web UI for Deal Screener. Run with: streamlit run app.py"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import streamlit as st

from deal_screener.agent import ProgressEvent, ScreenResult, screen
from deal_screener.cli import ICONS, slugify
from deal_screener.config import ConfigError, Settings
from deal_screener.envfile import load_dotenv
from deal_screener.models import Memo
from deal_screener.render_md import render_markdown
from deal_screener.render_pdf import render_pdf

EXAMPLES = Path(__file__).parent / "examples"

st.set_page_config(page_title="Deal Screener", page_icon="📊", layout="wide")


def _load_secrets_into_env() -> None:
    """Streamlit Cloud stores the key in st.secrets; the agent reads it from the env."""
    load_dotenv()
    try:
        for key in ("ANTHROPIC_API_KEY", "DEAL_SCREENER_MODEL", "DEAL_SCREENER_MAX_TOOL_CALLS",
                    "DEAL_SCREENER_MAX_TOKENS", "DEAL_SCREENER_MAX_BUDGET_USD"):
            if key in st.secrets and key not in os.environ:
                os.environ[key] = str(st.secrets[key])
    except FileNotFoundError:  # no secrets.toml locally
        pass


def show_memo(memo: Memo, markdown: str) -> None:
    slug = slugify(memo.company_name)
    c1, c2, _ = st.columns([1, 1, 4])
    c1.download_button("⬇ PDF", render_pdf(memo), f"{slug}.pdf", "application/pdf", use_container_width=True)
    c2.download_button("⬇ Markdown", markdown, f"{slug}.md", "text/markdown", use_container_width=True)
    st.markdown(markdown)


_load_secrets_into_env()
st.title("📊 Deal Screener")
st.caption("AI research agent that turns a company URL into a sourced one-page VC/PE screening memo.")

with st.sidebar:
    st.subheader("Example memos")
    st.caption("Produced during development, no API key needed.")
    for path in sorted(EXAMPLES.glob("*.json")):
        if st.button(path.stem.title(), use_container_width=True):
            st.session_state["result"] = Memo.model_validate_json(path.read_text(encoding="utf-8"))
    st.divider()
    st.caption("Not investment advice. Only public sources are used; unknowns are marked as unknown.")

with st.form("screen"):
    col_url, col_name = st.columns([3, 2])
    url = col_url.text_input("Company website", placeholder="https://example.com")
    name = col_name.text_input("Company name (optional)")
    submitted = st.form_submit_button("Screen", type="primary")

if submitted:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        st.error(str(exc))
        st.stop()
    if not url.strip():
        st.warning("Please enter a company website.")
        st.stop()
    with st.status(f"Researching {url} …", expanded=True) as status:
        def on_event(event: ProgressEvent) -> None:
            st.write(f"{ICONS.get(event.kind, '•')} {event.message}")

        try:
            result: ScreenResult = asyncio.run(screen(url, name or None, settings, on_event=on_event))
        except Exception as exc:  # surface any failure in the UI instead of a stack trace
            status.update(label="Screening failed", state="error")
            st.error(f"{type(exc).__name__}: {exc}")
            st.stop()
        cost = f", ${result.cost_usd:.2f}" if result.cost_usd else ""
        status.update(
            label=f"Done: {result.tool_calls} tool calls, ~{result.tokens:,} tokens{cost}",
            state="complete", expanded=False,
        )
    st.session_state["result"] = result.memo

memo = st.session_state.get("result")
if memo is not None:
    show_memo(memo, render_markdown(memo))
