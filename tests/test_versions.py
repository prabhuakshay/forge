"""Tests for version-agreement detection (the audit gate's version check).

The detector reads every place a project records its version and reports when they
disagree — the drift that ships a package whose own files contradict each other.
"""

from __future__ import annotations

import json

from conftest import write

from lib import versions

_PYPROJECT = '[project]\nname = "x"\nversion = "{v}"\n'


def test_no_sites_no_disagreement(project):
    assert versions.declared_versions(project) == []
    assert versions.disagreements(project) is None


def test_single_site_never_disagrees(project):
    write(project, "pyproject.toml", _PYPROJECT.format(v="1.2.3"))
    assert len(versions.declared_versions(project)) == 1
    assert versions.disagreements(project) is None


def test_agreeing_sites_pass(project):
    write(project, "pyproject.toml", _PYPROJECT.format(v="2.0.0"))
    write(project, "src/pkg/__init__.py", '__version__ = "2.0.0"\n')
    write(project, ".claude-plugin/plugin.json", json.dumps({"version": "2.0.0"}))
    assert versions.disagreements(project) is None


def test_pyproject_vs_package_mismatch(project):
    write(project, "pyproject.toml", _PYPROJECT.format(v="2.0.0"))
    write(project, "src/pkg/__init__.py", "__version__ = '1.9.0'\n")
    msg = versions.disagreements(project)
    assert msg and "2.0.0" in msg and "1.9.0" in msg


def test_nested_manifest_versions_are_collected(project):
    """A marketplace manifest has a top-level version AND per-plugin entries; all
    must be found so drift in any of them is caught."""
    write(project, "pyproject.toml", _PYPROJECT.format(v="0.10.0"))
    write(
        project,
        ".claude-plugin/marketplace.json",
        json.dumps({"version": "0.9.1", "plugins": [{"version": "0.9.1"}]}),
    )
    sites = versions.declared_versions(project)
    assert {s.version for s in sites} == {"0.10.0", "0.9.1"}
    assert "Version mismatch across 3 sites" in (versions.disagreements(project) or "")


def test_pyproject_section_scoped(project):
    """A `version` under a different table (e.g. [tool.poetry]) is not the
    canonical [project] version and must not be picked up."""
    write(
        project,
        "pyproject.toml",
        '[tool.poetry]\nversion = "9.9.9"\n\n[project]\nversion = "1.0.0"\n',
    )
    sites = versions.declared_versions(project)
    assert [s.version for s in sites] == ["1.0.0"]


def test_malformed_json_manifest_is_skipped(project):
    write(project, "pyproject.toml", _PYPROJECT.format(v="1.0.0"))
    write(project, ".claude-plugin/plugin.json", "{ not valid json ")
    # The bad manifest contributes no site; the lone pyproject can't disagree.
    assert versions.disagreements(project) is None
