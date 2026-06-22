"""Cheap pre-filter that extracts *verifiable* claims from docs for the doc-sync agent.

The doc-sync-auditor is grounded by design: it may only report drift it can tie to
code. To keep it fast and cheap, we don't hand it raw prose — we hand it a list of
concrete, checkable claims already located by line. The agent then verifies each
against the code and reports MISSING/MISMATCH, never inventing.

What counts as a verifiable claim:
  * shell/console commands in fenced code blocks (do they still run? right tool?)
  * file/dir paths mentioned in backticks (do they exist?)
  * dotted import paths / qualified names (do they resolve?)

Prose assertions ("this module is fast") are intentionally NOT extracted — they
aren't mechanically checkable and are exactly where small models hallucinate.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict

_FENCE = re.compile(r"^```(\w+)?\s*$")
# A backtick token that looks like a path: has a slash or a known code-y suffix.
_PATH_TOKEN = re.compile(r"`([^`]+)`")
_PATHISH = re.compile(r"[/\\]|\.(py|toml|cfg|ini|txt|md|yml|yaml|json|lock)$")
# A dotted, importable-looking name: foo.bar.Baz
_DOTTED = re.compile(r"^[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*){1,}$")

_SHELL_LANGS = {"bash", "sh", "shell", "console", "zsh", ""}
_DOC_EXTS = {".md", ".rst", ".txt"}


@dataclass
class Claim:
    doc: str  # path relative to project root
    line: int  # 1-based line number
    kind: str  # "command" | "path" | "symbol"
    text: str  # the literal claim


def _iter_doc_files(project_dir: str):
    # README at the root plus everything under docs/.
    candidates = []
    for name in os.listdir(project_dir) if os.path.isdir(project_dir) else []:
        if (
            name.lower().startswith("readme")
            and os.path.splitext(name)[1].lower() in _DOC_EXTS
        ):
            candidates.append(os.path.join(project_dir, name))
    docs_root = os.path.join(project_dir, "docs")
    for root, _, files in os.walk(docs_root):
        for name in files:
            if os.path.splitext(name)[1].lower() in _DOC_EXTS:
                candidates.append(os.path.join(root, name))
    return candidates


def extract(project_dir: str) -> list[dict]:
    """Return all verifiable claims across the project's docs as plain dicts
    (JSON-serialisable, ready to hand to the agent)."""
    claims: list[Claim] = []
    for path in _iter_doc_files(project_dir):
        rel = os.path.relpath(path, project_dir)
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        claims.extend(_extract_from(rel, lines))
    return [asdict(c) for c in claims]


def _extract_from(rel: str, lines: list[str]) -> list[Claim]:
    out: list[Claim] = []
    in_fence = False
    fence_lang = ""
    for i, raw in enumerate(lines, start=1):
        fence = _FENCE.match(raw.strip())
        if fence:
            if not in_fence:
                in_fence, fence_lang = True, (fence.group(1) or "").lower()
            else:
                in_fence, fence_lang = False, ""
            continue

        if in_fence:
            # Inside a shell block, each non-comment, non-empty line is a command
            # claim worth checking (right tool name, flags that still exist).
            if fence_lang in _SHELL_LANGS:
                cmd = raw.strip().lstrip("$ ").rstrip()
                # Drop a trailing inline comment ("uv sync  # set up") so the
                # claim is the command alone, not the prose explaining it.
                cmd = re.split(r"\s+#", cmd, maxsplit=1)[0].rstrip()
                if cmd and not cmd.startswith("#"):
                    out.append(Claim(rel, i, "command", cmd))
            continue

        # Outside fences: harvest backtick tokens that look like paths or symbols.
        for tok in _PATH_TOKEN.findall(raw):
            tok = tok.strip()
            # Slash-commands like `/forge:review` contain a colon and aren't files;
            # skip colon-bearing tokens so they aren't checked as paths.
            if ":" in tok:
                continue
            if _PATHISH.search(tok):
                out.append(Claim(rel, i, "path", tok))
            elif _DOTTED.match(tok):
                out.append(Claim(rel, i, "symbol", tok))
    return out
