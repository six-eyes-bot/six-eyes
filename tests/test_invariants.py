"""Invariants that must hold for the whole life of this repository.

This is deliberately not a placeholder. Every assertion here encodes a decision
from internal-docs/adr/0001-dependency-selection.md that a future `pip install`
could silently undo. `make test` green should mean something.

Stage A ships invariants 1-4 and 7. Stage B adds 5, 6 and 8 (vendored-engine
manifest integrity), which cannot exist before engine/ does.
"""

from __future__ import annotations

import re
from importlib.metadata import distributions
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCKFILE = REPO_ROOT / "requirements.lock"

#: Per ADR 0001. `openbb` is AGPL-3.0-only and serves zero required metrics the
#: direct providers do not. `backtrader` (GPLv3+) and `redis` arrive only from
#: an unused declaration in the vendored engine's pyproject and are stripped.
BANNED_DISTRIBUTIONS = {"openbb", "openbb-mcp-server", "backtrader", "redis"}

RUNTIME_IMPORTS = [
    "yfinance",
    "finvizfinance",
    "financetoolkit",
    "litellm",
    "langfuse",
    "pydantic",
    "yaml",
]

_COPYLEFT = re.compile(r"\b(?:A?GPL|GNU (?:Affero )?General Public)", re.IGNORECASE)
#: LGPL is weak copyleft and does not bind us for ordinary dynamic use.
_LGPL = re.compile(r"\bLGPL|Lesser General Public", re.IGNORECASE)


def _licence_facts(dist) -> tuple[str | None, str | None, list[str]]:
    """The three places a licence can hide. Reading only one is how you miss it."""
    md = dist.metadata
    return (
        md.get("License-Expression"),
        md.get("License"),
        [c for c in md.get_all("Classifier") or [] if c.startswith("License ::")],
    )


#: A declaration is short ("GPL-3.0-or-later", "BSD"). Anything longer is the
#: full licence *text* bundled into the metadata field, and grepping prose for
#: "GPL" finds discussion of the GPL, not a declaration of it.
#: Measured: pandas 3.0.5 ships a 52,990-character License field containing the
#: PSF licence, whose GPL-compatibility discussion matched a naive regex and
#: flagged a BSD-3-Clause package as copyleft.
MAX_DECLARATION_CHARS = 200


def _verdict(text: str) -> bool:
    return bool(_COPYLEFT.search(text)) and not _LGPL.search(text)


def is_strong_copyleft(
    license_expression: str | None,
    license_field: str | None,
    classifiers: list[str],
) -> bool | None:
    """True / False / None-for-unknown, by source precedence.

    Structured metadata is authoritative and free text is a last resort:

      1. `License-Expression` (PEP 639) — authoritative if present. A
         classifier-only check misses these entirely: PEP 639 packages emit
         `License-Expression: GPL-3.0-or-later` and often carry no classifier,
         so a real GPL wheel would pass.
      2. Trove classifiers — authoritative if present. Any single copyleft
         classifier is enough; dual-licensed packages are treated conservatively.
      3. The legacy `License` field — only when it is short enough to be a
         declaration rather than embedded licence text.

    Returns None when nothing usable is declared. That is *unknown, not clean*;
    the caller decides. Recorded as policy in internal-docs/LICENSES.md.
    """
    if license_expression:
        return _verdict(license_expression)
    if classifiers:
        return any(_verdict(c) for c in classifiers)
    if license_field and len(license_field) <= MAX_DECLARATION_CHARS:
        return _verdict(license_field)
    return None


# --------------------------------------------------------------------------
# 1. every runtime dependency imports
# --------------------------------------------------------------------------
@pytest.mark.parametrize("module", RUNTIME_IMPORTS)
def test_runtime_dependency_imports(module: str) -> None:
    __import__(module)


# --------------------------------------------------------------------------
# 2. installed versions match the lockfile
# --------------------------------------------------------------------------
def test_installed_versions_match_lockfile() -> None:
    assert LOCKFILE.exists(), f"{LOCKFILE.name} missing — `make lock` has not been run"
    installed = {d.metadata["Name"].lower().replace("_", "-"): d.version
                 for d in distributions() if d.metadata["Name"]}
    pinned: dict[str, str] = {}
    for raw in LOCKFILE.read_text().splitlines():
        line = raw.split("#")[0].strip().rstrip("\\").strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)==([^\s;]+)", line)
        if m:
            pinned[m.group(1).lower().replace("_", "-")] = m.group(2)
    assert pinned, "lockfile parsed to zero pins — the parser or the file is wrong"

    drift = {
        name: (want, installed[name])
        for name, want in pinned.items()
        if name in installed and installed[name] != want
    }
    assert not drift, "installed versions drifted from the lockfile: " + ", ".join(
        f"{n} locked {w} but installed {g}" for n, (w, g) in sorted(drift.items())
    )


# --------------------------------------------------------------------------
# 3. no strong-copyleft distribution in the resolved environment
# --------------------------------------------------------------------------
def test_no_strong_copyleft_distributions() -> None:
    offenders, unknown = [], []
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        verdict = is_strong_copyleft(*_licence_facts(dist))
        if verdict is True:
            offenders.append(f"{name} {dist.version}")
        elif verdict is None:
            unknown.append(name)
    assert not offenders, (
        "GPL/AGPL distribution(s) in the environment: " + ", ".join(sorted(offenders))
        + ". This repository is public; see ADR 0001."
    )
    # `unknown` is intentionally not an assertion failure — a great many
    # well-behaved packages declare nothing. It is surfaced so the count cannot
    # quietly grow unnoticed.
    print(f"\n  [licence] {len(unknown)} distribution(s) declare no licence metadata")


# --------------------------------------------------------------------------
# 4. banned distributions are absent
# --------------------------------------------------------------------------
def test_banned_distributions_absent() -> None:
    present = {
        d.metadata["Name"].lower().replace("_", "-")
        for d in distributions()
        if d.metadata["Name"]
    }
    found = sorted(BANNED_DISTRIBUTIONS & present)
    assert not found, (
        f"banned distribution(s) installed: {found}. "
        "openbb is AGPL-3.0-only; backtrader is GPLv3+ and imported by nothing."
    )


# --------------------------------------------------------------------------
# 7. the mutation test — prove invariant 3 can actually fail
# --------------------------------------------------------------------------
class TestCopyleftDetectorCanFail:
    """Invariant 3 is only worth having if it detects what it claims to.

    A Done criterion that says "prove it fails" and is verified once by a human
    is a checkbox. These are the proof, and they run on every commit.
    """

    def test_detects_pep639_expression_with_no_classifier(self) -> None:
        # The false-negative class that a classifier-only check misses.
        assert is_strong_copyleft("GPL-3.0-or-later", None, []) is True

    def test_detects_agpl_expression(self) -> None:
        assert is_strong_copyleft("AGPL-3.0-only", None, []) is True

    def test_detects_classifier_only(self) -> None:
        assert is_strong_copyleft(
            None, None,
            ["License :: OSI Approved :: GNU General Public License v3 (GPLv3)"],
        ) is True

    def test_detects_legacy_license_field(self) -> None:
        assert is_strong_copyleft(None, "GPLv3+", []) is True

    def test_permissive_is_clean(self) -> None:
        assert is_strong_copyleft("MIT", None, []) is False
        assert is_strong_copyleft(
            None, None, ["License :: OSI Approved :: Apache Software License"]
        ) is False

    def test_lgpl_is_not_strong_copyleft(self) -> None:
        assert is_strong_copyleft("LGPL-3.0-or-later", None, []) is False

    def test_absent_metadata_is_unknown_not_clean(self) -> None:
        assert is_strong_copyleft(None, None, []) is None

    def test_bundled_licence_text_mentioning_gpl_is_not_a_declaration(self) -> None:
        """Regression: pandas 3.0.5 failed this check on 2026-08-19.

        Its License field is 52,990 chars of bundled text including the PSF
        licence, which says "GPL-compatible" and "unlike the GPL". Those are
        statements *about* the GPL. Its classifier says BSD.
        """
        bundled = (
            "Historically, most, but not all, Python releases have also been "
            "GPL-compatible. GPL-compatible doesn't mean that we're distributing "
            "Python under the GPL. All Python licenses, unlike the GPL, let you "
            "distribute a modified version without making your changes open source. "
        ) * 40
        assert len(bundled) > MAX_DECLARATION_CHARS
        assert is_strong_copyleft(
            None, bundled, ["License :: OSI Approved :: BSD License"]
        ) is False
        # and with no classifier to fall back on, it is unknown -- never a
        # false accusation drawn from prose
        assert is_strong_copyleft(None, bundled, []) is None

    def test_structured_metadata_wins_over_prose(self) -> None:
        # a genuine GPL expression is not excused by a permissive classifier
        assert is_strong_copyleft(
            "GPL-3.0-only", None, ["License :: OSI Approved :: MIT License"]
        ) is True
