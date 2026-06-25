"""Workflow state: what phase we're in, and whether the gates are currently green.

The whole enforcement model rests on one question a hook can answer cheaply:
"has the code changed since the last green check?" We answer it by fingerprinting
the source tree and comparing against the fingerprint recorded when a gate last
passed. If they match, the green result still holds; if not, the gate is stale
and must run again before commit/release.

We also track the set of source files edited since the last green check (the
"dirty" set), so the Stop hook can type-check only what changed instead of the
whole tree on every turn.

State lives in <project>/.forge/state.json. It is intentionally a plain JSON
file (not git-tracked metadata) so it survives across sessions and is trivial to
inspect or reset by hand.

Every read-modify-write of that file is serialised under a POSIX advisory lock
(see `locked`), because Claude Code can run tools — and therefore hooks —
concurrently, and two updaters racing on load→mutate→save would let the second
`os.replace` silently drop the first's change. That dependency on `fcntl` is why
forge is POSIX-only (Linux/macOS); Windows is not supported.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

# The source-tree fingerprint lives in its own dependency-free module; re-exported
# here (code_fingerprint) since callers reach it through `state`.
from lib.fingerprint import STATE_DIRNAME, code_fingerprint

STATE_FILENAME = "state.json"

# Local-only (gitignored) lock file guarding the read-modify-write of state.json.
LOCK_FILENAME = ".state.lock"

# The gates that accept a one-shot override sentinel (.forge/override-<gate>).
# Kept here so the /forge:override CLI and the status report agree on the set.
OVERRIDE_GATES = ("check", "audit", "review", "stop", "plan", "uv")

__all__ = ["STATE_DIRNAME", "code_fingerprint"]  # re-exports used by callers


def _state_path(project_dir: str) -> str:
    return os.path.join(project_dir, STATE_DIRNAME, STATE_FILENAME)


@contextlib.contextmanager
def locked(project_dir: str) -> Iterator[None]:
    """Serialise a load→mutate→save sequence across concurrent processes.

    Wraps the body in an exclusive POSIX advisory lock held on a sibling
    `.forge/.state.lock` file, so two hooks firing at once can't each read the
    same state, change different fields, and have the second write clobber the
    first (a lost dirty-set entry, or — worse — a missing override-trail record).
    The lock is per open-file-description, so callers must NOT nest `locked`
    blocks in one thread: that would deadlock waiting on a lock the same thread
    already holds. Every mutator below takes the lock exactly once.
    """
    os.makedirs(os.path.join(project_dir, STATE_DIRNAME), exist_ok=True)
    fd = os.open(
        os.path.join(project_dir, STATE_DIRNAME, LOCK_FILENAME),
        os.O_CREAT | os.O_RDWR,
        0o644,
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(project_dir: str) -> dict[str, Any]:
    """Read state, returning a well-formed empty skeleton if absent/corrupt."""
    path = _state_path(project_dir)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {
        "phase": None,
        "active_plan": None,
        "last_check": None,
        "last_audit": None,
        "dirty_py": [],
        "overrides": [],
    }


def save(project_dir: str, state: dict[str, Any]) -> None:
    """Persist state atomically: write a sibling temp file, then os.replace it
    over the target. A torn write would otherwise be read back as corrupt JSON
    and silently reset to the empty skeleton (load()), dropping recorded passes
    AND the overrides audit trail — and two tool calls writing at once could lose
    one's update. os.replace is atomic on the same filesystem, so a reader sees
    either the old file or the fully-written new one, never a half-written one."""
    path = _state_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(path), prefix=".state-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        # Don't leave the temp file behind if the write/replace failed.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def record_pass(project_dir: str, gate: str) -> None:
    """Mark `gate` ('check' or 'audit') green against the current tree.

    A green *code* check proves the whole tree, so it also clears the dirty set:
    nothing is left outstanding for the incremental Stop gate to re-check.
    """
    fingerprint = code_fingerprint(project_dir)  # outside the lock: only reads
    with locked(project_dir):
        state = load(project_dir)
        state[f"last_{gate}"] = {
            "passed": True,
            "fingerprint": fingerprint,
            "at": now_iso(),
        }
        if gate == "check":
            state["dirty_py"] = []
        save(project_dir, state)


def set_active_plan(project_dir: str, plan_path: str) -> None:
    """Record `plan_path` as the project's active plan.

    The single writer of the `active_plan` field, so /forge:plan never has to
    hand-edit state.json (a malformed write there would corrupt workflow state).
    Stored verbatim — callers pass a repo-relative path like
    `docs/plans/0003-thing.md`."""
    with locked(project_dir):
        st = load(project_dir)
        st["active_plan"] = plan_path
        save(project_dir, st)


def add_dirty(project_dir: str, rel_path: str) -> None:
    """Record a source file edited since the last green check.

    The Stop gate type-checks only these files instead of the whole tree, so an
    every-turn mypy stays proportional to what changed rather than to repo size.
    Cleared when a full code gate passes (see record_pass)."""
    with locked(project_dir):
        state = load(project_dir)
        dirty = state.get("dirty_py")
        if not isinstance(dirty, list):
            dirty = []
        if rel_path not in dirty:
            dirty.append(rel_path)
            state["dirty_py"] = dirty
            save(project_dir, state)


def dirty_files(project_dir: str) -> list[str]:
    """Recorded dirty files that still exist, relative to the project root.

    Files edited and later deleted are dropped: there's nothing to type-check and
    handing a nonexistent path to mypy would just error."""
    state = load(project_dir)
    dirty = state.get("dirty_py")
    if not isinstance(dirty, list):
        return []
    return [p for p in dirty if os.path.exists(os.path.join(project_dir, p))]


def is_current(project_dir: str, gate: str) -> bool:
    """True if `gate` last passed and nothing has changed since."""
    state = load(project_dir)
    record = state.get(f"last_{gate}")
    if not record or not record.get("passed"):
        return False
    return record.get("fingerprint") == code_fingerprint(project_dir)


def invalidate(project_dir: str, gate: str = "check") -> None:
    """Drop a recorded pass — called when source changes so a stale green can't
    wave a commit through. Cheap no-op if there was nothing to drop."""
    with locked(project_dir):
        state = load(project_dir)
        if state.get(f"last_{gate}"):
            state[f"last_{gate}"] = None
            save(project_dir, state)


def _append_override(state: dict[str, Any], gate: str, reason: str) -> None:
    """Append one override record to `state` in place (caller holds the lock and
    saves). Factored out so take_override can record under its own single lock
    instead of nesting a second one via log_override — which would deadlock."""
    state.setdefault("overrides", []).append(
        {"gate": gate, "reason": reason, "at": now_iso()}
    )


def log_override(project_dir: str, gate: str, reason: str) -> None:
    """Record that a human deliberately bypassed `gate`. Overrides are kept, not
    consumed: the audit trail of *what was skipped and why* is the whole point."""
    with locked(project_dir):
        state = load(project_dir)
        _append_override(state, gate, reason)
        save(project_dir, state)


def request_override(project_dir: str, gate: str, reason: str = "") -> str:
    """Arm a one-shot override for `gate` by writing its sentinel file.

    This is the ergonomic counterpart to `take_override`: the next matching gated
    action consumes the file and logs the bypass. Writing the reason into the file
    means the audit trail carries *why* without a second step. Returns the path of
    the sentinel written.
    """
    path = os.path.join(project_dir, STATE_DIRNAME, f"override-{gate}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write((reason or "").strip() + "\n")
    return path


def pending_overrides(project_dir: str) -> dict[str, str]:
    """Gates with an armed-but-not-yet-consumed override, mapped to their reason.

    These are the sentinel files on disk (what *will* be bypassed on the next
    gated action), as opposed to the consumed-and-logged `overrides` trail in
    state. Used by /forge:status to surface a bypass before it silently fires."""
    d = os.path.join(project_dir, STATE_DIRNAME)
    out: dict[str, str] = {}
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for name in names:
        if not name.startswith("override-"):
            continue
        gate = name[len("override-") :]
        try:
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                out[gate] = fh.read().strip()
        except OSError:
            out[gate] = ""
    return out


def take_override(project_dir: str, gate: str) -> dict[str, Any] | None:
    """Return a one-shot override flag for `gate` if present, clearing it.

    The override is written as <project>/.forge/override-<gate> (optionally
    containing a reason). It is deleted on read so a bypass applies to exactly
    one gated action and never silently lingers.
    """
    flag = os.path.join(project_dir, STATE_DIRNAME, f"override-{gate}")
    with locked(project_dir):
        if not os.path.exists(flag):
            return None
        reason = ""
        try:
            with open(flag, encoding="utf-8") as fh:
                reason = fh.read().strip()
        except OSError:
            pass
        try:
            os.remove(flag)
        except OSError:
            pass
        state = load(project_dir)
        _append_override(state, gate, reason or "(no reason given)")
        save(project_dir, state)
    return {"gate": gate, "reason": reason}
