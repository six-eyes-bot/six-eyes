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


def is_strong_copyleft(
    license_expression: str | None,
    license_field: str | None,
    classifiers: list[str],
) -> bool | None:
    """True / False / None for unknown.

    Reads all three metadata surfaces. A classifier-only check is not enough:
    PEP 639 packages emit `License-Expression: GPL-3.0-or-later` and frequently
    carry no Trove classifier at all, so a real GPL wheel would pass while a
    synthetic fixture written *with* a classifier "proves" the check works.

    Returns None when nothing is declared — that is *unknown, not clean*, and
    the caller decides. Recorded as policy in internal-docs/LICENSES.md.
    """
    haystacks = [h for h in (license_expression, license_field, *classifiers) if h]
    if not haystacks:
        return None
    for h in haystacks:
        if _LGPL.search(h):
            continue
        if _COPYLEFT.search(h):
            return True
    return False


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
