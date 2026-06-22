"""Shared fixtures for the forge plugin's own test suite."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

import pytest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PLUGIN_ROOT, "hooks", "scripts")


@pytest.fixture
def project(tmp_path):
    """A throwaway forge-enabled project root (has a .forge/ dir), returned as a
    string path since the lib functions take str project dirs."""
    (tmp_path / ".forge").mkdir()
    return str(tmp_path)


def write(root: str, rel: str, content: str = "") -> str:
    """Create `root/rel` (and parents), returning the absolute path."""
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return full


# --- hook subprocess harness ---------------------------------------------
# The integration tests drive each hook the way Claude Code does: a fresh
# `python <script>.py` process fed the event JSON on stdin, whose stdout is the
# decision protocol. Running the real process (not an in-proc import) is what
# exercises _bootstrap's sys.path insertion and the actual stdin/stdout contract.


@dataclass
class HookRun:
    code: int
    out: str
    err: str

    @property
    def decision(self) -> dict | None:
        """Parsed stdout JSON, or None when the hook emitted nothing (= allow)."""
        return json.loads(self.out) if self.out.strip() else None


def run_hook(script: str, payload: dict, env: dict | None = None) -> HookRun:
    """Run hooks/scripts/<script>.py with `payload` as stdin JSON."""
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, f"{script}.py")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env if env is not None else os.environ.copy(),
        timeout=60,
    )
    return HookRun(proc.returncode, proc.stdout, proc.stderr)


# --- fake toolchain ------------------------------------------------------
# auto_format and stop_gate shell out to uv/ruff/mypy. To test their behaviour
# deterministically (and without a real ruff/mypy in the test env), we shadow
# those tools with shell shims on a PATH-prefixed bin dir: each shim logs its
# argv and exits with a code we control, and `uv run X` just execs X so it
# resolves to the matching shim.

_UV_SHIM = '#!/bin/sh\nif [ "$1" = "run" ]; then shift; fi\nexec "$@"\n'


def _tool_shim(name: str) -> str:
    # Log the invocation, then exit with $<NAME>_EXIT (default 0) so a test can
    # make a given tool "fail" without touching the others.
    return (
        f'#!/bin/sh\necho "{name} $*" >> "$TOOL_LOG"\n'
        f"exit ${{{name.upper()}_EXIT:-0}}\n"
    )


class FakeTools:
    def __init__(self, bindir: str, logpath: str):
        self._bindir = bindir
        self._logpath = logpath

    def env(self, *, ruff_exit: int = 0, mypy_exit: int = 0) -> dict:
        """A subprocess env with the shims shadowing the real tools."""
        env = os.environ.copy()
        env["PATH"] = self._bindir + os.pathsep + env.get("PATH", "")
        env["TOOL_LOG"] = self._logpath
        env["RUFF_EXIT"] = str(ruff_exit)
        env["MYPY_EXIT"] = str(mypy_exit)
        return env

    def log(self) -> str:
        try:
            with open(self._logpath, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def invoked(self, tool: str) -> bool:
        return any(line.startswith(tool + " ") for line in self.log().splitlines())


@pytest.fixture
def faketools(tmp_path) -> FakeTools:
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    for name, content in (
        ("uv", _UV_SHIM),
        ("ruff", _tool_shim("ruff")),
        ("mypy", _tool_shim("mypy")),
    ):
        shim = bindir / name
        shim.write_text(content)
        shim.chmod(0o755)
    return FakeTools(str(bindir), str(tmp_path / "tool.log"))
