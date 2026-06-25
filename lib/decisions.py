"""The durable-intent layer: binding directives and the decision (ADR) log.

Project intent — "the CLI is subcommand-based", "all config via pydantic-settings"
— is neither code nor docs: no test fails when it's violated, yet every future
agent must obey it. We persist it IN THE REPO so it travels with the project and
binds everyone, and we keep two views of it:

  * .forge/directives.md  — the distilled, currently-binding rules. Terse,
    imperative, small enough to inject into every session's context. This is the
    "never ignored" surface.
  * docs/decisions/NNNN-*.md — the append-only history (ADRs): context, decision,
    rationale, status. Supersedable but never deleted, so the reasoning survives.

This module is the plumbing for both: locating files, allocating ADR numbers, and
rendering the directive block that the SessionStart hook injects.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from dataclasses import dataclass

DIRECTIVES_REL = os.path.join(".forge", "directives.md")
DECISIONS_REL = os.path.join("docs", "decisions")

_ADR_FILENAME = re.compile(r"^(\d{4})-[\w-]+\.md$")


def directives_path(project_dir: str) -> str:
    return os.path.join(project_dir, DIRECTIVES_REL)


def decisions_dir(project_dir: str) -> str:
    return os.path.join(project_dir, DECISIONS_REL)


def read_directives(project_dir: str) -> str:
    """The raw directives markdown, or '' if none recorded yet."""
    try:
        with open(directives_path(project_dir), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def has_directives(project_dir: str) -> bool:
    return bool(read_directives(project_dir))


def binding_directive_count(project_dir: str) -> int:
    """How many directives have actually been recorded — the `- …` bullet lines
    `/forge:decide` appends, not whether the file merely exists.

    The scaffolded `directives.md` ships prose (a header and usage note) but no
    bullets, so `has_directives` (non-empty) is True from day one. This counts the
    real, binding decisions, which is the signal callers want when asking 'does
    this project have anything for review to enforce?'."""
    return sum(
        1
        for line in read_directives(project_dir).splitlines()
        if line.strip().startswith("-")
    )


def has_binding_directives(project_dir: str) -> bool:
    """True once at least one real directive (not just the template) is recorded."""
    return binding_directive_count(project_dir) > 0


def injection_block(project_dir: str) -> str:
    """Render directives for SessionStart injection, or '' to inject nothing.

    The framing matters: we label these as binding constraints and point at the
    full log, so the agent treats them as rules rather than background prose.
    """
    body = read_directives(project_dir)
    if not body:
        return ""
    return (
        "# Binding project directives (forge)\n"
        "These are durable, agreed constraints for THIS project. Obey them "
        "without exception. A change that violates one is a blocking error — "
        "stop and raise it rather than proceeding. The full rationale for each "
        "lives in docs/decisions/.\n\n"
        f"{body}\n"
    )


def next_adr_number(project_dir: str) -> int:
    """Lowest unused 4-digit ADR number (1-based)."""
    d = decisions_dir(project_dir)
    highest = 0
    try:
        for name in os.listdir(d):
            m = _ADR_FILENAME.match(name)
            if m:
                highest = max(highest, int(m.group(1)))
    except OSError:
        pass
    return highest + 1


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "decision"


def adr_filename(number: int, title: str) -> str:
    return f"{number:04d}-{slugify(title)}.md"


@dataclass
class AdrDraft:
    """Everything needed to write one ADR and its directive line. Commands fill
    this in (with the user's confirmation) and call `write`."""

    number: int
    title: str
    context: str
    decision: str
    rationale: str
    directive: str  # the one-line imperative added to directives.md


def render_adr(draft: AdrDraft, date: str) -> str:
    """`date` is passed in (not computed) so callers stamp a real timestamp;
    keeping I/O and time at the edges makes this trivially testable."""
    return (
        f"# {draft.number:04d}. {draft.title}\n\n"
        f"- Status: Accepted\n"
        f"- Date: {date}\n\n"
        f"## Context\n\n{draft.context}\n\n"
        f"## Decision\n\n{draft.decision}\n\n"
        f"## Rationale\n\n{draft.rationale}\n"
    )


def directive_line(draft: AdrDraft) -> str:
    """The terse rule appended to directives.md, back-linked to its ADR."""
    return f"- {draft.directive} (see docs/decisions/{adr_filename(draft.number, draft.title)})"


def _atomic_write(path: str, content: str) -> None:
    """Write `content` to `path` via a sibling temp file + os.replace, so a reader
    never sees a half-written ADR and a crash mid-write leaves the old file (if
    any) intact rather than truncated."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".adr-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def record_decision(
    project_dir: str,
    *,
    title: str,
    context: str,
    decision: str,
    rationale: str,
    directive: str,
    date: str,
) -> tuple[int, str, str]:
    """Allocate the next ADR number and write the ADR, its binding directive, and
    the index entry as one serialised unit. Returns (number, adr_path, directives_path).

    Number allocation and the writes run under the shared `.forge` lock
    (`state.locked`) so two concurrent `/forge:decide` runs can't both read the
    same highest number and each claim it — which would produce two ADRs sharing
    `0004` and a directive whose back-reference is ambiguous, corrupting the very
    audit trail the feature exists to protect. The ADR is the source of truth and
    is written (atomically) first, then the directive line, then the optional
    index; so a crash between steps can at worst orphan an ADR file — never leave a
    directive pointing at a number that was never written.
    """
    # Local import: only this path needs `state`, and importing it lazily keeps
    # the module's pure render/parse helpers free of that dependency.
    from lib import state

    with state.locked(project_dir):
        number = next_adr_number(project_dir)
        draft = AdrDraft(
            number=number,
            title=title,
            context=context,
            decision=decision,
            rationale=rationale,
            directive=directive,
        )
        ddir = decisions_dir(project_dir)
        os.makedirs(ddir, exist_ok=True)
        adr_name = adr_filename(number, title)
        adr_path = os.path.join(ddir, adr_name)
        _atomic_write(adr_path, render_adr(draft, date))

        dpath = directives_path(project_dir)
        os.makedirs(os.path.dirname(dpath), exist_ok=True)
        with open(dpath, "a", encoding="utf-8") as fh:
            fh.write(directive_line(draft) + "\n")

        index = os.path.join(ddir, "README.md")
        if os.path.exists(index):
            with open(index, "a", encoding="utf-8") as fh:
                fh.write(f"- [{number:04d}. {title}]({adr_name}) — Accepted\n")
    return number, adr_path, dpath
