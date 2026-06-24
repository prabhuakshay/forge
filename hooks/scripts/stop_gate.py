"""Stop hook: don't let the agent finish its turn on a broken tree.

Runs cheap, mechanical checks (no subagents) when the turn ends and blocks the
stop if any fail, feeding the reason back so the agent keeps fixing:

  * fast code gate: ruff format --check, ruff check, mypy  (tests excluded — too
    slow for an every-turn gate; the commit gate covers the suite). mypy is
    scoped to the files edited since the last green check (the dirty set) so an
    every-turn type check stays proportional to the edit, not the repo; when
    nothing is dirty, types are already proven and mypy is skipped entirely.
  * .env drift: any env var read in code but missing from .env.example

Loop safety: if we already blocked once this turn (stop_hook_active) we still
re-check, but a clean result releases immediately — there's no artificial retry
cap, the agent simply can't stop while something concrete is broken.
"""

import os

import _bootstrap  # noqa: F401

from lib import env_scan, gate, hookio, state


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)

    # Only gate forge-enabled projects; everything else stops normally.
    if not os.path.isdir(os.path.join(project, ".forge")):
        return

    # Honoured escape hatch for a deliberately-unfinished state.
    if state.take_override(project, "stop"):
        return

    problems: list[str] = []

    # Type-check only what changed this turn. An empty dirty set means nothing
    # was edited since the last green check, so mypy is skipped (run_types would
    # otherwise default to the whole tree); ruff still runs whole-tree since it's
    # cheap. The Stop gate's job is "did *you* leave the tree broken?", so gating
    # on the agent's own edits rather than pre-existing state is the right scope.
    dirty = state.dirty_files(project)
    steps = [gate.run_format_check(project), gate.run_lint(project)]
    if dirty:
        steps.append(gate.run_types(project, paths=dirty))
    fast = gate.GateResult(steps)
    if not fast.ok:
        detail = "\n".join(
            f"    {s.name}:\n{_indent(s.output)}" for s in fast.failures()
        )
        problems.append("Code gate is red:\n" + fast.summary() + "\n" + detail)

    drift = env_scan.analyse(project)
    if not drift.ok:
        problems.append(
            "Undocumented env vars (read in code, missing from .env.example): "
            + ", ".join(drift.undocumented)
            + ". Add them to .env.example with safe placeholder values."
        )

    if problems:
        hookio.block_stop(
            "Don't stop yet — fix these first, then finish:\n\n"
            + "\n\n".join(problems)
            + "\n\n(If this is a deliberate stopping point, run "
            '/forge:override stop "<why>" and end again — the bypass is logged.)'
        )


def _indent(text: str, width: int = 6) -> str:
    pad = " " * width
    return "\n".join(pad + line for line in (text or "").splitlines()[:40])


if __name__ == "__main__":
    main()
