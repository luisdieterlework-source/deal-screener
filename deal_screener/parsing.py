"""Turn the agent's final text into a validated Memo and audit its citations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from deal_screener.models import Claim, Memo

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class MemoParseError(ValueError):
    """Raised when the agent output cannot be turned into a Memo."""


def extract_json(text: str) -> dict[str, Any]:
    """Return the JSON object in `text`, preferring the last ```json fenced block.

    Falls back to the outermost balanced {...} span so that unfenced output still parses.
    """
    candidates = _FENCE_RE.findall(text)
    if not candidates:
        span = _outermost_object(text)
        if span is None:
            raise MemoParseError("no JSON object found in agent output")
        candidates = [span]
    last_error: Exception | None = None
    for raw in reversed(candidates):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(data, dict):
            return data
    raise MemoParseError(f"agent output contained invalid JSON: {last_error}")


def _outermost_object(text: str) -> str | None:
    """Find the first balanced {...} span, ignoring braces inside JSON strings."""
    start = text.find("{")
    if start == -1:
        return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


@dataclass
class CitationReport:
    """Result of checking that every claim points at a real source."""

    dangling: list[str] = field(default_factory=list)   # cited ids that do not exist (removed)
    uncited: list[str] = field(default_factory=list)    # factual claims without any source
    unused_sources: list[int] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        out = [f"Removed citation to non-existent source {d}" for d in self.dangling]
        out += [f"Claim without source in {u}" for u in self.uncited]
        out += [f"Source [{i}] is listed but never cited" for i in self.unused_sources]
        return out


def audit_citations(memo: Memo) -> CitationReport:
    """Strip citations to unknown source ids (in place) and report uncited claims."""
    report = CitationReport()
    valid = {s.id for s in memo.sources}

    def clean(label: str, ids: list[int]) -> list[int]:
        kept = [i for i in ids if i in valid]
        report.dangling += [f"[{i}] in {label}" for i in ids if i not in valid]
        return kept

    for label, claim in memo.all_claims():
        if label.startswith("competitors."):
            continue  # handled below on the real objects
        claim.sources = clean(label, claim.sources)
        if not claim.sources and not claim.is_unknown:
            report.uncited.append(label)
    for comp in memo.competitors:
        comp.sources = clean(f"competitors.{comp.name}", comp.sources)
        if not comp.sources:
            report.uncited.append(f"competitors.{comp.name}")
    for acq in memo.acquirers:
        acq.sources = clean(f"acquirers.{acq.name}", acq.sources)
    report.unused_sources = sorted(valid - memo.referenced_source_ids())
    return report


def parse_memo(text: str) -> tuple[Memo, CitationReport]:
    """Parse and validate agent output. Raises MemoParseError with a readable message."""
    data = extract_json(text)
    try:
        memo = Memo.model_validate(data)
    except ValidationError as exc:
        raise MemoParseError(f"memo JSON does not match the schema: {exc}") from exc
    return memo, audit_citations(memo)


def is_uncited(claim: Claim) -> bool:
    """True for a factual claim that has no supporting source."""
    return not claim.sources and not claim.is_unknown
