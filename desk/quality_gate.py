"""Quality gate between the analysts and the bull/bear debate.

Recorded in internal-docs/SUPERSEDED.md as "added, with no ticket that owns
them" and folded into T7. The PATTERN is read from
`simonlin1212/TradingAgents-astock` (Apache-2.0) — grade each analyst report
and reject empty, too-short, or LLM-failure-marker outputs. No code is copied;
see internal-docs/LICENSES.md, which already records that if T7 adopts the
pattern it is attributed here and in this file.

Why it earns its place: a 14-node graph fails in the middle, not at the end.
An analyst that returns "I'm unable to retrieve that data" is not a bearish
signal, but a debate node reading it as prose will happily argue from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Phrases that mean the model failed, not that the news is bad. Matched
#: case-insensitively as whole phrases.
FAILURE_MARKERS: tuple[str, ...] = (
    "i cannot retrieve",
    "i can't retrieve",
    "unable to fetch",
    "unable to retrieve",
    "i do not have access",
    "i don't have access",
    "no data available",
    "as an ai language model",
    "i'm sorry, but i cannot",
)

#: Below this a report is not an analysis. Deliberately low: the gate is meant
#: to catch failures, not to enforce verbosity.
MIN_CHARS = 120


@dataclass(frozen=True)
class Grade:
    agent: str
    passed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.passed


def grade(agent: str, report: str | None) -> Grade:
    if report is None or not report.strip():
        return Grade(agent, False, "empty report")

    text = report.strip()
    lowered = text.lower()
    for marker in FAILURE_MARKERS:
        if marker in lowered:
            return Grade(agent, False, f"LLM failure marker: {marker!r}")

    if len(text) < MIN_CHARS:
        return Grade(agent, False, f"too short: {len(text)} chars < {MIN_CHARS}")

    # A report that is only a restatement of the ticker and no numbers is a
    # non-answer dressed as one.
    if not re.search(r"\d", text):
        return Grade(agent, False, "no numeric content")

    return Grade(agent, True)


def grade_all(reports: dict[str, str | None]) -> dict[str, Grade]:
    return {agent: grade(agent, text) for agent, text in sorted(reports.items())}


def rejected(grades: dict[str, Grade]) -> dict[str, Grade]:
    return {a: g for a, g in grades.items() if not g.passed}
