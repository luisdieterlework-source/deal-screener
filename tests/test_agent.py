"""Agent loop tests with a fake SDK client: no network, no API key needed."""

import datetime as dt

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from conftest import FakeClient
from deal_screener.agent import AgentRunError, FETCH_TOOL, screen
from deal_screener.config import Settings
from deal_screener.guardrails import BudgetExceededError

SETTINGS = Settings(api_key="test-key", model="test-model", max_tool_calls=2, max_tokens=50_000)


def assistant(*blocks, usage=None, mid=None):
    return AssistantMessage(content=list(blocks), model="test-model", usage=usage, message_id=mid)


def result(text, is_error=False):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error,
                         num_turns=1, session_id="s", total_cost_usd=0.12, result=text)


def make_factory(turns, holder):
    def factory(options):
        holder["client"] = FakeClient(options, turns)
        return holder["client"]
    return factory


async def test_happy_path_emits_progress_and_renders(memo_json_text):
    turns = [[
        assistant(ToolUseBlock("t1", "WebSearch", {"query": "acme robotics funding"}), usage={"input_tokens": 1000}, mid="m1"),
        assistant(ToolUseBlock("t2", FETCH_TOOL, {"url": "https://acme.example"}), usage={"input_tokens": 2000}, mid="m2"),
        assistant(TextBlock(memo_json_text), usage={"output_tokens": 500}, mid="m3"),
        result(memo_json_text),
    ]]
    events, holder = [], {}
    res = await screen("acme.example", settings=SETTINGS, on_event=events.append,
                       client_factory=make_factory(turns, holder), today=dt.date(2026, 11, 4))
    assert res.memo.company_name == "Acme Robotics"
    assert "## 7. Sources" in res.markdown
    assert (res.tool_calls, res.tokens, res.cost_usd) == (2, 3500, 0.12)
    kinds = [e.kind for e in events]
    assert kinds[0] == "start" and "search" in kinds and "fetch" in kinds and kinds[-1] == "done"
    assert "https://acme.example" in holder["client"].prompts[0] and "2026-11-04" in holder["client"].prompts[0]


async def test_tool_calls_beyond_budget_are_denied(memo_json_text):
    tools = [assistant(ToolUseBlock(f"t{i}", "WebSearch", {"query": str(i)}), mid=f"m{i}") for i in range(3)]
    holder, events = {}, []
    await screen("https://acme.example", settings=SETTINGS, on_event=events.append,
                 client_factory=make_factory([tools + [result(memo_json_text)]], holder))
    hooks = holder["client"].hook_results
    assert hooks[:2] == [{}, {}]
    assert hooks[2]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert any(e.kind == "blocked" for e in events)


async def test_options_restrict_tools_and_pass_key(memo_json_text):
    holder = {}
    await screen("https://acme.example", settings=SETTINGS,
                 client_factory=make_factory([[result(memo_json_text)]], holder))
    opts = holder["client"].options
    assert opts.tools == ["WebSearch"]
    assert set(opts.allowed_tools) == {"WebSearch", FETCH_TOOL}
    assert opts.model == "test-model" and opts.env["ANTHROPIC_API_KEY"] == "test-key"


async def test_invalid_json_triggers_one_repair_turn(memo_json_text):
    holder = {}
    res = await screen("https://acme.example", settings=SETTINGS,
                       client_factory=make_factory([[result("oops, no json")], [result(memo_json_text)]], holder))
    assert res.memo.company_name == "Acme Robotics"
    assert "could not be parsed" in holder["client"].prompts[1]


async def test_gives_up_after_failed_repair():
    with pytest.raises(AgentRunError, match="valid memo"):
        await screen("https://acme.example", settings=SETTINGS,
                     client_factory=make_factory([[result("nope")], [result("still nope")]], {}))


async def test_token_limit_interrupts_run():
    holder = {}
    turns = [[assistant(TextBlock("thinking"), usage={"input_tokens": 60_000}, mid="m1"), result("x")]]
    with pytest.raises(BudgetExceededError):
        await screen("https://acme.example", settings=SETTINGS, client_factory=make_factory(turns, holder))
    assert holder["client"].interrupted


async def test_api_error_is_reported():
    with pytest.raises(AgentRunError, match="failed"):
        await screen("https://acme.example", settings=SETTINGS,
                     client_factory=make_factory([[result(None, is_error=True)]], {}))
