"""Tests for the verifiable-claim extractor that feeds the doc-sync auditor."""

from __future__ import annotations

from conftest import write
from lib import doc_claims

DOC = """# Project

Install it:

```bash
uv sync  # set up the env
$ uv run app
```

See `src/app.py` and the `forge.lib.state` module.
Run `/forge:check` to verify. This module is fast.
"""


def _claims(project):
    return doc_claims.extract(project)


def test_extracts_shell_commands_without_comment_or_prompt(project):
    write(project, "README.md", DOC)
    cmds = [c["text"] for c in _claims(project) if c["kind"] == "command"]
    assert "uv sync" in cmds  # trailing inline comment stripped
    assert "uv run app" in cmds  # leading "$ " prompt stripped


def test_extracts_paths_and_symbols(project):
    write(project, "README.md", DOC)
    claims = _claims(project)
    paths = [c["text"] for c in claims if c["kind"] == "path"]
    symbols = [c["text"] for c in claims if c["kind"] == "symbol"]
    assert "src/app.py" in paths
    assert "forge.lib.state" in symbols


def test_skips_slash_commands_and_prose(project):
    write(project, "README.md", DOC)
    texts = [c["text"] for c in _claims(project)]
    assert "/forge:check" not in texts  # colon-bearing token skipped
    assert "This module is fast." not in texts  # prose is never a claim


def test_claims_are_located_by_line(project):
    write(project, "README.md", DOC)
    for c in _claims(project):
        assert c["doc"] == "README.md"
        assert isinstance(c["line"], int) and c["line"] >= 1
