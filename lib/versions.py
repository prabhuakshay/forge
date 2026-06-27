"""Collect the version string a project declares in every place it records one,
so the audit gate can refuse to ship when they disagree.

A project's version is duplicated across files that MUST agree — `pyproject.toml`,
a package `__init__.py`'s `__version__`, and (for a Claude Code plugin repo) the
`.claude-plugin/` manifests. A release that bumps some but not all of them ships
an inconsistent artifact: the package says one version, the marketplace advertises
another. `bin/bump.py` writes them together, but nothing *verifies* they stayed
together — that's this module's job, read-only.

stdlib-only and tolerant of the project's deps being absent (it runs inside the
audit hook): TOML is parsed by a small line scanner (tomllib is 3.11+, forge
targets 3.10) and JSON via the stdlib. A file we can't read is simply skipped —
a missing site can't disagree.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass

# `__version__ = "1.2.3"` (single or double quotes) in a package init.
_DUNDER_VERSION = re.compile(r"""(?m)^__version__\s*=\s*['"]([^'"]+)['"]""")
# A `version = "..."` line (TOML). Used only after we've narrowed to [project].
_TOML_VERSION = re.compile(r"""^version\s*=\s*['"]([^'"]+)['"]""")


@dataclass(frozen=True)
class VersionSite:
    """One place a version string was found: a human label and the value."""

    source: str
    version: str


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _pyproject_version(project_dir: str) -> list[VersionSite]:
    """The `[project]` table's `version`, scoped to that section so a
    `[tool.poetry]` (or other) version table can't be misread as the canonical
    one. Returns at most one site."""
    text = _read(os.path.join(project_dir, "pyproject.toml"))
    if text is None:
        return []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section == "project":
            m = _TOML_VERSION.match(line)
            if m:
                return [VersionSite("pyproject.toml [project]", m.group(1))]
    return []


def _iter_json_versions(node: object, path: str) -> list[tuple[str, str]]:
    """Every string-valued `"version"` reachable in a parsed JSON document,
    each paired with a dotted path describing where it sits (so two versions in
    one manifest are told apart in the report)."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            sub = f"{path}.{key}" if path else key
            if key == "version" and isinstance(value, str):
                found.append((path or key, value))
            else:
                found.extend(_iter_json_versions(value, sub))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_iter_json_versions(value, f"{path}[{i}]"))
    return found


def _plugin_manifest_versions(project_dir: str) -> list[VersionSite]:
    """Every `"version"` in any `.claude-plugin/*.json` manifest — top-level and
    nested (e.g. a marketplace's per-plugin entries), which all describe the same
    plugin and must move together."""
    sites: list[VersionSite] = []
    manifest_dir = os.path.join(project_dir, ".claude-plugin")
    for path in sorted(glob.glob(os.path.join(manifest_dir, "*.json"))):
        text = _read(path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        name = os.path.relpath(path, project_dir)
        for where, ver in _iter_json_versions(data, ""):
            label = f"{name}:{where}" if where else name
            sites.append(VersionSite(label, ver))
    return sites


def _package_versions(project_dir: str) -> list[VersionSite]:
    """Any `__version__` declared in a `src/**/__init__.py`, the conventional
    home of a package's runtime version."""
    sites: list[VersionSite] = []
    pattern = os.path.join(project_dir, "src", "**", "__init__.py")
    for path in sorted(glob.glob(pattern, recursive=True)):
        text = _read(path)
        if text is None:
            continue
        m = _DUNDER_VERSION.search(text)
        if m:
            sites.append(VersionSite(os.path.relpath(path, project_dir), m.group(1)))
    return sites


def declared_versions(project_dir: str) -> list[VersionSite]:
    """Every version string the project declares, across all known sites."""
    return (
        _pyproject_version(project_dir)
        + _package_versions(project_dir)
        + _plugin_manifest_versions(project_dir)
    )


def disagreements(project_dir: str) -> str | None:
    """A human-readable message if the project declares its version in 2+ places
    and they don't all agree; None when they agree (or there's nothing to compare).

    A single site (or none) can't disagree, so it's never a problem — this check
    enforces *consistency*, not the presence of a version."""
    sites = declared_versions(project_dir)
    distinct = {s.version for s in sites}
    if len(sites) < 2 or len(distinct) < 2:
        return None
    detail = "; ".join(f"{s.source} = {s.version}" for s in sites)
    return f"Version mismatch across {len(sites)} sites: {detail}"
