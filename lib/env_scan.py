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

# os.environ["X"] / os.environ['X'] / os.environ.get("X") / os.getenv("X").
# The opener is `[` for subscripts and `(` for the .get(...) call, so we accept
# either — an earlier version only allowed `[`, which silently missed every
# os.environ.get("X") read and let those vars escape drift detection.
_OS_ENV = re.compile(r"""os\.environ(?:\.get)?\s*[\[(]?\s*['"]([A-Z][A-Z0-9_]*)['"]""")
_GETENV = re.compile(r"""os\.getenv\(\s*['"]([A-Z][A-Z0-9_]*)['"]""")

# A pydantic-settings field becomes an env var by its (upper-cased) name. We only
# scan within a class that visibly derives from BaseSettings/Settings to avoid
# sweeping up every dataclass attribute in the project.
_SETTINGS_CLASS = re.compile(
    r"class\s+\w+\s*\(\s*[^)]*\b(?:BaseSettings|Settings)\b[^)]*\)\s*:"
)
_FIELD = re.compile(r"^\s{4}([A-Za-z_][A-Za-z0-9_]*)\s*[:=]")

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
}


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
        found.update(_OS_ENV.findall(text))
        found.update(_GETENV.findall(text))
        found.update(_settings_fields(text))
    return found


def _settings_fields(text: str) -> set[str]:
    """Field names inside BaseSettings subclasses, upper-cased to their env form.

    pydantic-settings matches env vars case-insensitively by default, so a field
    `database_url` maps to DATABASE_URL — we normalise to upper to compare against
    the conventionally upper-cased .env.example keys.
    """
    fields: set[str] = set()
    inside = False
    for line in text.splitlines():
        if _SETTINGS_CLASS.search(line):
            inside = True
            continue
        if inside:
            stripped = line.strip()
            # A non-indented, non-blank line ends the class body.
            if stripped and not line.startswith((" ", "\t")):
                inside = False
                continue
            m = _FIELD.match(line)
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
