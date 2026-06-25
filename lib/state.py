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
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

STATE_DIRNAME = ".forge"
STATE_FILENAME = "state.json"

# The gates that accept a one-shot override sentinel (.forge/override-<gate>).
# Kept here so the /forge:override CLI and the status report agree on the set.
OVERRIDE_GATES = ("check", "audit", "review", "stop", "plan", "uv")

# Directories that never contain first-party source but can hold thousands of
# .py files. Walking them would make the fingerprint slow and, worse, unstable
# (a dependency reinstall would invalidate every green check).
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "build",
    "dist",
    ".tox",
    ".eggs",
    ".forge",
}


def _state_path(project_dir: str) -> str:
    return os.path.join(project_dir, STATE_DIRNAME, STATE_FILENAME)


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


def _iter_source_files(project_dir: str):
    """Yield (relpath, fullpath) for every first-party .py file, in a stable
    sorted order so the fingerprint is deterministic across runs and platforms.
    Dependency/vendor/cache dirs are pruned so the walk stays bounded to code we
    actually own."""
    for root, dirs, files in os.walk(project_dir):
        # Prune skip-dirs in place so os.walk doesn't descend into them.
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(files):
            if name.endswith(".py"):
                full = os.path.join(root, name)
                yield os.path.relpath(full, project_dir), full


def _file_digest(path: str) -> bytes:
    """sha256 of a file's bytes, read in chunks to bound memory on large files.
    An unreadable file still perturbs the fingerprint deterministically rather
    than silently dropping out of it."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return b"<unreadable>"
    return h.digest()


def code_fingerprint(project_dir: str) -> str:
    """A content-addressed fingerprint of the first-party Python source tree.

    We hash each file's relative path plus a sha256 of its *bytes*. An earlier
    version keyed on size+mtime to save the read, but mtime churns on operations
    that don't change a single byte — `git checkout`, branch switches, stash
    pops, fresh clones — and every one of them silently invalidated a green gate
    and forced a needless re-check. Content hashing makes "green" survive exactly
    as long as the code is byte-for-byte unchanged, however it got that way.
    Reading first-party source is the cost; pruning vendor/venv dirs (_SKIP_DIRS)
    keeps it proportional to the code, not the dependency tree. Path is included
    so a rename still registers as a change.
    """
    h = hashlib.sha256()
    for rel, full in _iter_source_files(project_dir):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(_file_digest(full))
    return h.hexdigest()


def record_pass(project_dir: str, gate: str) -> None:
    """Mark `gate` ('check' or 'audit') green against the current tree.

    A green *code* check proves the whole tree, so it also clears the dirty set:
    nothing is left outstanding for the incremental Stop gate to re-check.
    """
    state = load(project_dir)
    state[f"last_{gate}"] = {
        "passed": True,
        "fingerprint": code_fingerprint(project_dir),
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
    st = load(project_dir)
    st["active_plan"] = plan_path
    save(project_dir, st)


def add_dirty(project_dir: str, rel_path: str) -> None:
    """Record a source file edited since the last green check.

    The Stop gate type-checks only these files instead of the whole tree, so an
    every-turn mypy stays proportional to what changed rather than to repo size.
    Cleared when a full code gate passes (see record_pass)."""
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
    state = load(project_dir)
    if state.get(f"last_{gate}"):
        state[f"last_{gate}"] = None
        save(project_dir, state)


def log_override(project_dir: str, gate: str, reason: str) -> None:
    """Record that a human deliberately bypassed `gate`. Overrides are kept, not
    consumed: the audit trail of *what was skipped and why* is the whole point."""
    state = load(project_dir)
    state.setdefault("overrides", []).append(
        {"gate": gate, "reason": reason, "at": now_iso()}
    )
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
    log_override(project_dir, gate, reason or "(no reason given)")
    return {"gate": gate, "reason": reason}
