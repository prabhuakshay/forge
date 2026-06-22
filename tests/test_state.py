"""Tests for the workflow-state and fingerprint layer."""

from __future__ import annotations

import os

from conftest import write
from lib import state


def test_load_returns_skeleton_when_absent(project):
    st = state.load(project)
    assert st["last_check"] is None
    assert st["dirty_py"] == []
    assert st["overrides"] == []


def test_load_tolerates_corrupt_json(project):
    write(project, ".forge/state.json", "{not json")
    assert state.load(project)["last_check"] is None


def test_fingerprint_is_stable_across_mtime_change(project):
    """The whole point of content hashing: touching a file (new mtime, same
    bytes) must NOT change the fingerprint, so a branch switch / checkout can't
    spuriously invalidate a green gate."""
    p = write(project, "src/app.py", "x = 1\n")
    before = state.code_fingerprint(project)
    os.utime(p, (10**9, 10**9))  # rewind mtime far into the past
    assert state.code_fingerprint(project) == before


def test_fingerprint_changes_on_content_change(project):
    write(project, "src/app.py", "x = 1\n")
    before = state.code_fingerprint(project)
    write(project, "src/app.py", "x = 2\n")
    assert state.code_fingerprint(project) != before


def test_fingerprint_changes_on_rename(project):
    write(project, "src/a.py", "x = 1\n")
    before = state.code_fingerprint(project)
    os.rename(os.path.join(project, "src/a.py"), os.path.join(project, "src/b.py"))
    assert state.code_fingerprint(project) != before


def test_fingerprint_ignores_vendor_dirs(project):
    write(project, "src/app.py", "x = 1\n")
    before = state.code_fingerprint(project)
    write(project, ".venv/lib/dep.py", "junk = 1\n")
    assert state.code_fingerprint(project) == before


def test_record_pass_then_is_current(project):
    write(project, "src/app.py", "x = 1\n")
    assert not state.is_current(project, "check")
    state.record_pass(project, "check")
    assert state.is_current(project, "check")


def test_edit_breaks_is_current(project):
    write(project, "src/app.py", "x = 1\n")
    state.record_pass(project, "check")
    write(project, "src/app.py", "x = 2\n")
    assert not state.is_current(project, "check")


def test_invalidate_drops_pass(project):
    write(project, "src/app.py", "x = 1\n")
    state.record_pass(project, "check")
    state.invalidate(project, "check")
    assert not state.is_current(project, "check")


def test_dirty_tracking(project):
    write(project, "src/a.py", "")
    write(project, "src/b.py", "")
    state.add_dirty(project, "src/a.py")
    state.add_dirty(project, "src/a.py")  # idempotent
    state.add_dirty(project, "src/b.py")
    assert state.dirty_files(project) == ["src/a.py", "src/b.py"]


def test_dirty_files_drops_deleted(project):
    write(project, "src/a.py", "")
    state.add_dirty(project, "src/a.py")
    state.add_dirty(project, "src/gone.py")  # never created
    assert state.dirty_files(project) == ["src/a.py"]


def test_record_check_pass_clears_dirty(project):
    write(project, "src/a.py", "x = 1\n")
    state.add_dirty(project, "src/a.py")
    state.record_pass(project, "check")
    assert state.dirty_files(project) == []


def test_record_audit_pass_keeps_dirty(project):
    """audit is a non-code gate; it must not clear the code dirty set."""
    write(project, "src/a.py", "x = 1\n")
    state.add_dirty(project, "src/a.py")
    state.record_pass(project, "audit")
    assert state.dirty_files(project) == ["src/a.py"]


def test_override_is_one_shot_and_logged(project):
    flag = os.path.join(project, ".forge", "override-check")
    with open(flag, "w", encoding="utf-8") as fh:
        fh.write("hotfix: prod down")

    taken = state.take_override(project, "check")
    assert taken is not None and taken["reason"] == "hotfix: prod down"
    assert not os.path.exists(flag)  # consumed
    assert state.take_override(project, "check") is None  # only once

    overrides = state.load(project)["overrides"]
    assert overrides and overrides[-1]["gate"] == "check"
