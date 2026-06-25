"""PreToolUse hook: refuse to publish/push unless the non-code audit is green.

The release boundary. Pushing or building an artifact ships docs, config, and
metadata along with code — so it's gated on /forge:audit (docs↔code sync, .env
sync, lockfile sync, dependency and metadata hygiene), not just on tests.

  * fires on Bash commands that push or build/publish a distribution
  * only in forge-enabled projects
  * override: .forge/override-audit (one-shot, logged)
"""

import os

import _bootstrap  # noqa: F401

from lib import cmdscan, hookio, state


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    if not os.path.isdir(os.path.join(project, ".forge")):
        hookio.allow()

    ti = payload.get("tool_input") or {}
    command = ti.get("command") or ""
    # `git push`, or any build/publish invocation — parsed, not string-matched,
    # so a commit message mentioning "git push" doesn't trip this (see cmdscan).
    if not (
        cmdscan.runs_git_subcommand(command, "push") or cmdscan.runs_publish(command)
    ):
        hookio.allow()

    # Freshness before override: a green tree has nothing to bypass, so don't
    # consume (and log) a one-shot override that wasn't needed. See require_check.
    if state.is_current(project, "audit"):
        hookio.allow()

    if state.take_override(project, "audit"):
        hookio.allow()

    hookio.deny(
        "Project audit is not green for the current tree. Push/publish blocked.\n"
        "Run /forge:audit and resolve any drift (docs↔code, .env, lockfile, "
        "deps, metadata), then retry.\n"
        "To bypass deliberately, run /forge:override audit "
        '"<why>" (the bypass is logged) and retry.'
    )


if __name__ == "__main__":
    main()
