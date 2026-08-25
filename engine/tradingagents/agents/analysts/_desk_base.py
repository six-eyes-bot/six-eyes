"""Shared shape for the four analyst nodes T6 adds.

FIRST-PARTY CODE INSIDE engine/. These files are deliberately NOT in
engine/.vendored-manifest, so ruff lints them, mypy types them, and invariant
5 would fail if anyone added them to the exclusion list. That is the exact
scenario T1 refused a directory glob for: `extend-exclude = ["engine/**"]`
would have exempted this directory forever.

Dependency direction (VENDORING.md §4b): engine/ may import desk; desk must
never import engine. These import desk.data.

NO LLM CALLS. T6 produces the metric schedule; T7 wraps it in prose and a
verdict. Keeping the numbers deterministic means they can be tested without a
model, and it is DESK_DESIGN §1 W1's rule applied to W2: the LLM writes the
words, not the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Metric:
    """One number, with the provenance needed to audit it.

    `unavailable` is a first-class state. DESK_DESIGN lists metrics this
    project cannot source at its subscription tier, and reporting a plausible
    substitute for one of them would be the exact failure the whole data layer
    was built to prevent.
    """

    name: str
    value: float | None
    source: str
    unit: str = ""
    degraded: bool = False
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.value is not None

    def render(self) -> str:
        if not self.available:
            return f"{self.name}: UNAVAILABLE ({self.unavailable_reason})"
        flag = " [degraded]" if self.degraded else ""
        return f"{self.name}: {self.value:,.4g}{self.unit} ({self.source}){flag}"


@dataclass(frozen=True)
class AnalystReport:
    analyst: str
    ticker: str
    as_of: date
    metrics: tuple[Metric, ...] = field(default_factory=tuple)

    @property
    def available(self) -> tuple[Metric, ...]:
        return tuple(m for m in self.metrics if m.available)

    @property
    def missing(self) -> tuple[Metric, ...]:
        return tuple(m for m in self.metrics if not m.available)

    def render(self) -> str:
        head = f"{self.analyst} — {self.ticker} @ {self.as_of.isoformat()}"
        return "\n".join([head, *(f"  {m.render()}" for m in self.metrics)])


def unavailable(name: str, reason: str) -> Metric:
    return Metric(name=name, value=None, source="none", unavailable_reason=reason)
