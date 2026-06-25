"""Content-addressed fingerprint of a project's first-party Python source.

The whole enforcement model rests on one cheap question a hook can answer: "has
the code changed since the last green check?" We answer it by hashing the source
tree and comparing against the fingerprint recorded when a gate last passed. This
module owns that hash (and the stat-keyed cache that keeps it cheap); `state`
records and compares the result.

It is deliberately dependency-free within the package so `state` can import it
without a cycle.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from typing import Any

STATE_DIRNAME = ".forge"
# Local-only (gitignored) sidecar: a stat-keyed digest cache that lets
# code_fingerprint skip re-reading files nothing has touched.
FPCACHE_FILENAME = "fpcache.json"

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


def _stat_key(path: str) -> tuple[int, int] | None:
    """(mtime_ns, size) for `path`, or None if it can't be stat'd. Used only as a
    cache key — never as the source of truth about whether content changed."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _fpcache_path(project_dir: str) -> str:
    return os.path.join(project_dir, STATE_DIRNAME, FPCACHE_FILENAME)


def _load_fp_cache(project_dir: str) -> tuple[dict[str, Any], int | None]:
    """Return (files, built_ns) from the cache. `files` maps relpath → entry;
    `built_ns` is when that cache was written (None if absent/corrupt) — the racy
    guard in _digest_cached needs it to know which entries are safe to trust."""
    try:
        with open(_fpcache_path(project_dir), encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            files = data.get("files")
            built = data.get("built_ns")
            return (
                files if isinstance(files, dict) else {},
                built if isinstance(built, int) else None,
            )
    except (OSError, json.JSONDecodeError):
        pass
    return {}, None


def _save_fp_cache(project_dir: str, files: dict[str, Any], built_ns: int) -> None:
    """Persist the digest cache, best-effort and atomically. It only accelerates
    fingerprinting — a failed or torn write just means the next call re-hashes —
    so any OSError is swallowed rather than propagated into a gate check."""
    d = os.path.join(project_dir, STATE_DIRNAME)
    try:
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".fpcache-", suffix=".tmp")
    except OSError:
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"built_ns": built_ns, "files": files}, fh)
        os.replace(tmp, _fpcache_path(project_dir))
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(tmp)


def _digest_cached(
    full: str,
    rel: str,
    old: dict[str, Any],
    new: dict[str, Any],
    prev_built_ns: int | None,
) -> bytes:
    """sha256 of `full`'s bytes, reusing the cached digest when the file is
    provably unchanged since it was hashed.

    "Provably unchanged" needs care: (mtime, size) alone is not enough, because a
    same-size edit landing in the same clock-granularity tick as the last hash
    leaves both unchanged while the bytes differ (the classic "racy clean"
    problem — and not theoretical: fast/tmpfs writes hit it). So, like git, we
    trust a cached entry only when the file's mtime is in a *strictly earlier
    whole second* than the moment the previous cache was built (`prev_built_ns`).
    The second-granularity comparison is deliberate: a filesystem truncates mtime
    to its own (often coarse) granularity, so an edit made in the same second as
    the build can carry an mtime numerically *below* the fine-grained build clock
    — comparing raw nanoseconds would wrongly trust it. Demanding a strictly
    earlier second means a file is trusted only once a build has happened in a
    later second than its last write; until then it is re-hashed. mtime is thus a
    cache key, never the source of truth — a `git checkout` that rewrites
    bytes-identical files still re-hashes to the same digest, so a green gate
    survives. The fresh entry is copied into `new` so the cache forgets deleted
    files. (Assumes mtime granularity ≤ 1s, true of ext4/apfs/xfs/tmpfs; a 2s-
    granularity filesystem like FAT could race, but those don't host dev repos.)"""
    key = _stat_key(full)
    if (
        key is not None
        and prev_built_ns is not None
        and key[0] // 1_000_000_000 < prev_built_ns // 1_000_000_000
    ):
        ent = old.get(rel)
        if (
            isinstance(ent, dict)
            and ent.get("mtime") == key[0]
            and ent.get("size") == key[1]
            and isinstance(ent.get("digest"), str)
        ):
            try:
                digest = bytes.fromhex(ent["digest"])
            except ValueError:
                digest = None
            if digest is not None:
                new[rel] = ent
                return digest
    digest = _file_digest(full)
    if key is not None:
        new[rel] = {"mtime": key[0], "size": key[1], "digest": digest.hex()}
    return digest


def code_fingerprint(project_dir: str) -> str:
    """A content-addressed fingerprint of the first-party Python source tree.

    We hash each file's relative path plus a sha256 of its *bytes*. An earlier
    version keyed on size+mtime to save the read, but mtime churns on operations
    that don't change a single byte — `git checkout`, branch switches, stash
    pops, fresh clones — and every one of them silently invalidated a green gate
    and forced a needless re-check. Content hashing makes "green" survive exactly
    as long as the code is byte-for-byte unchanged, however it got that way.

    The cost of that guarantee is reading first-party source; pruning vendor/venv
    dirs (_SKIP_DIRS) keeps it proportional to the code, and a stat-keyed digest
    cache (_digest_cached, racy-clean-safe) skips re-reading files provably
    untouched since the last build — so the common "nothing moved since the last
    check" path stats each file instead of hashing it, without weakening the
    content guarantee. Path is included so a rename still registers as a change.

    `built_ns` is sampled BEFORE the walk: any file modified during or after the
    hash gets an mtime >= built_ns and so is re-hashed next time rather than
    trusted — never the other way round.
    """
    old, prev_built_ns = _load_fp_cache(project_dir)
    built_ns = time.time_ns()
    new: dict[str, Any] = {}
    h = hashlib.sha256()
    for rel, full in _iter_source_files(project_dir):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(_digest_cached(full, rel, old, new, prev_built_ns))
    _save_fp_cache(project_dir, new, built_ns)
    return h.hexdigest()
