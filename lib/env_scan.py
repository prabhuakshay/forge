"""Detect drift between configuration the code reads and what `.env.example` documents.

The onboarding promise — "copy .env.example, fill it in, run" — only holds if
every environment variable the code actually reads is listed there. This module
scans source for env reads and pydantic-settings fields, parses .env.example,
and reports both directions of drift:

  * undocumented: read in code, missing from .env.example  (breaks onboarding)
  * stale:        in .env.example, never read in code       (dead config / confusion)

It is regex-based on purpose: it must run with no third-party imports and tolerate
code it can't fully parse. False positives are preferable to importing the world.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# os.environ["X"] / os.environ.get("X") / os.environ.pop("X") /
# os.environ.setdefault("X", ...) / os.getenv("X").
#
# Two earlier blind spots are deliberately closed here:
#   * the opener is `[` for subscripts and `(` for the method calls, so we accept
#     either — the first cut allowed only `[` and silently missed every
#     os.environ.get(...) read;
#   * `.pop()` and `.setdefault()` read the variable just as `.get()` does, so
#     they count too — omitting them let a real read escape drift detection.
#
# Names are captured in ANY case, not UPPER_CASE only. Environment variables are
# case-sensitive on POSIX, so `os.getenv("debug_mode")` is a real read that
# onboarding must document; matching only `[A-Z…]` quietly dropped every
# lower/mixed-case read on the floor. The drift check compares names verbatim, so
# a read and its .env.example entry must agree on case — which is exactly the
# contract the OS enforces at runtime. (pydantic-settings is the one exception:
# it resolves env vars case-insensitively, so _settings_fields still upper-cases.)
_OS_ENV = re.compile(
    r"""os\.environ(?:\.(?:get|pop|setdefault))?\s*[\[(]?\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""
)
_GETENV = re.compile(r"""os\.getenv\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]""")

# A pydantic-settings field becomes an env var by its (upper-cased) name. We only
# scan within a class that visibly derives from BaseSettings/Settings to avoid
# sweeping up every dataclass attribute in the project.
_SETTINGS_CLASS = re.compile(
    r"class\s+\w+\s*\(\s*[^)]*\b(?:BaseSettings|Settings)\b[^)]*\)\s*:"
)
# A field name at the start of a (stripped) class-body line. Indentation is not
# baked in here: the class scanner establishes the body's own indent level (which
# may be tabs, 2 spaces, or 4) and only matches lines at exactly that level, so a
# differently-indented Settings class is still read and method-body locals nested
# deeper are not mistaken for fields.
_FIELD_NAME = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]")

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "build",
    "dist",
    ".forge",
    "tests",
}

_COMMENT = re.compile(r"(?m)#[^\n]*")
# Triple-quoted strings (docstrings, multi-line literals). Stripped before the
# env-read patterns run so a doc example like `os.environ["SECRET"]` written
# inside a docstring isn't mistaken for a real read.
_TRIPLE = re.compile(r'(?s)""".*?"""|\'\'\'.*?\'\'\'')


@dataclass
class EnvDrift:
    undocumented: list[str]  # read in code, absent from .env.example
    stale: list[str]  # in .env.example, never read in code
    in_code: set[str]
    in_example: set[str]

    @property
    def ok(self) -> bool:
        # Only undocumented vars are a hard failure; stale ones are a warning,
        # because a var may be consumed by infra outside this codebase.
        return not self.undocumented


def _iter_py_files(project_dir: str):
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def scan_code(project_dir: str) -> set[str]:
    found: set[str] = set()
    for path in _iter_py_files(project_dir):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        # Strip triple-quoted strings then line comments so env-read patterns
        # appearing in docstrings/comments don't fire as real reads.
        stripped = _COMMENT.sub("", _TRIPLE.sub("", text))
        found.update(_OS_ENV.findall(stripped))
        found.update(_GETENV.findall(stripped))
        found.update(_settings_fields(stripped))
    return found


def _settings_fields(text: str) -> set[str]:
    """Field names inside BaseSettings subclasses, upper-cased to their env form.

    pydantic-settings matches env vars case-insensitively by default, so a field
    `database_url` maps to DATABASE_URL — we normalise to upper to compare against
    the conventionally upper-cased .env.example keys.
    """
    fields: set[str] = set()
    inside = False
    body_indent: str | None = None
    for line in text.splitlines():
        if _SETTINGS_CLASS.search(line):
            inside = True
            body_indent = None  # the first body line will fix the field level
            continue
        if not inside:
            continue
        if not line.strip():
            continue  # blank lines neither end the class nor set its indent
        indent = line[: len(line) - len(line.lstrip())]
        if indent == "":
            inside = False  # a dedent back to column 0 ends the class body
            continue
        if body_indent is None:
            body_indent = indent
        if indent != body_indent:
            continue  # deeper than the field level (method bodies etc.)
        m = _FIELD_NAME.match(line.strip())
        if m:
            name = m.group(1)
            if not name.startswith("_") and name not in {"model_config", "Config"}:
                fields.add(name.upper())
    return fields


def parse_env_example(project_dir: str) -> set[str]:
    keys: set[str] = set()
    path = os.path.join(project_dir, ".env.example")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                keys.add(line.split("=", 1)[0].strip())
    except OSError:
        pass
    return keys


def analyse(project_dir: str) -> EnvDrift:
    in_code = scan_code(project_dir)
    in_example = parse_env_example(project_dir)
    return EnvDrift(
        undocumented=sorted(in_code - in_example),
        stale=sorted(in_example - in_code),
        in_code=in_code,
        in_example=in_example,
    )
