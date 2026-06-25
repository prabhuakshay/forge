"""PreToolUse hook: refuse `git commit` unless review is green — when there are
binding rules to honour.

Forge's directives and blocking style references are "binding", but nothing
mechanical proves a commit honoured them: whether a change obeys "the CLI is
subcommand-based" is an LLM judgement, the one `/forge:review` makes. So we gate
the same way check/audit do — on a pass fingerprinted to the current tree, recorded
only when the review came back clean — rather than trying to re-derive compliance
inside a hook.

What keeps this from being heavyweight is that it only fires where the project has
actually committed to something to enforce (option B):

  * at least one real directive is recorded (`/forge:decide`), OR
  * an installed style reference governs a file in the pending change set.

A project with neither has nothing for review to bind, so the gate stays out of the
way entirely. Where it does apply, editing any .py invalidates the recorded review
(see mark_dirty.py), so "reviewed earlier" never counts.

  * fires on Bash `git commit` in forge-enabled projects
  * override: .forge/override-review  (one-shot, logged) — the audited escape hatch
"""

import os
import subprocess

import _bootstrap  # noqa: F401

from lib import cmdscan, decisions, hookio, references, state


def _changed_files(project: str) -> list[str]:
    """Paths with uncommitted changes (staged, unstaged, or untracked), relative
    to the repo root. `-uall` lists individual untracked files rather than
    collapsing a new directory to `dir/` — we need the actual `.py` paths to match
    references against. Best-effort: any git failure yields an empty list, so the
    reference half of the gate fails open rather than wedging a commit on a repo
    git can't read."""
    try:
        proc = subprocess.run(
            ["git", "-C", project, "status", "--porcelain", "-uall"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    files: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]  # strip the two-char status field and its trailing space
        if " -> " in path:  # a rename: "old -> new" — the new path is what matters
            path = path.split(" -> ", 1)[1]
        files.append(path.strip().strip('"'))
    return files


def _has_binding_rules(project: str) -> bool:
    """Option B: review only binds where the project has something to enforce — a
    recorded directive, or an installed reference governing a changed file."""
    if decisions.has_binding_directives(project):
        return True
    refs = references.installed(project)
    if not refs:
        return False
    return any(r.governs(f) for f in _changed_files(project) for r in refs)


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    if not os.path.isdir(os.path.join(project, ".forge")):
        hookio.allow()

    ti = payload.get("tool_input") or {}
    command = ti.get("command") or ""
    if not cmdscan.runs_git_subcommand(command, "commit"):
        hookio.allow()

    # Nothing binding to enforce → this gate doesn't apply (see module docstring).
    if not _has_binding_rules(project):
        hookio.allow()

    if state.take_override(project, "review"):
        hookio.allow()

    if state.is_current(project, "review"):
        hookio.allow()

    hookio.deny(
        "This project has binding directives or a governing style reference, but "
        "the current tree hasn't passed review. Commit blocked.\n"
        "Run /forge:review and resolve any blocking findings (directive or "
        "reference violations, correctness, security), then commit.\n"
        "To bypass for a deliberate reason, run /forge:override review "
        '"<why>" (the bypass is logged) and retry.'
    )


if __name__ == "__main__":
    main()
