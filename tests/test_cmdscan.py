"""Tests for the command-line scanner behind the commit/push/publish guards.

These pin the two failure modes that motivated parsing over regex: real
invocations that must be CAUGHT, and innocent commands that must NOT be."""

from __future__ import annotations

import pytest

from lib import cmdscan


# --- git commit detection: must catch ------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'x'",
        "git add -A && git commit -m 'x'",
        "cd repo && git commit",
        "GIT_AUTHOR_DATE=now git commit -m x",  # env prefix
        "git -C /repo commit -m x",  # value-taking global opt
        "git -c user.name=bot commit -m x",  # -c key=val
        "git --git-dir /r/.git commit",  # long value opt
        "bash -c 'git commit -m x'",  # nested shell
        "sudo git commit",  # wrapper
        "false || git commit -m x",  # second segment
        "(git commit -m x)",  # subshell
    ],
)
def test_detects_git_commit(command):
    assert cmdscan.runs_git_subcommand(command, "commit")


# --- git commit detection: must NOT fire ---------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "echo 'git commit now'",  # quoted, not a command
        "git log --grep=commit",  # 'commit' is an option value, not the subcmd
        "git show HEAD",  # different subcommand
        "git status",
        "grep -r 'git commit' .",
    ],
)
def test_ignores_non_commit(command):
    assert not cmdscan.runs_git_subcommand(command, "commit")


# --- the precise cross-guard false positive ------------------------------


def test_commit_message_mentioning_push_does_not_trip_push_guard():
    cmd = "git commit -m 'implement git push retry'"
    assert not cmdscan.runs_git_subcommand(cmd, "push")
    assert not cmdscan.runs_publish(cmd)
    assert cmdscan.runs_git_subcommand(cmd, "commit")  # still a real commit


# --- git push detection ---------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push origin main",
        "git push --force-with-lease",
        "git -C /repo push",
        "git add . && git commit -m x && git push",
        "bash -c 'git push origin main'",
    ],
)
def test_detects_git_push(command):
    assert cmdscan.runs_git_subcommand(command, "push")


def test_push_in_message_is_not_a_push():
    assert not cmdscan.runs_git_subcommand("git commit -m 'add git push docs'", "push")


# --- publish detection ----------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "uv build",
        "uv publish",
        "python -m build",
        "python3 -m build --wheel",
        "twine upload dist/*",
        "flit publish",
        "poetry publish",
        "hatch publish",
        "rm -rf dist && uv build",
    ],
)
def test_detects_publish(command):
    assert cmdscan.runs_publish(command)


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest",  # uv, but not build/publish
        "uv lock",
        "uv sync",
        "python -m pytest",  # -m, but not build
        "twine check dist/*",
        "echo 'uv publish'",
    ],
)
def test_ignores_non_publish(command):
    assert not cmdscan.runs_publish(command)


# --- lower-level helpers --------------------------------------------------


def test_iter_commands_splits_and_strips():
    cmds = cmdscan.iter_commands("FOO=1 sudo git commit && echo done")
    assert cmds == [["git", "commit"], ["echo", "done"]]


def test_iter_commands_recurses_into_shell_c():
    assert cmdscan.iter_commands("bash -c 'git push origin main'") == [
        ["git", "push", "origin", "main"]
    ]


def test_malformed_quotes_do_not_raise():
    # An unbalanced quote must degrade gracefully, never crash the hook.
    assert cmdscan.runs_git_subcommand('git commit -m "oops', "commit")
