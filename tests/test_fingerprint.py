"""Tests for the stat-keyed fingerprint cache (the fast path under
code_fingerprint), focusing on the two properties that matter: it must speed up
the unchanged case, and it must never mask a real change."""

from __future__ import annotations

import os

from conftest import write
from lib import fingerprint


def test_cache_file_is_written(project):
    write(project, "src/a.py", "x = 1\n")
    fingerprint.code_fingerprint(project)
    assert os.path.exists(os.path.join(project, ".forge", fingerprint.FPCACHE_FILENAME))


def test_corrupt_cache_is_tolerated(project):
    """A garbage cache file must be ignored and the fingerprint recomputed from
    bytes, not crash the gate."""
    write(project, "src/a.py", "x = 1\n")
    fp = fingerprint.code_fingerprint(project)
    write(project, f".forge/{fingerprint.FPCACHE_FILENAME}", "{not json")
    assert fingerprint.code_fingerprint(project) == fp


def test_cache_skips_rehashing_unchanged_files(project, monkeypatch):
    """Once a file's mtime sits in a strictly earlier second than the last cache
    build, the next fingerprint serves its digest from cache instead of reading
    the bytes — that's the whole point of the cache."""
    p = write(project, "src/a.py", "x = 1\n")
    os.utime(p, ns=(10**9, 10**9))  # mtime in a long-past second
    fingerprint.code_fingerprint(project)  # populate cache with that old mtime

    read_paths: list[str] = []
    real = fingerprint._file_digest
    monkeypatch.setattr(
        fingerprint,
        "_file_digest",
        lambda path: read_paths.append(path) or real(path),
    )
    fingerprint.code_fingerprint(project)
    assert read_paths == []  # nothing re-read; all served from cache


def test_same_second_edit_is_not_masked(project):
    """The racy-clean guard: a same-size edit made in the same second as the
    cache build must still change the fingerprint, never be hidden by a stale
    cached digest."""
    write(project, "src/a.py", "x = 1\n")
    before = fingerprint.code_fingerprint(project)
    write(project, "src/a.py", "x = 2\n")  # identical size, same-second mtime
    assert fingerprint.code_fingerprint(project) != before


def test_cached_run_matches_uncached_digest(project):
    """A fingerprint served partly from cache must equal one computed cold."""
    p = write(project, "src/a.py", "x = 1\n")
    os.utime(p, ns=(10**9, 10**9))
    warm = fingerprint.code_fingerprint(project)  # builds cache
    os.remove(os.path.join(project, ".forge", fingerprint.FPCACHE_FILENAME))
    cold = fingerprint.code_fingerprint(project)  # no cache to lean on
    assert warm == cold
