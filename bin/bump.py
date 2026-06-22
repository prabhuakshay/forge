#!/usr/bin/env python3
"""Set the forge version in every file that records it, in one shot.

The version lives in three files that MUST agree: the plugin manifest
(`.claude-plugin/plugin.json`), the dev `pyproject.toml`, and the marketplace
manifest (`.claude-plugin/marketplace.json` — its top-level version AND every
plugin entry's version). A release that bumps some but not all of them ships an
inconsistent plugin, so the release checklist calls this single command instead
of hand-editing each file. stdlib-only, like everything under bin/.

Usage:
    bump.py <X.Y.Z>             # set an explicit version
    bump.py major|minor|patch   # bump the current version by that level
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGIN = os.path.join(ROOT, ".claude-plugin", "plugin.json")
MARKET = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
PYPROJECT = os.path.join(ROOT, "pyproject.toml")

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# The version *value* in a JSON `"version": "X"` field — every occurrence in the
# manifests is the plugin's version and should move together.
_JSON_VERSION = re.compile(r'("version"\s*:\s*)"[^"]*"')
# The `[project]` version line in pyproject (anchored to line start; no other
# top-level `version =` key exists).
_TOML_VERSION = re.compile(r'(?m)^(version\s*=\s*)"[^"]*"')


def current_version() -> str:
    with open(PLUGIN, encoding="utf-8") as fh:
        m = re.search(r'"version"\s*:\s*"([^"]+)"', fh.read())
    if not m:
        sys.exit("could not find a version in plugin.json")
    return m.group(1)


def resolve(arg: str, current: str) -> str:
    """Turn a CLI argument into the concrete new version string."""
    if _SEMVER.match(arg):
        return arg
    if arg in {"major", "minor", "patch"}:
        major, minor, patch = (int(p) for p in current.split("."))
        if arg == "major":
            return f"{major + 1}.0.0"
        if arg == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"
    sys.exit(f"expected X.Y.Z or major|minor|patch, got: {arg!r}")


def _sub(path: str, pattern: re.Pattern[str], new: str) -> int:
    """Rewrite every version field matched by `pattern` in `path`; return the
    count changed. Only the quoted value is touched, so file formatting and key
    order are preserved (and the JSON/TOML stays valid)."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    updated, n = pattern.subn(rf'\g<1>"{new}"', text)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    return n


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: bump.py <X.Y.Z | major | minor | patch>")
    current = current_version()
    new = resolve(sys.argv[1], current)

    fields = (
        _sub(PLUGIN, _JSON_VERSION, new)
        + _sub(MARKET, _JSON_VERSION, new)
        + _sub(PYPROJECT, _TOML_VERSION, new)
    )
    print(f"forge {current} -> {new}  ({fields} version fields across 3 files)")
    print("Next: run `uv lock`, update CHANGELOG.md, then commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
