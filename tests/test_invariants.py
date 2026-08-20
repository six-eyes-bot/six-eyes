"""Invariants that must hold for the whole life of this repository.

This is deliberately not a placeholder. Every assertion here encodes a decision
from internal-docs/adr/0001-dependency-selection.md that a future `pip install`
could silently undo. `make test` green should mean something.

Stage A ships invariants 1-4 and 7. Stage B adds 5, 6 and 8 (vendored-engine
manifest integrity), which cannot exist before engine/ does.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tomllib
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


# ==========================================================================
# Stage B — the vendored engine
#
# These three exist because a vendored tree has two failure modes that no
# amount of care prevents: the quality gate quietly widening until it exempts
# first-party code, and vendored source being edited in place so our
# Apache-2.0 statement of changes silently stops being true.
# ==========================================================================

ENGINE = REPO_ROOT / "engine"
MANIFEST = ENGINE / ".vendored-manifest"


def _manifest() -> dict[str, str]:
    """{repo-relative path: sha256} from engine/.vendored-manifest."""
    assert MANIFEST.exists(), (
        f"{MANIFEST.relative_to(REPO_ROOT)} missing — run `make vendor-manifest`"
    )
    entries: dict[str, str] = {}
    for raw in MANIFEST.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, path = line.partition(" ")
        entries[path.strip()] = digest
    assert entries, "manifest parsed to zero entries — the parser or the file is wrong"
    return entries


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# 5. the derived exclusion lists still equal the manifest
# --------------------------------------------------------------------------
def test_exclusions_equal_manifest() -> None:
    """ruff's exclusions are DERIVED from the manifest and must not drift.

    The two directions mean opposite things and get different messages —
    conflating them is how you spend an afternoon on the wrong problem.
    """
    manifest = set(_manifest())
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    excluded = {
        p for p in cfg["tool"]["ruff"]["extend-exclude"] if p.startswith("engine/")
    }

    stale_config = sorted(manifest - excluded)
    over_excluded = sorted(excluded - manifest)

    assert not stale_config, (
        "STALE TOOLING CONFIG — vendored per the manifest but not excluded from "
        f"lint: {stale_config[:5]}{'...' if len(stale_config) > 5 else ''} "
        f"({len(stale_config)} file(s)). Run `make tooling-config`."
    )
    assert not over_excluded, (
        "OVER-EXCLUDED — excluded from lint but NOT vendored, so this is "
        f"first-party code that has been silently exempted: {over_excluded}. "
        "Never hand-edit extend-exclude; run `make tooling-config`."
    )


# --------------------------------------------------------------------------
# 6. every vendored file still matches its recorded hash
# --------------------------------------------------------------------------
def test_vendored_files_match_manifest_hashes() -> None:
    """Without this, an in-place edit to vendored source is invisible to CI —
    and our Apache-2.0 §4(b) statement of changes silently becomes false."""
    missing, modified = [], []
    for rel, want in sorted(_manifest().items()):
        path = REPO_ROOT / rel
        if not path.is_file():
            missing.append(rel)
        elif _sha256(path) != want:
            modified.append(rel)

    assert not missing, (
        f"vendored file(s) in the manifest but absent from the tree: {missing}. "
        "Run `make vendor-engine`, or regenerate the manifest if the pin moved."
    )
    assert not modified, (
        f"vendored file(s) EDITED IN PLACE: {modified}. Vendored source is "
        "byte-identical to upstream at the pinned SHA by construction. If the "
        "change is deliberate, record it in engine/PROVENANCE.md under 'Local "
        "changes' (Apache-2.0 §4(b)) and re-run `make vendor-manifest`."
    )


def test_engine_files_outside_the_manifest_are_first_party() -> None:
    """Not a failure — a census. Files under engine/ that the manifest does not
    claim are ours, and are linted, typed and tested. Printed so the set cannot
    grow unnoticed between reviews."""
    manifest = set(_manifest())
    on_disk = {
        p.relative_to(REPO_ROOT).as_posix()
        for p in ENGINE.rglob("*")
        if p.is_file() and p.name != ".vendored-manifest"
    }
    first_party = sorted(on_disk - manifest)
    print(f"\n  [engine] {len(first_party)} first-party file(s) under engine/: {first_party}")


# --------------------------------------------------------------------------
# 8. the mutation test — prove an unblessed file under engine/ IS linted
# --------------------------------------------------------------------------
def test_unblessed_file_under_engine_is_linted() -> None:
    """Invariant 5 compares two lists. This proves the lists do something.

    The failure this guards against is the one the whole enumerated-exclusion
    policy exists for: a directory glob would exempt every future file under
    engine/ — including T6's four analyst nodes, the highest-value net-new
    code in Track B — and nothing would ever report it.
    """
    ruff = REPO_ROOT / ".venv" / "bin" / "ruff"
    if not ruff.exists():  # pragma: no cover - depends on provisioning
        pytest.skip("ruff not installed; run `make setup`")

    canary = ENGINE / "_lint_canary_delete_me.py"
    assert not canary.exists(), "canary already present — a previous run leaked"
    # `import os` unused (F401) + a line well past line-length 100 (E501).
    canary.write_text("import os\n" + f"x = '{'y' * 130}'\n")
    try:
        # `ruff check .` is what `make lint` runs. Passing the path explicitly
        # would bypass extend-exclude and prove nothing.
        proc = subprocess.run(
            [str(ruff), "check", "."],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert proc.returncode != 0, (
            "ruff PASSED with a deliberately broken file at "
            f"{canary.relative_to(REPO_ROOT)}. The exclusion list is exempting "
            "files it should not — the gate has a hole in it."
        )
        assert canary.name in proc.stdout, (
            f"ruff failed, but not because of {canary.name}. Output:\n{proc.stdout}"
        )
    finally:
        canary.unlink()


def test_vendored_files_are_not_linted() -> None:
    """The converse of invariant 8, and the reason the exclusions exist at all.

    Asserted over the whole vendored set rather than one sample: the first
    attempt picked `engine/cli/__init__.py`, which is trivial enough to pass
    our config unmodified, so it proved nothing.
    """
    ruff = REPO_ROOT / ".venv" / "bin" / "ruff"
    if not ruff.exists():  # pragma: no cover
        pytest.skip("ruff not installed; run `make setup`")

    vendored_py = sorted(p for p in _manifest() if p.endswith(".py"))
    assert vendored_py, "no vendored .py files in the manifest — nothing to prove"

    # 1. Upstream genuinely does not satisfy our lint config, so the exemption
    #    is load-bearing rather than a coincidence of upstream being tidy.
    #    --no-force-exclude makes explicitly-named paths bypass the exclusion.
    direct = subprocess.run(
        [str(ruff), "check", "--no-force-exclude", *vendored_py],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert direct.returncode != 0, (
        "the entire vendored tree passes our lint config unmodified, so the "
        "exclusion list is not actually suppressing anything and this test "
        "cannot distinguish a working gate from a broken one."
    )

    # 2. And none of them are reported by the run `make lint` actually does.
    checked = subprocess.run(
        [str(ruff), "check", "."], cwd=REPO_ROOT, capture_output=True, text=True
    )
    leaked = sorted(f for f in vendored_py if f in checked.stdout)
    assert not leaked, (
        f"vendored file(s) reported by `ruff check .`: {leaked} — not excluded."
    )


# --------------------------------------------------------------------------
# 5b. the mypy exemption list is enumerated and matches the manifest
# --------------------------------------------------------------------------
def _mypy_vendor_overrides() -> list[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    for ov in cfg["tool"]["mypy"].get("overrides", []):
        if ov.get("ignore_errors"):
            mods = ov["module"]
            return [mods] if isinstance(mods, str) else list(mods)
    return []


def test_mypy_exemptions_are_enumerated_not_globbed() -> None:
    """A glob here is the ruff mistake through mypy's back door.

    `module = ["tradingagents.*"]` reads as the obvious way to exempt the
    vendored engine. It also exempts engine/tradingagents/agents/analysts/,
    which is exactly where T6's four analyst nodes go — so they would be born
    untyped and stay that way silently.
    """
    globbed = sorted(m for m in _mypy_vendor_overrides() if "*" in m)
    assert not globbed, (
        f"globbed mypy exemption(s): {globbed}. Exemptions must be exact "
        "module names derived from the manifest — run `make tooling-config`."
    )


def test_mypy_exemptions_match_manifest() -> None:
    """Every exempted module is a vendored file, and every vendored module is
    exempted. A module here that the manifest does not back is first-party code
    silently exempted from typing."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from vendor_engine import vendored_modules
    finally:
        sys.path.pop(0)

    expected = set(vendored_modules(sorted(_manifest())))
    actual = set(_mypy_vendor_overrides())
    assert expected, "mypy resolved zero vendored modules — the resolver call is wrong"

    assert not (expected - actual), (
        f"vendored module(s) not exempted: {sorted(expected - actual)[:5]} — "
        "run `make tooling-config`."
    )
    assert not (actual - expected), (
        f"module(s) exempted from typing but NOT vendored: "
        f"{sorted(actual - expected)} — first-party code must stay typed."
    )


def test_a_new_file_under_engine_is_type_checked() -> None:
    """Invariant 8's typing analogue, at the exact path T6 will use.

    Placed inside engine/tradingagents/agents/analysts/ deliberately: that is
    the directory a `tradingagents.*` glob would have swallowed.
    """
    mypy_bin = REPO_ROOT / ".venv" / "bin" / "mypy"
    if not mypy_bin.exists():  # pragma: no cover
        pytest.skip("mypy not installed; run `make setup`")

    target_dir = ENGINE / "tradingagents" / "agents" / "analysts"
    assert target_dir.is_dir(), "expected T6's analyst directory to exist"
    canary = target_dir / "_type_canary_delete_me.py"
    assert not canary.exists(), "canary already present — a previous run leaked"
    canary.write_text("def f() -> int:\n    return 'not an int'\n")
    try:
        proc = subprocess.run(
            [str(mypy_bin), "--follow-imports=skip", "--no-incremental", str(canary)],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert proc.returncode != 0, (
            f"mypy PASSED a deliberate type error at "
            f"{canary.relative_to(REPO_ROOT)}. A new first-party file under "
            "engine/ is being exempted — the typing gate has a hole in it.\n"
            f"{proc.stdout}"
        )
        assert "_type_canary_delete_me" in proc.stdout, (
            f"mypy failed, but not on the canary:\n{proc.stdout}"
        )
    finally:
        canary.unlink()
