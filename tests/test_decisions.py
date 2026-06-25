"""Tests for the durable-intent (directives + ADR) layer."""

from __future__ import annotations

from conftest import write
from lib import decisions
from lib.decisions import AdrDraft


def test_slugify():
    assert decisions.slugify("CLI uses subcommands!") == "cli-uses-subcommands"
    assert decisions.slugify("   ") == "decision"


def test_adr_filename():
    assert decisions.adr_filename(3, "Use uv") == "0003-use-uv.md"


def test_next_adr_number_empty(project):
    assert decisions.next_adr_number(project) == 1


def test_next_adr_number_increments(project):
    write(project, "docs/decisions/0001-a.md", "")
    write(project, "docs/decisions/0007-b.md", "")
    write(project, "docs/decisions/notes.md", "")  # ignored: no NNNN- prefix
    assert decisions.next_adr_number(project) == 8


def _draft() -> AdrDraft:
    return AdrDraft(
        number=2,
        title="Adopt uv",
        context="pip is slow.",
        decision="Use uv for envs and deps.",
        rationale="Faster, lockfile-native.",
        directive="Dependencies MUST be managed with uv.",
    )


def test_render_adr_contains_all_sections():
    md = decisions.render_adr(_draft(), date="2026-06-22")
    assert "# 0002. Adopt uv" in md
    assert "Date: 2026-06-22" in md
    for heading in ("## Context", "## Decision", "## Rationale"):
        assert heading in md


def test_directive_line_backlinks_to_adr():
    line = decisions.directive_line(_draft())
    assert line.startswith("- Dependencies MUST be managed with uv.")
    assert "docs/decisions/0002-adopt-uv.md" in line


def test_directives_roundtrip_and_injection(project):
    assert not decisions.has_directives(project)
    assert decisions.injection_block(project) == ""

    write(project, ".forge/directives.md", "- CLI MUST use subcommands.")
    assert decisions.has_directives(project)
    block = decisions.injection_block(project)
    assert "Binding project directives" in block
    assert "CLI MUST use subcommands." in block


# The scaffolded template is prose only (no bullets), so "the file exists" must
# NOT read as "a directive was recorded" — that distinction is what keeps the
# review gate off projects that haven't actually decided anything.
_TEMPLATE_ONLY = (
    "# Binding directives — demo\n\n"
    "Durable, agreed constraints for this project.\n\n"
    "<!-- directives are appended below this line -->\n"
)


def test_binding_directive_count_ignores_template_prose(project):
    write(project, ".forge/directives.md", _TEMPLATE_ONLY)
    assert decisions.has_directives(project)  # file is non-empty
    assert decisions.binding_directive_count(project) == 0
    assert not decisions.has_binding_directives(project)


def test_binding_directive_count_counts_recorded_bullets(project):
    write(
        project,
        ".forge/directives.md",
        _TEMPLATE_ONLY
        + "- CLI MUST use subcommands. (see docs/decisions/0001-cli.md)\n"
        + "- Config MUST go through pydantic-settings. (see docs/decisions/0002-cfg.md)\n",
    )
    assert decisions.binding_directive_count(project) == 2
    assert decisions.has_binding_directives(project)


def test_has_binding_directives_false_when_absent(project):
    assert not decisions.has_binding_directives(project)
    assert decisions.binding_directive_count(project) == 0
