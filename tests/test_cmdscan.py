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


# --- non-uv dependency commands: must catch ------------------------------


@pytest.mark.parametrize(
    ("command", "label"),
    [
        ("pip install requests", "pip install"),
        ("pip3 install -r requirements.txt", "pip install"),
        ("pip uninstall flask", "pip uninstall"),
        ("python -m pip install requests", "python -m pip install"),
        ("python3 -m pip uninstall -y requests", "python -m pip uninstall"),
        ("uv pip install requests", "uv pip install"),
        ("uv pip sync requirements.txt", "uv pip sync"),
        ("poetry add httpx", "poetry add"),
        ("poetry install", "poetry install"),
        ("pipenv install requests", "pipenv install"),
        ("conda install numpy", "conda install"),
        ("mamba install scipy", "mamba install"),
        ("pip-compile", "pip-compile"),
        ("easy_install pytz", "easy_install"),
        ("cd app && pip install requests", "pip install"),  # second segment
        ("bash -c 'pip install requests'", "pip install"),  # nested shell
        ("VIRTUAL_ENV=x pip install requests", "pip install"),  # env prefix
    ],
)
def test_detects_non_uv_dep_command(command, label):
    assert cmdscan.dep_install_command(command) == label


# --- non-uv dependency commands: must NOT fire ---------------------------


@pytest.mark.parametrize(
    "command",
    [
        "uv add requests",  # the blessed path
        "uv add --group dev pytest",
        "uv remove flask",
        "uv sync --all-extras",
        "uv lock",
        "uv run pytest",
        "uv pip list",  # read-only, not mutating
        "uv pip freeze",
        "pip list",
        "pip show requests",
        "python -m pytest",  # -m, but not pip
        "echo 'pip install requests'",  # quoted, not a command
        "git commit -m 'switch from pip install to uv add'",  # message mention
    ],
)
def test_ignores_non_dep_or_uv_commands(command):
    assert cmdscan.dep_install_command(command) is None


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


# --- redirections don't leak into the parsed command ----------------------


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m x > out.log",
        "git commit -m x 2> err.log",  # fd-prefixed redirection
        "git commit -m x 2>> err.log",
        "git commit -m x &> all.log",  # combined redirection
        "git commit -m x 2>&1",  # fd duplication
        "git commit -m x > out 2> err",  # multiple redirections
    ],
)
def test_redirections_are_stripped_but_command_still_detected(command):
    assert cmdscan.runs_git_subcommand(command, "commit")


def test_redirection_target_is_not_kept_as_an_argument():
    # The redirect operator, its fd, and its target all drop out — what's left
    # is exactly the command and its real arguments.
    assert cmdscan.iter_commands("echo hi 2> /dev/null") == [["echo", "hi"]]
    assert cmdscan.iter_commands("uv build > dist.log") == [["uv", "build"]]


def test_publish_still_detected_with_redirection():
    assert cmdscan.runs_publish("uv build > /tmp/build.log 2>&1")
