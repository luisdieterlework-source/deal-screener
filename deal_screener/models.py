"""Memo data model. The agent returns JSON in this shape; renderers turn it into Markdown/PDF."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

UNKNOWN_MARKERS = ("unknown", "not publicly disclosed", "not disclosed", "n/a")


class Claim(BaseModel):
    """A single statement plus the ids of the sources that support it."""

    text: str
    sources: list[int] = Field(default_factory=list)

    @property
    def is_unknown(self) -> bool:
        """True if the claim explicitly states that the information is unknown."""
        return self.text.strip().lower().startswith(UNKNOWN_MARKERS)


class Snapshot(BaseModel):
    """Section 1: who the company is."""

    what_they_do: Claim
    business_model: Claim
    customers: Claim
    stage: Claim
    location: Claim
    funding: Claim = Field(default_factory=lambda: Claim(text="Unknown"))


class Competitor(BaseModel):
    name: str
    note: str
    sources: list[int] = Field(default_factory=list)


class Acquirer(BaseModel):
    name: str
    reason: str
    sources: list[int] = Field(default_factory=list)


class Source(BaseModel):
    id: int
    title: str
    url: str

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"source url must be http(s): {v!r}")
        return v


class Memo(BaseModel):
    """The full one-page investment screening memo."""

    company_name: str
    website: str
    as_of: str
    one_liner: str = ""
    snapshot: Snapshot
    market: list[Claim] = Field(default_factory=list)
    competitors: list[Competitor] = Field(default_factory=list)
    thesis: list[Claim] = Field(default_factory=list)
    risks: list[Claim] = Field(default_factory=list)
    acquirers: list[Acquirer] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_source_ids(self) -> Memo:
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")
        return self

    def all_claims(self) -> list[tuple[str, Claim]]:
        """Every claim in the memo, labelled with its section, for citation checks."""
        s = self.snapshot
        out: list[tuple[str, Claim]] = [
            ("snapshot.what_they_do", s.what_they_do),
            ("snapshot.business_model", s.business_model),
            ("snapshot.customers", s.customers),
            ("snapshot.stage", s.stage),
            ("snapshot.location", s.location),
            ("snapshot.funding", s.funding),
        ]
        out += [("market", c) for c in self.market]
        out += [("thesis", c) for c in self.thesis]
        out += [("risks", c) for c in self.risks]
        out += [(f"competitors.{c.name}", Claim(text=c.note, sources=c.sources)) for c in self.competitors]
        return out

    def referenced_source_ids(self) -> set[int]:
        ids = {i for _, c in self.all_claims() for i in c.sources}
        ids |= {i for a in self.acquirers for i in a.sources}
        return ids
