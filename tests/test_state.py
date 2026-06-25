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


def test_set_active_plan_records_path(project):
    state.set_active_plan(project, "docs/plans/0003-thing.md")
    assert state.load(project)["active_plan"] == "docs/plans/0003-thing.md"


def test_set_active_plan_preserves_other_fields(project):
    """The dedicated writer must not clobber unrelated state (e.g. a green check)."""
    write(project, "src/app.py", "x = 1\n")
    state.record_pass(project, "check")
    state.set_active_plan(project, "docs/plans/0001-a.md")
    st = state.load(project)
    assert st["active_plan"] == "docs/plans/0001-a.md"
    assert st["last_check"] and st["last_check"]["passed"]  # still green


def test_save_is_atomic_no_temp_left_behind(project):
    """save() writes via a temp file + os.replace; on success no stray temp file
    is left in .forge/ and the state reads back intact."""
    state.set_active_plan(project, "docs/plans/0001-a.md")
    leftovers = [
        n
        for n in os.listdir(os.path.join(project, ".forge"))
        if n.startswith(".state-")
    ]
    assert leftovers == []
    assert state.load(project)["active_plan"] == "docs/plans/0001-a.md"


def test_save_cleans_up_temp_on_replace_failure(project, monkeypatch):
    """If the final os.replace fails, save() must not leave its temp file behind
    (and must propagate the error rather than swallow it)."""
    import lib.state as state_mod

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(state_mod.os, "replace", boom)
    try:
        state.set_active_plan(project, "docs/plans/0001-a.md")
    except OSError:
        pass
    leftovers = [
        n
        for n in os.listdir(os.path.join(project, ".forge"))
        if n.startswith(".state-")
    ]
    assert leftovers == []


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


def test_request_override_arms_sentinel_with_reason(project):
    state.request_override(project, "audit", "shipping a docs hotfix")
    # The sentinel exists and carries the reason for the audit trail.
    pending = state.pending_overrides(project)
    assert pending == {"audit": "shipping a docs hotfix"}
    # ...and it really is the file take_override consumes.
    taken = state.take_override(project, "audit")
    assert taken is not None and taken["reason"] == "shipping a docs hotfix"
    assert state.pending_overrides(project) == {}  # consumed


def test_request_override_tolerates_empty_reason(project):
    state.request_override(project, "check")
    assert state.pending_overrides(project) == {"check": ""}


def test_pending_overrides_lists_each_armed_gate(project):
    state.request_override(project, "check", "a")
    state.request_override(project, "uv", "b")
    assert state.pending_overrides(project) == {"check": "a", "uv": "b"}


def test_pending_overrides_empty_without_forge_dir(tmp_path):
    # No .forge/ at all → nothing armed, no crash.
    assert state.pending_overrides(str(tmp_path)) == {}
