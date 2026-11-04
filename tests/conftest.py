"""Shared fixtures: a valid memo payload and a fake Agent SDK client."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

MINIMAL_MEMO: dict[str, Any] = {
    "company_name": "Acme Robotics",
    "website": "https://acme.example",
    "as_of": "2026-11-04",
    "one_liner": "Warehouse robots sold as a $2k/month subscription.",
    "snapshot": {
        "what_they_do": {"text": "Builds autonomous picking robots.", "sources": [1]},
        "business_model": {"text": "Robots-as-a-service subscription.", "sources": [1]},
        "customers": {"text": "Mid-size 3PL warehouses.", "sources": [2]},
        "stage": {"text": "Series A (2025).", "sources": [2]},
        "location": {"text": "Berlin, Germany.", "sources": [1]},
        "funding": {"text": "Unknown", "sources": []},
    },
    "market": [{"text": "Warehouse automation is growing fast.", "sources": [2]}],
    "competitors": [{"name": "Locus Robotics", "note": "Larger US incumbent.", "sources": [2]}],
    "thesis": [{"text": "Subscription pricing lowers adoption barriers.", "sources": [1]}],
    "risks": [{"text": "Hardware margins are thin.", "sources": []}],
    "acquirers": [{"name": "Zebra Technologies", "reason": "Adds robotics to its warehouse stack.", "sources": []}],
    "open_questions": ["What is the payback period per robot?"],
    "sources": [
        {"id": 1, "title": "Acme homepage", "url": "https://acme.example"},
        {"id": 2, "title": "Acme raises Series A", "url": "https://news.example/acme"},
    ],
}


@pytest.fixture
def memo_dict() -> dict[str, Any]:
    return copy.deepcopy(MINIMAL_MEMO)


@pytest.fixture
def memo_json_text(memo_dict: dict[str, Any]) -> str:
    return "Here is the memo:\n```json\n" + json.dumps(memo_dict) + "\n```"


class FakeClient:
    """Stands in for claude_agent_sdk.ClaudeSDKClient. Replays scripted turns.

    Each turn is a list of SDK message objects. Tool-use blocks are passed through the
    options' PreToolUse hook, like the real CLI would, so guardrails are exercised.
    """

    def __init__(self, options: Any, turns: list[list[Any]]):
        self.options = options
        self.turns = list(turns)
        self.prompts: list[str] = []
        self.hook_results: list[dict[str, Any]] = []
        self.interrupted = False

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def query(self, prompt: str) -> None:
        self.prompts.append(prompt)

    async def interrupt(self) -> None:
        self.interrupted = True

    async def receive_response(self):
        from claude_agent_sdk import AssistantMessage, ToolUseBlock

        hook = self.options.hooks["PreToolUse"][0].hooks[0]
        for msg in self.turns.pop(0):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        self.hook_results.append(await hook({"tool_name": block.name}, block.id, {}))
            yield msg
