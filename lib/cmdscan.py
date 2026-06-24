"""Parse shell command lines well enough to tell which programs they actually run.

The commit/push/publish guards must answer one question about a Bash command:
"does this invoke `git commit` / `git push` / a publish tool?" The first cut
matched a regex against the raw string, which failed both ways:

  * it MISSED real invocations — `git -C /repo commit` (the path after -C isn't a
    flag, so the regex lost the `commit`) and `bash -c "git push"`;
  * it FIRED on false ones — `git commit -m "fix git push retry"` tripped the
    push guard because "git push" appears inside the message.

So we parse instead. We tokenise with shlex (quoted arguments are therefore never
mistaken for commands), split on shell operators and newlines, strip leading env
assignments and wrapper commands (`env`, `sudo`, `time`, …), and recurse into
`sh -c '...'`. A command's program and subcommand are read from the command-word
positions only, never from a quoted argument.

This is a guardrail, not a sandbox: sufficiently determined obfuscation can still
slip through, which is exactly what the logged override exists for. The bar we aim
to clear is "not fooled by ordinary, legitimate command shapes".
"""

from __future__ import annotations

import os
import re
import shlex

# Tokens that separate one command from the next within a line.
_BOUNDARY = {"&&", "||", "|", "|&", ";", ";;", "&", "(", ")", "{", "}"}

# Programs that run another command given as their trailing arguments. We skip
# the wrapper and any leading env assignments; we do NOT try to parse wrapper
# options (e.g. `sudo -u user`), so such forms simply under-match — same failure
# mode as the old regex, and the override covers it.
_WRAPPERS = {
    "env",
    "sudo",
    "doas",
    "nohup",
    "time",
    "nice",
    "ionice",
    "command",
    "builtin",
    "exec",
    "xargs",
    "stdbuf",
    "setsid",
}

# Shells that take a command string via -c, whose contents we recurse into.
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

# git global options that consume the FOLLOWING token as their value; the
# subcommand parser must skip both so it doesn't read the value as the subcommand.
# (`git -C path commit`, `git -c key=val commit`, `git --git-dir d commit`.)
_GIT_VALUE_OPTS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
    "--exec-path",
}

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _basename(token: str) -> str:
    """Program name without its path: /usr/bin/git -> git."""
    return os.path.basename(token)


def _lex(line: str) -> list[str]:
    """shlex tokens for one line, with shell operators emitted as their own
    tokens. Unbalanced quotes (a half-written command) must never crash a hook,
    so we fall back to a plain whitespace split."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return line.split()


def _segments(command: str) -> list[list[str]]:
    """Split a command line into independent command segments, breaking on shell
    operators and newlines. Redirection tokens (`>`, `2>>`, …) are dropped."""
    segments: list[list[str]] = []
    current: list[str] = []
    for line in command.split("\n"):
        for tok in _lex(line):
            if tok in _BOUNDARY:
                if current:
                    segments.append(current)
                    current = []
            elif set(tok) <= {"<", ">"}:
                continue  # a bare redirection operator: not a command boundary
            else:
                current.append(tok)
        if current:  # a newline ends the current segment
            segments.append(current)
            current = []
    return segments


def _resolve(tokens: list[str]) -> tuple[str, object]:
    """Strip env assignments and wrappers from a segment.

    Returns ('nested', cmdstring) when the real command is the argument of a
    shell -c (recurse into it), else ('cmd', tokens) with the actual command's
    tokens."""
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]
        if _ENV_ASSIGN.match(tok):
            i += 1
            continue
        base = _basename(tok)
        if base in _WRAPPERS:
            i += 1
            continue
        if base in _SHELLS:
            j = i + 1
            while j < n:
                if tokens[j] == "-c" and j + 1 < n:
                    return ("nested", tokens[j + 1])
                if not tokens[j].startswith("-"):
                    break
                j += 1
            return ("cmd", tokens[i:])
        return ("cmd", tokens[i:])
    return ("cmd", [])


def iter_commands(command: str) -> list[list[str]]:
    """Every concrete command the line runs, as token lists, with env/wrapper
    prefixes stripped and `sh -c '...'` strings recursed into."""
    commands: list[list[str]] = []
    for segment in _segments(command):
        kind, value = _resolve(segment)
        if kind == "nested":
            commands.extend(iter_commands(str(value)))
        elif value:
            commands.append(value)  # type: ignore[arg-type]
    return commands


def _first_arg(args: list[str]) -> str | None:
    """First non-option token (the conventional subcommand position)."""
    for tok in args:
        if not tok.startswith("-"):
            return tok
    return None


def _git_subcommand(args: list[str]) -> str | None:
    """The git subcommand, skipping global options — including those that take a
    separate value token (so `git -C path commit` reads as `commit`)."""
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in _GIT_VALUE_OPTS:
            i += 2
        elif tok.startswith("-"):
            i += 1  # boolean global flag or `--opt=value`
        else:
            return tok
    return None


def _has_module(args: list[str], module: str) -> bool:
    """True for `python -m <module>` (also the rare glued `-m<module>`)."""
    for i, tok in enumerate(args):
        if tok == "-m" and i + 1 < len(args):
            return args[i + 1] == module
        if tok == "-m" + module:
            return True
    return False


def runs_git_subcommand(command: str, subcommand: str) -> bool:
    """True if any command in the line is `git <subcommand>`."""
    return any(
        _basename(toks[0]) == "git" and _git_subcommand(toks[1:]) == subcommand
        for toks in iter_commands(command)
        if toks
    )


def _arg_after(args: list[str], marker: str) -> str | None:
    """First non-option token following the first `marker` token, or None.

    Lets us read the subcommand out of `uv pip install` / `python -m pip install`
    by anchoring on the `pip` token rather than position 0."""
    try:
        i = args.index(marker)
    except ValueError:
        return None
    return _first_arg(args[i + 1 :])


# Mutating subcommands per tool — the ones that install/remove/lock dependencies
# (as opposed to read-only `list`/`show`/`freeze`, which we leave alone).
_PIP_MUTATING = {"install", "uninstall", "download"}
_UV_PIP_MUTATING = {"install", "uninstall", "sync"}
_POETRY_MUTATING = {"add", "remove", "install", "update", "lock", "sync"}
_PIPENV_MUTATING = {"install", "uninstall", "update", "lock", "sync"}
_CONDA_MUTATING = {"install", "remove", "uninstall", "update", "create"}


def dep_install_command(command: str) -> str | None:
    """The first non-uv dependency-management invocation in `command`, named for
    a message (e.g. 'pip install', 'uv pip install', 'poetry add'), or None.

    Forge mandates uv as the single dependency manager: dependencies are added
    with `uv add` (recorded in pyproject.toml + uv.lock) and removed with
    `uv remove` — never pip, a requirements file, or a hand-edited pyproject. The
    require_uv gate refuses the alternatives. We flag only the *mutating*
    subcommands; inspection commands (`pip list`, `uv pip freeze`) are untouched.
    Note `uv pip install` IS flagged: it writes to the venv without recording the
    dependency, which is exactly the bypass `uv add` exists to prevent.
    """
    for toks in iter_commands(command):
        if not toks:
            continue
        prog = _basename(toks[0])
        rest = toks[1:]
        first = _first_arg(rest)

        if prog in {"pip", "pip3"} and first in _PIP_MUTATING:
            return f"pip {first}"
        if prog in {"python", "python3"} and _has_module(rest, "pip"):
            sub = _arg_after(rest, "pip")
            if sub in _PIP_MUTATING:
                return f"python -m pip {sub}"
        if prog == "uv" and first == "pip":
            sub = _arg_after(rest, "pip")
            if sub in _UV_PIP_MUTATING:
                return f"uv pip {sub}"
        if prog == "poetry" and first in _POETRY_MUTATING:
            return f"poetry {first}"
        if prog == "pipenv" and first in _PIPENV_MUTATING:
            return f"pipenv {first}"
        if prog in {"conda", "mamba", "micromamba"} and first in _CONDA_MUTATING:
            return f"{prog} {first}"
        if prog in {"pip-compile", "pip-sync", "easy_install"}:
            return prog
    return None


def runs_publish(command: str) -> bool:
    """True if any command builds or publishes a distribution (the non-git half
    of the release gate): uv build/publish, python -m build, twine upload, and
    the publish subcommand of flit/poetry/hatch."""
    for toks in iter_commands(command):
        if not toks:
            continue
        prog = _basename(toks[0])
        rest = toks[1:]
        first = _first_arg(rest)
        if prog == "uv" and first in {"build", "publish"}:
            return True
        if prog in {"python", "python3"} and _has_module(rest, "build"):
            return True
        if prog == "twine" and first == "upload":
            return True
        if prog in {"flit", "poetry", "hatch"} and first == "publish":
            return True
    return False
