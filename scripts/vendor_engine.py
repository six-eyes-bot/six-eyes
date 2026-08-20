#!/usr/bin/env python3
"""Vendor TauricResearch/TradingAgents into engine/ at a pinned SHA.

Three subcommands, one rule set:

    vendor          copy upstream@PIN into engine/
    manifest        write engine/.vendored-manifest from upstream@PIN
    tooling-config  regenerate ruff/pytest exclusions FROM the manifest

The omission rules and the pin live here and nowhere else. If `vendor` and
`manifest` could disagree about which files are vendored, invariant 6 would
fail for a reason that has nothing to do with the thing it exists to catch.

WHY THE MANIFEST IS FETCHED, NOT WALKED
---------------------------------------
Generating the manifest from the local working tree is the obvious
implementation and it is wrong: after T6 adds first-party analyst nodes
*inside* engine/, re-running it would silently re-bless them as vendored and
exempt them from lint, typing and tests forever. So `manifest` downloads
upstream at the pinned SHA and hashes that. It FAILS CLOSED if upstream is
unreachable -- never falling back to the working tree.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE = REPO_ROOT / "engine"
MANIFEST = ENGINE / ".vendored-manifest"
VERSIONS = REPO_ROOT / "versions.lock"
PYPROJECT = REPO_ROOT / "pyproject.toml"

UPSTREAM = "TauricResearch/TradingAgents"

#: Directories dropped wholesale (matched against the upstream-relative path).
OMIT_DIRS = {
    "tests",     # a second top-level `tests` package -> mypy duplicate-module
                 # and pytest rootdir errors
    ".github",   # their CI is not ours
    "assets",    # 4.0 MB of README screenshots; 85% of the payload, zero function
}

#: Individual files dropped.
OMIT_FILES = {
    "pyproject.toml",           # uv treats a nested one as a workspace member;
                                # ruff resolves settings from the NEAREST one
    "requirements.txt",         # contains only "." -- installs the omitted pyproject
    "test.py",                  # root-level test script; module name `test`
    "conftest.py",
    ".gitignore",               # ours governs
    "Dockerfile",               # all three reference the omitted pyproject /
    "docker-compose.yml",       # requirements.txt, so they are broken by
    ".dockerignore",            # construction if vendored
    ".env.example",             # we ship our own; also keeps engine/ clear of
    ".env.enterprise.example",  # anything the CI secret-shaped-file check scans
}


def pinned_sha() -> str:
    """The pinned commit SHA, read from versions.lock. Never a tag or branch."""
    if not VERSIONS.exists():
        sys.exit(f"{VERSIONS.name} missing -- nothing is pinned")
    m = re.search(
        r"^tradingagents_sha\s*=\s*([0-9a-f]{40})\s*$", VERSIONS.read_text(), re.M
    )
    if not m:
        sys.exit(f"{VERSIONS.name}: no 40-char tradingagents_sha found")
    return m.group(1)


def is_vendored(rel: str) -> bool:
    """Does this upstream-relative path get vendored?"""
    parts = rel.split("/")
    if parts[0] in OMIT_DIRS:
        return False
    if rel in OMIT_FILES or parts[-1] in OMIT_FILES:
        return False
    # Defence in depth: never let an env-shaped file into a public repo,
    # whatever upstream adds later.
    if parts[-1].startswith(".env"):
        return False
    return True


def fetch(sha: str, dest: Path) -> Path:
    """Download and extract upstream@sha. Fails closed -- no working-tree fallback."""
    url = f"https://codeload.github.com/{UPSTREAM}/tar.gz/{sha}"
    tgz = dest / "upstream.tar.gz"
    # A bare python.org interpreter ships no CA roots, so verification fails
    # with CERTIFICATE_VERIFY_FAILED. certifi is in requirements.lock; use its
    # bundle when present. Never fall back to an unverified context -- this
    # code lands in a public repo at a pinned SHA and the TLS check is the
    # only thing making the pin mean anything.
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, timeout=60, context=ctx) as r, tgz.open("wb") as f:
            shutil.copyfileobj(r, f)
    except (urllib.error.URLError, TimeoutError, OSError, ssl.SSLError) as exc:
        sys.exit(
            f"FAILED CLOSED: could not fetch {UPSTREAM}@{sha[:12]} -- {exc}\n"
            "The manifest is generated from the pinned upstream SHA and never "
            "from the local working tree. Fix the network and re-run.\n"
            "If this is CERTIFICATE_VERIFY_FAILED, run under the venv "
            "(`make vendor-manifest` uses .venv/bin/python, which has certifi)."
        )
    with tarfile.open(tgz) as tar:
        # Refuse absolute/escaping members before extracting anything.
        for member in tar.getmembers():
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts:
                sys.exit(f"refusing unsafe tar member: {member.name}")
        tar.extractall(dest)  # noqa: S202 - members validated above
    root = dest / f"TradingAgents-{sha}"
    if not root.is_dir():
        sys.exit(f"unexpected archive layout: {root.name} not found")
    return root


def vendored_files(root: Path) -> list[tuple[str, Path]]:
    """[(repo-relative path, source path)] sorted, for everything we vendor."""
    out = []
    for src in sorted(root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(root).as_posix()
        if is_vendored(rel):
            out.append((f"engine/{rel}", src))
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest() -> dict[str, str]:
    """{repo-relative path: sha256}. The manifest defines what 'vendored' means."""
    if not MANIFEST.exists():
        sys.exit(f"{MANIFEST} missing -- run `make vendor-manifest`")
    entries = {}
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, path = line.partition(" ")
        entries[path.strip()] = digest
    return entries


# ---------------------------------------------------------------- subcommands


def cmd_vendor(_: argparse.Namespace) -> None:
    sha = pinned_sha()
    with tempfile.TemporaryDirectory() as td:
        root = fetch(sha, Path(td))
        files = vendored_files(root)
        # Clear ONLY the paths we are about to re-vendor. A blanket
        # rmtree(engine/) would delete the first-party analyst nodes T6 puts
        # *inside* engine/ -- the whole reason exclusions are enumerated.
        for rel, _src in files:
            stale = REPO_ROOT / rel
            if stale.exists():
                stale.unlink()
        for rel, src in files:
            dst = REPO_ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    print(f"vendored {len(files)} files from {UPSTREAM}@{sha[:12]} -> engine/")


def cmd_manifest(_: argparse.Namespace) -> None:
    sha = pinned_sha()
    with tempfile.TemporaryDirectory() as td:
        root = fetch(sha, Path(td))
        files = vendored_files(root)
        lines = [f"{sha256(src)} {rel}" for rel, src in files]
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        f"# Generated by `make vendor-manifest` from {UPSTREAM}@{sha}\n"
        "# sha256<space>path, hashed from the PINNED UPSTREAM, not the working tree.\n"
        "# Anything under engine/ NOT listed here is first-party and is linted,\n"
        "# typed and tested. Do not hand-edit.\n" + "\n".join(lines) + "\n"
    )
    print(f"manifest: {len(lines)} files from {UPSTREAM}@{sha[:12]}")


BEGIN = "# BEGIN vendored (generated by `make tooling-config`) -- do not hand-edit"
END = "# END vendored"


def _replace_block(text: str, key: str, body: str) -> str:
    """Rewrite the generated region inside `key = [...]`."""
    pat = re.compile(
        rf"(?P<head>^{re.escape(key)}\s*=\s*\[\n)"
        rf"(?P<body>.*?)"
        rf"(?P<tail>^\]$)",
        re.S | re.M,
    )
    if not pat.search(text):
        sys.exit(f"pyproject.toml: could not find a `{key} = [` block to regenerate")
    return pat.sub(lambda m: m.group("head") + body + m.group("tail"), text, count=1)


def vendored_modules(paths: list[str]) -> list[str]:
    """The module names mypy assigns to the vendored files.

    Asked of mypy's own resolver rather than reimplemented. Two hand-rolled
    rules were tried and both were wrong, in opposite directions:

      * "strip engine/, join with dots" mislabels
        engine/scripts/smoke_structured_output.py, which mypy calls
        `smoke_structured_output` -- `scripts` is dropped.
      * "climb while __init__.py exists" mislabels
        engine/tradingagents/agents/analysts/*.py, which mypy calls
        `tradingagents.agents.analysts.*` even though analysts/ has no
        __init__.py, because namespace_packages defaults to True.

    Getting it wrong is SILENT: a non-matching override simply never applies,
    the module stays checked, and the only signal is a warn_unused_configs
    note that does not fail the build.
    """
    try:
        from mypy.find_sources import create_source_list
        from mypy.options import Options
    except ImportError:  # pragma: no cover
        sys.exit(
            "tooling-config needs mypy's module resolver but mypy is not "
            "importable. Run `make setup` and use `make tooling-config`, "
            "which runs under .venv."
        )

    want = set(paths)
    found = set()
    for src in create_source_list([str(ENGINE)], Options()):
        if src.path is None:  # a namespace package with no file of its own
            continue
        rel = Path(src.path).resolve().relative_to(REPO_ROOT).as_posix()
        if rel in want:
            found.add(src.module)
    return sorted(found)


def cmd_tooling_config(_: argparse.Namespace) -> None:
    paths = sorted(read_manifest())

    excl = f"    {BEGIN}\n"
    excl += "".join(f'    "{p}",\n' for p in paths)
    excl += f"    {END}\n"

    # ENUMERATED module names, never `tradingagents.*`. A glob here would be
    # the ruff mistake through mypy's back door: T6's analyst nodes land in
    # engine/tradingagents/agents/analysts/, squarely inside that glob, and
    # would be born untyped with nothing reporting it.
    modules = vendored_modules(paths)
    mods = f"    {BEGIN}\n"
    mods += "".join(f'    "{m}",\n' for m in modules)
    mods += f"    {END}\n"

    text = PYPROJECT.read_text()
    text = _replace_block(text, "extend-exclude", excl)
    text = _replace_block(text, "module", mods)
    PYPROJECT.write_text(text)
    print(
        f"tooling-config: ruff extend-exclude <- {len(paths)} paths; "
        f"mypy ignore_errors <- {len(modules)} modules"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("vendor").set_defaults(fn=cmd_vendor)
    sub.add_parser("manifest").set_defaults(fn=cmd_manifest)
    sub.add_parser("tooling-config").set_defaults(fn=cmd_tooling_config)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
