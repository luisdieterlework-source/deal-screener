"""Runtime settings, read from environment variables only."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_TOOL_CALLS = 25
DEFAULT_MAX_TOKENS = 400_000


class ConfigError(RuntimeError):
    """Raised when the environment is not configured correctly."""


class MissingApiKeyError(ConfigError):
    """Raised when ANTHROPIC_API_KEY is not set."""

    def __init__(self) -> None:
        super().__init__(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key, "
            "or run `export ANTHROPIC_API_KEY=sk-ant-...` before starting Deal Screener. "
            "On Streamlit Community Cloud, add it under App settings -> Secrets."
        )


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value


def _float_or_none(env: Mapping[str, str], name: str) -> float | None:
    raw = (env.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """All knobs for one screening run."""

    api_key: str
    model: str = DEFAULT_MODEL
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_budget_usd: float | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from environment variables; fail loudly if the key is missing."""
        env = os.environ if env is None else env
        api_key = (env.get("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            raise MissingApiKeyError()
        return cls(
            api_key=api_key,
            model=(env.get("DEAL_SCREENER_MODEL") or "").strip() or DEFAULT_MODEL,
            max_tool_calls=_int(env, "DEAL_SCREENER_MAX_TOOL_CALLS", DEFAULT_MAX_TOOL_CALLS),
            max_tokens=_int(env, "DEAL_SCREENER_MAX_TOKENS", DEFAULT_MAX_TOKENS),
            max_budget_usd=_float_or_none(env, "DEAL_SCREENER_MAX_BUDGET_USD"),
        )

    def __repr__(self) -> str:  # never leak the key into logs
        return (
            f"Settings(model={self.model!r}, max_tool_calls={self.max_tool_calls}, "
            f"max_tokens={self.max_tokens}, max_budget_usd={self.max_budget_usd})"
        )
