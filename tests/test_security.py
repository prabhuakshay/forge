"""Tests for the security scanners (the audit gate's security checks).

The subprocess boundary and tool availability are monkeypatched so the parsing
and skip logic are asserted deterministically, without pip-audit/bandit installed.
"""

from __future__ import annotations

import json

from lib import security


# --- pip-audit JSON parsing -----------------------------------------------


def test_parse_pip_audit_object_form_with_fix():
    out = json.dumps(
        {
            "dependencies": [
                {"name": "foo", "version": "1.0", "vulns": []},
                {
                    "name": "bar",
                    "version": "2.1",
                    "vulns": [{"id": "PYSEC-1", "fix_versions": ["2.2"]}],
                },
            ]
        }
    )
    findings = security.parse_pip_audit(out)
    assert findings == ["bar 2.1: PYSEC-1 (fix: 2.2)"]


def test_parse_pip_audit_legacy_list_and_no_fix():
    out = json.dumps([{"name": "baz", "version": "0.1", "vulns": [{"id": "CVE-9"}]}])
    assert security.parse_pip_audit(out) == ["baz 0.1: CVE-9 (no fix available)"]


def test_parse_pip_audit_handles_garbage():
    assert security.parse_pip_audit("not json") == []


# --- bandit JSON parsing --------------------------------------------------

_BANDIT = json.dumps(
    {
        "results": [
            {
                "filename": "a.py",
                "line_number": 3,
                "issue_severity": "HIGH",
                "issue_confidence": "HIGH",
                "test_id": "B602",
                "issue_text": "subprocess with shell=True",
            },
            {
                "filename": "b.py",
                "line_number": 9,
                "issue_severity": "MEDIUM",
                "issue_confidence": "MEDIUM",
                "test_id": "B105",
                "issue_text": "possible hardcoded password",
            },
            {
                "filename": "c.py",
                "line_number": 1,
                "issue_severity": "LOW",
                "issue_confidence": "LOW",
                "test_id": "B404",
                "issue_text": "import subprocess",
            },
        ]
    }
)


def test_parse_bandit_advisory_keeps_medium_and_high():
    findings = security.parse_bandit(_BANDIT, high_only=False)
    assert len(findings) == 2  # LOW dropped
    assert any("a.py:3" in f for f in findings)
    assert any("b.py:9" in f for f in findings)


def test_parse_bandit_strict_keeps_only_high_high():
    findings = security.parse_bandit(_BANDIT, high_only=True)
    assert findings == [
        "a.py:3 [HIGH/HIGH] B602: subprocess with shell=True",
    ]


def test_parse_bandit_handles_garbage():
    assert security.parse_bandit("{bad", high_only=False) == []


# --- skip path when the tool is absent ------------------------------------


def test_scan_dependencies_skips_when_unavailable(monkeypatch, project):
    monkeypatch.setattr(security, "_available", lambda project_dir, tool: False)
    r = security.scan_dependencies(project)
    assert not r.available and not r.completed
    assert "pip-audit" in r.note


def test_scan_code_skips_when_unavailable(monkeypatch, project):
    monkeypatch.setattr(security, "_available", lambda project_dir, tool: False)
    r = security.scan_code(project)
    assert not r.available and not r.completed
    assert "bandit" in r.note


# --- strict-mode toggle ---------------------------------------------------


def test_strict_reads_env(monkeypatch):
    monkeypatch.delenv("FORGE_SECURITY_STRICT", raising=False)
    assert security.strict() is False
    monkeypatch.setenv("FORGE_SECURITY_STRICT", "1")
    assert security.strict() is True
    monkeypatch.setenv("FORGE_SECURITY_STRICT", "off")
    assert security.strict() is False


# --- bandit target selection ----------------------------------------------


def test_bandit_target_prefers_src(project, tmp_path):
    (tmp_path / "src").mkdir()
    targets, excludes = security._bandit_target(project)
    assert targets == ["src"] and excludes == []


def test_bandit_target_falls_back_to_root_with_excludes(project):
    targets, excludes = security._bandit_target(project)
    assert targets == ["."] and "./.venv" in excludes
