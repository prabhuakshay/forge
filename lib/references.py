"""Scoped style references: portable convention guides that govern a subset of files.

Where directives are project-specific decisions (global, few), references are
reusable style guides scoped to a kind of code — django.md governs the Django
files, cli.md the CLI files. A reference is the spec a file is checked against, so
divergence from it is drift, caught two ways:

  * proactively: when you edit a governed file, its rules are injected into context
    (once per session, tracked here) so you write to the convention, not against it.
  * at review: the reference-auditor checks changed files against their references.

References live committed in <project>/.forge/references/*.md so they travel with
the repo and bind everyone. Each declares what it governs in frontmatter:

    ---
    name: django
    summary: Django conventions for this repo
    applies_to: ["src/**/models.py", "**/migrations/*.py"]
    enforcement: blocking        # blocking | advisory
    ---
    <the rules>
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field

REFS_REL = os.path.join(".forge", "references")
_FRONTMATTER = re.compile(r"^---\s*$")


@dataclass
class Reference:
    name: str
    summary: str
    applies_to: list[str]
    enforcement: str  # "blocking" | "advisory"
    body: str
    path: str  # absolute path to the .md file
    globs: list[str] = field(default_factory=list)

    def governs(self, rel_path: str) -> bool:
        rel = rel_path.replace("\\", "/").lstrip("./")
        return any(_glob_match(rel, g) for g in self.applies_to)

    def match_specificity(self, rel_path: str) -> int:
        """How specifically this reference claims `rel_path`: the score of its
        narrowest matching glob, or -1 if it doesn't govern the file. Used to
        order overlapping references so the most specific one wins a conflict."""
        rel = rel_path.replace("\\", "/").lstrip("./")
        scores = [_glob_specificity(g) for g in self.applies_to if _glob_match(rel, g)]
        return max(scores) if scores else -1


def refs_dir(project_dir: str) -> str:
    return os.path.join(project_dir, REFS_REL)


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split a reference file into (metadata, body).

    Deliberately tiny and stdlib-only — we cannot import a YAML parser. We accept
    `key: value` lines, where a value starting with `[` is read as a Python/JSON
    list literal (covering the `applies_to: ["a", "b"]` form).
    """
    lines = text.splitlines()
    if not lines or not _FRONTMATTER.match(lines[0]):
        return {}, text
    meta: dict[str, object] = {}
    i = 1
    while i < len(lines) and not _FRONTMATTER.match(lines[i]):
        line = lines[i]
        if ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if val.startswith("["):
                try:
                    meta[key] = ast.literal_eval(val)
                except (ValueError, SyntaxError):
                    meta[key] = []
            else:
                meta[key] = val.strip().strip('"').strip("'")
        i += 1
    body = "\n".join(lines[i + 1 :]).strip() if i < len(lines) else ""
    return meta, body


def load_one(path: str) -> Reference | None:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    meta, body = _parse_frontmatter(text)
    name = str(meta.get("name") or os.path.splitext(os.path.basename(path))[0])
    applies = meta.get("applies_to") or []
    if not isinstance(applies, list):
        applies = [str(applies)]
    return Reference(
        name=name,
        summary=str(meta.get("summary") or name),
        applies_to=[str(g) for g in applies],
        enforcement=str(meta.get("enforcement") or "blocking"),
        body=body,
        path=path,
    )


def installed(project_dir: str) -> list[Reference]:
    d = refs_dir(project_dir)
    out: list[Reference] = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for name in names:
        if name.endswith(".md"):
            ref = load_one(os.path.join(d, name))
            if ref:
                out.append(ref)
    return out


def _enforcement_rank(enforcement: str) -> int:
    """Tie-break weight for two equally-specific references: `blocking` (0) sorts
    ahead of everything else (1). `enforcement` is free text on disk, so anything
    that isn't exactly "blocking" is treated as the weaker, advisory side rather
    than silently winning the tie."""
    return 0 if enforcement == "blocking" else 1


def for_file(project_dir: str, rel_path: str) -> list[Reference]:
    """References that govern `rel_path`, in conflict-resolution order.

    When several references claim the same file (e.g. a broad `src/**/*.py` and a
    narrow `src/**/cli.py`), the one with the narrowest matching glob comes first,
    so a caller resolving a conflict can take the most specific rule. At *equal*
    specificity the order is still deterministic: a `blocking` reference outranks
    an `advisory` one (the stricter contract wins the tie), and references tied on
    both fall back to name order."""
    matched = [r for r in installed(project_dir) if r.governs(rel_path)]
    return sorted(
        matched,
        key=lambda r: (
            -r.match_specificity(rel_path),
            _enforcement_rank(r.enforcement),
            r.name,
        ),
    )


def index_block(project_dir: str) -> str:
    """A compact 'these style references exist and what they govern' block for
    SessionStart, so the agent always knows which guides to consult."""
    refs = installed(project_dir)
    if not refs:
        return ""
    lines = [
        "# Style references (forge)",
        "This repo carries scoped style references. When you edit a file a "
        "reference governs, follow it; a `blocking` reference's rules are "
        "mandatory. Full text in .forge/references/.",
        "",
    ]
    for r in refs:
        scope = ", ".join(r.applies_to) or "(unscoped)"
        lines.append(f"- {r.name} [{r.enforcement}]: {r.summary} — governs {scope}")
    return "\n".join(lines) + "\n"


def injection_block(ref: Reference) -> str:
    """Full rules for one reference, framed for proactive edit-time injection."""
    return (
        f"# Style reference: {ref.name} ({ref.enforcement})\n"
        f"You are editing a file governed by this reference. Follow it"
        f"{' — its rules are mandatory' if ref.enforcement == 'blocking' else ''}.\n\n"
        f"{ref.body}\n"
    )


# --- per-session injection tracking --------------------------------------
# We inject a given reference at most once per session to avoid re-spending
# tokens on every edit. State is keyed by session id and reset when it changes,
# so the record never grows without bound.


def _track(project_dir: str, session_id: str, name: str, *, write: bool) -> bool:
    from lib import state  # local import: avoid a cycle at module load

    with state.locked(project_dir):
        st = state.load(project_dir)
        track = st.get("ref_injection")
        if not isinstance(track, dict) or track.get("session") != session_id:
            track = {"session": session_id, "names": []}
        already = name in track["names"]
        if write and not already:
            track["names"].append(name)
            st["ref_injection"] = track
            state.save(project_dir, st)
    return already


def was_injected(project_dir: str, session_id: str, name: str) -> bool:
    return _track(project_dir, session_id, name, write=False)


def mark_injected(project_dir: str, session_id: str, name: str) -> None:
    _track(project_dir, session_id, name, write=True)


# --- glob matching --------------------------------------------------------
# fnmatch mishandles `**`, so we translate globs to regex ourselves:
#   **  → any chars incl. '/'   *  → any chars except '/'   ?  → one non-'/'


def _glob_to_regex(pattern: str) -> str:
    out = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                # Swallow a slash right after ** so 'a/**/b' also matches 'a/b'.
                if i < n and pattern[i] == "/":
                    i += 1
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return "^" + "".join(out) + "$"


def _glob_match(path: str, pattern: str) -> bool:
    return re.match(_glob_to_regex(pattern), path) is not None


def _glob_specificity(pattern: str) -> int:
    """A rough 'how narrow is this glob' score: the count of fixed (literal)
    characters. Wildcards contribute nothing — `*`/`?` match within a segment and
    `**` crosses segments — so `src/**/cli.py` (12 literal chars) outranks the
    broader `src/**/*.py` (8). Used only to order overlapping references."""
    score = 0
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                i += 2  # `**` is the least specific wildcard
                continue
        elif c != "?":
            score += 1  # a literal character
        i += 1
    return score
