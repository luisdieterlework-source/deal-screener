import pytest

from deal_screener.config import ConfigError, MissingApiKeyError, Settings
from deal_screener.guardrails import Budget, BudgetExceededError


def test_tool_budget_denies_after_limit():
    b = Budget(max_tool_calls=2, max_tokens=1_000)
    assert b.request_tool()[0] and b.request_tool()[0]
    allowed, reason = b.request_tool()
    assert not allowed and "Write the final memo" in reason
    assert b.tool_calls == 2


def test_tools_blocked_near_token_limit():
    b = Budget(max_tool_calls=100, max_tokens=1_000)
    b.add_usage({"input_tokens": 850})
    assert b.request_tool()[0] is False


def test_usage_dedup_and_cache_reads_ignored():
    b = Budget(max_tool_calls=5, max_tokens=10_000)
    usage = {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 9_999}
    b.add_usage(usage, "msg_1")
    b.add_usage(usage, "msg_1")  # same API response streamed as several blocks
    assert b.tokens == 160


def test_hard_token_limit_raises():
    b = Budget(max_tool_calls=5, max_tokens=100)
    b.add_usage({"output_tokens": 101})
    with pytest.raises(BudgetExceededError):
        b.check_tokens()


def test_invalid_budget():
    with pytest.raises(ValueError):
        Budget(max_tool_calls=0, max_tokens=10)


def test_missing_key_gives_clear_error():
    with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY is not set"):
        Settings.from_env({})


def test_settings_from_env_and_repr_hides_key():
    s = Settings.from_env({
        "ANTHROPIC_API_KEY": "sk-ant-secret", "DEAL_SCREENER_MODEL": "claude-x",
        "DEAL_SCREENER_MAX_TOOL_CALLS": "7", "DEAL_SCREENER_MAX_TOKENS": "5000",
        "DEAL_SCREENER_MAX_BUDGET_USD": "1.5",
    })
    assert (s.model, s.max_tool_calls, s.max_tokens, s.max_budget_usd) == ("claude-x", 7, 5000, 1.5)
    assert "sk-ant-secret" not in repr(s)


@pytest.mark.parametrize("value", ["abc", "-3", "0"])
def test_invalid_numbers_rejected(value):
    with pytest.raises(ConfigError):
        Settings.from_env({"ANTHROPIC_API_KEY": "k", "DEAL_SCREENER_MAX_TOOL_CALLS": value})
