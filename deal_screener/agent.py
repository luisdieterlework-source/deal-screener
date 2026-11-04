"""The research agent loop built on the Claude Agent SDK."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from deal_screener.config import Settings
from deal_screener.guardrails import Budget, BudgetExceededError
from deal_screener.models import Memo
from deal_screener.parsing import CitationReport, MemoParseError, parse_memo
from deal_screener.prompts import SYSTEM_PROMPT, build_repair_prompt, build_user_prompt
from deal_screener.render_md import render_markdown
from deal_screener.tools import build_research_server, normalize_url

FETCH_TOOL = "mcp__research__fetch_page"
SEARCH_TOOL = "WebSearch"


class AgentRunError(RuntimeError):
    """Raised when the agent run fails (API error, no usable memo)."""


@dataclass(frozen=True)
class ProgressEvent:
    """Something the UI/CLI can show while the agent works."""

    kind: str  # "start" | "search" | "fetch" | "note" | "blocked" | "parse" | "done"
    message: str


@dataclass
class ScreenResult:
    memo: Memo
    markdown: str
    citations: CitationReport
    tool_calls: int
    tokens: int
    cost_usd: float | None


ProgressCallback = Callable[[ProgressEvent], None]


def describe_tool_use(name: str, tool_input: dict[str, Any]) -> ProgressEvent:
    """Human-readable progress line for a tool call."""
    if name == SEARCH_TOOL:
        return ProgressEvent("search", f"Searching: {tool_input.get('query', '')}")
    if name == FETCH_TOOL:
        return ProgressEvent("fetch", f"Reading: {tool_input.get('url', '')}")
    return ProgressEvent("note", f"Tool: {name}")


def build_options(settings: Settings, budget: Budget, emit: ProgressCallback) -> Any:
    """Agent options: only search + fetch, budget hook, no local settings or file access."""
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

    async def guard(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        allowed, reason = budget.request_tool()
        if allowed:
            return {}
        emit(ProgressEvent("blocked", "Tool budget reached, asking the agent to write the memo."))
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    return ClaudeAgentOptions(
        model=settings.model,
        system_prompt=SYSTEM_PROMPT,
        tools=[SEARCH_TOOL],                      # built-in tools exposed to the model
        allowed_tools=[SEARCH_TOOL, FETCH_TOOL],  # auto-approved; everything else is denied
        mcp_servers={"research": build_research_server()},
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[guard])]},
        permission_mode="dontAsk",
        max_turns=settings.max_tool_calls + 10,   # backstop in case hooks are bypassed
        max_budget_usd=settings.max_budget_usd,
        setting_sources=[],                        # ignore any local Claude Code config
        env={"ANTHROPIC_API_KEY": settings.api_key},
    )


async def _run_turn(client: Any, prompt: str, budget: Budget, emit: ProgressCallback) -> tuple[str, float | None]:
    """Send one prompt and stream the response. Returns (final_text, cost_usd)."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

    await client.query(prompt)
    texts: list[str] = []
    final: str | None = None
    cost: float | None = None
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            if msg.error:
                raise AgentRunError(f"Model API error: {msg.error}")
            budget.add_usage(msg.usage, msg.message_id)
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    emit(describe_tool_use(block.name, block.input))
                elif isinstance(block, TextBlock) and block.text.strip():
                    texts.append(block.text)
            try:
                budget.check_tokens()
            except BudgetExceededError:
                await client.interrupt()
                raise
        elif isinstance(msg, ResultMessage):
            cost = msg.total_cost_usd
            if msg.is_error:
                detail = "; ".join(msg.errors or []) or msg.subtype
                raise AgentRunError(f"Agent run failed: {detail}")
            final = msg.result
    return (final or (texts[-1] if texts else "")), cost


async def screen(
    url: str,
    company_name: str | None = None,
    settings: Settings | None = None,
    on_event: ProgressCallback | None = None,
    client_factory: Callable[[Any], Any] | None = None,
    today: dt.date | None = None,
) -> ScreenResult:
    """Research a company and return a validated, rendered memo.

    `client_factory` exists for tests: it receives the options and returns an object that
    behaves like `claude_agent_sdk.ClaudeSDKClient` (async context manager with
    `query`, `receive_response`, `interrupt`).
    """
    settings = settings or Settings.from_env()
    url = normalize_url(url)
    emit: ProgressCallback = on_event or (lambda _e: None)
    budget = Budget(max_tool_calls=settings.max_tool_calls, max_tokens=settings.max_tokens)
    options = build_options(settings, budget, emit)
    if client_factory is None:
        from claude_agent_sdk import ClaudeSDKClient

        client_factory = ClaudeSDKClient
    today_str = (today or dt.date.today()).isoformat()

    emit(ProgressEvent("start", f"Screening {url} with {settings.model}"))
    total_cost = 0.0
    async with client_factory(options) as client:
        text, cost = await _run_turn(client, build_user_prompt(url, company_name, today_str), budget, emit)
        total_cost += cost or 0.0
        try:
            memo, report = parse_memo(text)
        except MemoParseError as exc:
            emit(ProgressEvent("parse", "Memo JSON invalid, asking the agent to repair it."))
            text, cost = await _run_turn(client, build_repair_prompt(str(exc)), budget, emit)
            total_cost += cost or 0.0
            try:
                memo, report = parse_memo(text)
            except MemoParseError as exc2:
                raise AgentRunError(f"Agent did not return a valid memo: {exc2}") from exc2

    for warning in report.warnings:
        emit(ProgressEvent("note", warning))
    emit(ProgressEvent("done", f"Done: {budget.tool_calls} tool calls, ~{budget.tokens:,} tokens"))
    return ScreenResult(
        memo=memo,
        markdown=render_markdown(memo),
        citations=report,
        tool_calls=budget.tool_calls,
        tokens=budget.tokens,
        cost_usd=total_cost or None,
    )
