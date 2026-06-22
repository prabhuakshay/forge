"""Thin helpers for reading hook input and emitting hook decisions.

Claude Code hooks communicate over stdin/stdout with a documented JSON protocol.
Centralising the encoding here keeps each hook script down to its actual logic
and means a protocol change is a one-file fix rather than a six-file sweep.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def read_input() -> dict[str, Any]:
    """Parse the hook payload from stdin.

    Returns an empty dict on malformed/empty input rather than raising: a hook
    that crashes on bad input would wedge the tool call it gates, so we fail
    open and let the caller decide what a missing field means.
    """
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def project_dir(payload: dict[str, Any]) -> str:
    """The directory the tool call runs in — where .forge/ state lives."""
    return payload.get("cwd") or "."


# --- PreToolUse decisions -------------------------------------------------


def allow() -> None:
    """Let the tool call proceed. Emitting nothing also allows, but being
    explicit documents intent and short-circuits cleanly."""
    sys.exit(0)


def deny(reason: str) -> None:
    """Block the tool call. `reason` is surfaced to the model so it can correct
    course (e.g. 'run /forge:plan first') rather than just seeing a wall."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


# --- Stop decisions -------------------------------------------------------


def block_stop(reason: str) -> None:
    """Prevent the agent from ending its turn and feed `reason` back so it
    keeps working until the gate is green."""
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


# --- Context injection (SessionStart / UserPromptSubmit) ------------------


def inject_context(event: str, text: str) -> None:
    """Push `text` into the agent's context for this session."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": text,
        }
    }
    print(json.dumps(out))
    sys.exit(0)
