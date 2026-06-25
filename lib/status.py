"""Render a human-readable snapshot of a project's forge workflow state.

This is the read model behind /forge:status: it answers "where does this project
stand right now?" in one screen — which gates are green for the current tree,
what's been edited since the last check, which style references are installed,
how many directives bind, and whether any one-shot override is armed (about to
fire) or has fired before.

It is deliberately a pure string builder over the existing state/refs/decisions
layers (no I/O of its own beyond what those do, no side effects), so the bin/
entrypoint stays a one-liner and the formatting is testable in-process.
"""

from __future__ import annotations

from lib import decisions, references, state

# Status glyphs, matching gate.GateResult.summary so the whole plugin speaks one
# visual language: green pass / red problem / not-applicable.
_OK = "✓"  # ✓
_BAD = "✗"  # ✗
_NA = "—"  # —


def _gate_line(project_dir: str, gate: str, label: str) -> str:
    """One gate's line: green for the current tree, stale, or never run."""
    record = state.load(project_dir).get(f"last_{gate}")
    if not record or not record.get("passed"):
        return f"  {_NA} {label}: never run"
    if state.is_current(project_dir, gate):
        return f"  {_OK} {label}: green (passed {record.get('at', '?')})"
    return (
        f"  {_BAD} {label}: stale — tree changed since {record.get('at', '?')}; "
        f"re-run /forge:{gate}"
    )


def report(project_dir: str) -> str:
    """The full status report as a printable block ending in a newline."""
    st = state.load(project_dir)
    out: list[str] = [f"forge status — {project_dir}", ""]

    out.append(f"  phase        {st.get('phase') or _NA}")
    out.append(f"  active plan  {st.get('active_plan') or _NA}")
    out.append("")

    out.append("gates")
    out.append(_gate_line(project_dir, "check", "check  (commit gate)"))
    # The review gate only binds when there's something to enforce (directives or
    # a governing reference), so only surface it then — otherwise it's noise.
    if decisions.has_binding_directives(project_dir) or references.installed(
        project_dir
    ):
        out.append(_gate_line(project_dir, "review", "review (commit gate)"))
    out.append(_gate_line(project_dir, "audit", "audit  (push/publish gate)"))
    out.append("")

    dirty = state.dirty_files(project_dir)
    if dirty:
        out.append(f"dirty since last check ({len(dirty)})")
        out.extend(f"  • {p}" for p in dirty)
        out.append("")

    refs = references.installed(project_dir)
    if refs:
        out.append(f"style references ({len(refs)})")
        for ref in refs:
            scope = ", ".join(ref.applies_to) or "(unscoped)"
            out.append(f"  • {ref.name} [{ref.enforcement}] — {scope}")
        out.append("")

    binding = decisions.binding_directive_count(project_dir)
    if binding:
        out.append(f"directives   {binding} binding (.forge/directives.md)")
        out.append("")

    pending = state.pending_overrides(project_dir)
    if pending:
        out.append(
            f"armed overrides ({len(pending)}) — each bypasses its gate once, then logs"
        )
        for gate, reason in pending.items():
            out.append(f"  {_BAD} {gate}" + (f" — {reason}" if reason else ""))
        out.append("")

    history = st.get("overrides")
    if isinstance(history, list) and history:
        out.append(f"override history ({len(history)})")
        for entry in history[-5:]:
            out.append(
                f"  {entry.get('at', '?')}  {entry.get('gate', '?')} — "
                f"{entry.get('reason', '')}"
            )
        out.append("")

    return "\n".join(out).rstrip() + "\n"
