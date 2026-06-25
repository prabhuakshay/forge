"""Tests for scoped style references: parsing, glob matching, injection tracking."""

from __future__ import annotations

import pytest

from conftest import write
from lib import references

DJANGO_REF = """---
name: django
summary: Django conventions
applies_to: ["**/models.py", "src/**/views.py"]
enforcement: blocking
---
- Fat models, thin views.
"""


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("**/models.py", "a/b/models.py", True),
        ("**/models.py", "models.py", True),  # ** also matches zero dirs
        ("src/**/views.py", "src/app/views.py", True),
        ("src/**/views.py", "src/views.py", True),
        ("src/*.py", "src/app.py", True),
        ("src/*.py", "src/sub/app.py", False),  # * does not cross '/'
        ("conf?.py", "confx.py", True),
        ("conf?.py", "conf.py", False),
    ],
)
def test_glob_match(pattern, path, expected):
    assert references._glob_match(path, pattern) is expected


def test_load_one_parses_frontmatter(project):
    path = write(project, ".forge/references/django.md", DJANGO_REF)
    ref = references.load_one(path)
    assert ref is not None
    assert ref.name == "django"
    assert ref.enforcement == "blocking"
    assert ref.applies_to == ["**/models.py", "src/**/views.py"]
    assert "Fat models" in ref.body


def test_enforcement_defaults_to_blocking(project):
    path = write(project, ".forge/references/x.md", "---\nname: x\n---\nrules")
    ref = references.load_one(path)
    assert ref is not None and ref.enforcement == "blocking"


def test_governs_and_for_file(project):
    write(project, ".forge/references/django.md", DJANGO_REF)
    refs = references.installed(project)
    assert [r.name for r in refs] == ["django"]
    assert refs[0].governs("app/models.py")
    assert not refs[0].governs("app/utils.py")

    matched = references.for_file(project, "src/web/views.py")
    assert [r.name for r in matched] == ["django"]
    assert references.for_file(project, "README.md") == []


def test_index_block_lists_installed(project):
    write(project, ".forge/references/django.md", DJANGO_REF)
    block = references.index_block(project)
    assert "Style references" in block
    assert "django [blocking]" in block


def test_for_file_orders_most_specific_first(project):
    # A broad reference and a narrow one both govern src/app/cli.py; the narrower
    # glob must win the ordering so a conflict resolves to the specific rule.
    write(
        project,
        ".forge/references/python-base.md",
        '---\nname: python-base\napplies_to: ["src/**/*.py"]\nenforcement: advisory\n---\nbase\n',
    )
    write(
        project,
        ".forge/references/cli.md",
        '---\nname: cli\napplies_to: ["src/**/cli.py"]\nenforcement: blocking\n---\ncli\n',
    )
    matched = references.for_file(project, "src/app/cli.py")
    assert [r.name for r in matched] == ["cli", "python-base"]


def test_for_file_breaks_specificity_ties_blocking_first(project):
    # Two references match src/app/models.py at the *same* specificity. The
    # blocking one must come first so an equal-specificity conflict resolves to
    # the stricter rule. Names are chosen so plain alphabetical order would put
    # the advisory one first — proving the enforcement tie-break overrides it.
    write(
        project,
        ".forge/references/a-advisory.md",
        '---\nname: a-advisory\napplies_to: ["src/**/models.py"]\nenforcement: advisory\n---\na\n',
    )
    write(
        project,
        ".forge/references/z-blocking.md",
        '---\nname: z-blocking\napplies_to: ["src/**/models.py"]\nenforcement: blocking\n---\nz\n',
    )
    matched = references.for_file(project, "src/app/models.py")
    assert [r.name for r in matched] == ["z-blocking", "a-advisory"]


def test_glob_specificity_ranks_literals_over_wildcards():
    assert references._glob_specificity("src/**/cli.py") > references._glob_specificity(
        "src/**/*.py"
    )
    assert references._glob_specificity("**/models.py") > references._glob_specificity(
        "**/*.py"
    )


def test_injection_tracking_is_once_per_session(project):
    write(project, ".forge/references/django.md", DJANGO_REF)
    assert not references.was_injected(project, "sess-1", "django")
    references.mark_injected(project, "sess-1", "django")
    assert references.was_injected(project, "sess-1", "django")
    # A new session starts fresh.
    assert not references.was_injected(project, "sess-2", "django")
