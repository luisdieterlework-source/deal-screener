"""Per-run budget: caps tool calls and tokens so a run can never loop or burn money unbounded."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class BudgetExceededError(RuntimeError):
    """Raised when a run blows through its hard token limit."""


@dataclass
class Budget:
    """Tracks tool calls and tokens for one run.

    Tool calls are a *soft* limit: once reached, further tool calls are denied and the
    agent is told to write the memo with what it has. Tokens are a *hard* limit: the run is
    aborted. At `wrap_up_ratio` of the token limit tools are denied as well, so the agent
    gets a chance to finish before the hard stop.
    """

    max_tool_calls: int
    max_tokens: int
    wrap_up_ratio: float = 0.8
    tool_calls: int = 0
    tokens: int = 0
    _seen_messages: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.max_tool_calls <= 0 or self.max_tokens <= 0:
            raise ValueError("budget limits must be positive")

    # --- tools -----------------------------------------------------------------
    def tools_exhausted(self) -> bool:
        return self.tool_calls >= self.max_tool_calls or self.tokens >= self.wrap_up_ratio * self.max_tokens

    def request_tool(self) -> tuple[bool, str]:
        """Register an attempted tool call. Returns (allowed, reason)."""
        if self.tools_exhausted():
            return False, (
                f"Research budget exhausted ({self.tool_calls}/{self.max_tool_calls} tool calls, "
                f"{self.tokens}/{self.max_tokens} tokens). Do not call more tools. Write the final "
                "memo JSON now using only the sources you already have; mark gaps as Unknown."
            )
        self.tool_calls += 1
        return True, ""

    # --- tokens ----------------------------------------------------------------
    def add_usage(self, usage: dict[str, Any] | None, message_id: str | None = None) -> None:
        """Add token usage from one API response. Duplicate message ids are counted once.

        Counts input + cache-creation + output tokens. Cache *reads* are excluded: they re-read
        the same context every turn and would inflate the count without adding real cost.
        """
        if not usage:
            return
        if message_id:
            if message_id in self._seen_messages:
                return
            self._seen_messages.add(message_id)
        self.tokens += sum(
            int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "output_tokens")
        )

    def check_tokens(self) -> None:
        if self.tokens > self.max_tokens:
            raise BudgetExceededError(
                f"Token limit exceeded: {self.tokens} > {self.max_tokens}. "
                "Raise DEAL_SCREENER_MAX_TOKENS or lower DEAL_SCREENER_MAX_TOOL_CALLS."
            )
