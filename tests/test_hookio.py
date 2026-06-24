"""Tests for the hook stdin/stdout protocol helpers."""

from __future__ import annotations

import io
import json

import pytest

from lib import hookio


def test_read_input_parses_json(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"cwd": "/x"}'))
    assert hookio.read_input() == {"cwd": "/x"}


def test_read_input_tolerates_garbage(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    assert hookio.read_input() == {}  # fail open, never wedge the gated call
    # ...but non-empty unparseable input leaves a diagnostic trace on stderr.
    assert "unparseable" in capsys.readouterr().err


def test_read_input_empty_is_silent(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert hookio.read_input() == {}
    assert capsys.readouterr().err == ""  # empty stdin is normal, not an anomaly


def test_read_input_non_dict_json_becomes_empty(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2, 3]"))
    assert hookio.read_input() == {}  # callers expect a dict payload


def test_project_dir_defaults_to_cwd_marker():
    assert hookio.project_dir({}) == "."
    assert hookio.project_dir({"cwd": "/repo"}) == "/repo"


def test_allow_exits_zero():
    with pytest.raises(SystemExit) as exc:
        hookio.allow()
    assert exc.value.code == 0


def test_deny_emits_block_decision(capsys):
    with pytest.raises(SystemExit) as exc:
        hookio.deny("nope")
    assert exc.value.code == 0
    out = json.loads(capsys.readouterr().out)
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"] == "nope"


def test_block_stop_emits_block(capsys):
    with pytest.raises(SystemExit):
        hookio.block_stop("keep going")
    out = json.loads(capsys.readouterr().out)
    assert out == {"decision": "block", "reason": "keep going"}


def test_inject_context_shape(capsys):
    with pytest.raises(SystemExit):
        hookio.inject_context("SessionStart", "hello")
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert out["additionalContext"] == "hello"
