"""Meta-tests: the prompt layer (commands, hooks manifest) must not reference
files or agents that don't exist.

`lib/` is unit-tested, but a command that calls `bin/typo.py`, an agent that was
renamed, or a hook script dropped from `hooks.json` would ship undetected — the
markdown/JSON isn't type-checked. These tests close that gap so forge stays as
honest about its own wiring as it asks its users' code to be.
"""

from __future__ import annotations

import json
import os
import re

from conftest import PLUGIN_ROOT

COMMANDS_DIR = os.path.join(PLUGIN_ROOT, "commands")
AGENTS_DIR = os.path.join(PLUGIN_ROOT, "agents")
BIN_DIR = os.path.join(PLUGIN_ROOT, "bin")
SCRIPTS_DIR = os.path.join(PLUGIN_ROOT, "hooks", "scripts")

# Agents review.md delegates to that forge does NOT ship: they belong to the
# user's Django project, and the command says so ("the project's ..."). Listing
# them here is what distinguishes "intentional external reference" from "typo".
KNOWN_EXTERNAL_AGENTS = {"django-quality-auditor", "django-security-auditor"}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _command_files() -> list[str]:
    return [
        os.path.join(COMMANDS_DIR, n)
        for n in sorted(os.listdir(COMMANDS_DIR))
        if n.endswith(".md")
    ]


def _shipped_agents() -> set[str]:
    names: set[str] = set()
    for n in os.listdir(AGENTS_DIR):
        if not n.endswith(".md"):
            continue
        m = re.search(r"(?m)^name:\s*(\S+)", _read(os.path.join(AGENTS_DIR, n)))
        if m:
            names.add(m.group(1))
    return names


def test_command_bin_references_exist():
    """Every `bin/<x>.py` a command tells the agent to run must be a real file."""
    missing = []
    for cmd in _command_files():
        for ref in re.findall(r"bin/([A-Za-z0-9_]+\.py)", _read(cmd)):
            if not os.path.isfile(os.path.join(BIN_DIR, ref)):
                missing.append(f"{os.path.basename(cmd)} -> bin/{ref}")
    assert not missing, f"commands reference non-existent bin scripts: {missing}"


def test_command_agent_references_resolve():
    """Every agent a command names (by forge's `*-auditor`/`*-author`/`*-scanner`
    convention) must be one forge ships, or a documented external agent."""
    shipped = _shipped_agents()
    assert shipped, "expected to discover forge's bundled agents"
    known = shipped | KNOWN_EXTERNAL_AGENTS
    unresolved = []
    for cmd in _command_files():
        refs = re.findall(
            r"`([a-z][a-z0-9-]*(?:-auditor|-author|-scanner))`", _read(cmd)
        )
        for ref in refs:
            if ref not in known:
                unresolved.append(f"{os.path.basename(cmd)} -> {ref}")
    assert not unresolved, f"commands reference unknown agents: {unresolved}"


def test_hook_scripts_exist():
    """Every script wired into hooks.json must be a real file — a renamed or
    deleted script would silently disable that hook (forge fails open)."""
    manifest = json.loads(_read(os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")))
    refs = re.findall(r"scripts/([A-Za-z0-9_]+\.py)", json.dumps(manifest))
    assert refs, "expected hook script references in hooks.json"
    missing = [r for r in refs if not os.path.isfile(os.path.join(SCRIPTS_DIR, r))]
    assert not missing, f"hooks.json references non-existent scripts: {missing}"
