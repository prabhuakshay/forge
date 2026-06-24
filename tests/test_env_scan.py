"""Tests for env-var drift detection."""

from __future__ import annotations

from conftest import write
from lib import env_scan

CODE = """
import os
from pydantic_settings import BaseSettings

DB = os.environ["DATABASE_URL"]
SECRET = os.environ.get("SECRET_KEY")
PORT = os.getenv("PORT")


class Settings(BaseSettings):
    redis_url: str = "redis://localhost"
    _private: str = "skip"
"""


def test_scan_code_finds_all_read_forms(project):
    write(project, "src/app.py", CODE)
    found = env_scan.scan_code(project)
    assert {"DATABASE_URL", "SECRET_KEY", "PORT", "REDIS_URL"} <= found
    assert "_PRIVATE" not in found


def test_parse_env_example(project):
    write(project, ".env.example", "# config\nDATABASE_URL=\nPORT=8000\n\nBAD LINE\n")
    assert env_scan.parse_env_example(project) == {"DATABASE_URL", "PORT"}


def test_analyse_reports_both_directions(project):
    write(project, "src/app.py", 'import os\nx = os.getenv("DATABASE_URL")\n')
    write(project, ".env.example", "OLD_FLAG=1\n")
    drift = env_scan.analyse(project)
    assert drift.undocumented == ["DATABASE_URL"]
    assert drift.stale == ["OLD_FLAG"]
    assert not drift.ok  # undocumented var is a hard failure


def test_analyse_ok_when_documented(project):
    write(project, "src/app.py", 'import os\nx = os.getenv("DATABASE_URL")\n')
    write(project, ".env.example", "DATABASE_URL=\n")
    drift = env_scan.analyse(project)
    assert drift.undocumented == []
    assert drift.ok


# --- settings fields at non-4-space indentation ---------------------------

TWO_SPACE = """
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  api_key: str
  page_size: int = 50
"""

TAB_INDENT = "from pydantic_settings import BaseSettings\n\n\nclass S(BaseSettings):\n\tsecret_key: str\n"


def test_settings_fields_detected_at_two_space_indent(project):
    write(project, "src/conf.py", TWO_SPACE)
    found = env_scan.scan_code(project)
    assert {"API_KEY", "PAGE_SIZE"} <= found


def test_settings_fields_detected_with_tabs(project):
    write(project, "src/conf.py", TAB_INDENT)
    assert "SECRET_KEY" in env_scan.scan_code(project)


def test_method_locals_in_settings_class_are_not_fields(project):
    code = (
        "from pydantic_settings import BaseSettings\n\n\n"
        "class Settings(BaseSettings):\n"
        "    url: str\n\n"
        "    def helper(self):\n"
        "        scratch = 1\n"  # deeper indent — a local, not a field
        "        return scratch\n"
    )
    write(project, "src/conf.py", code)
    found = env_scan.scan_code(project)
    assert "URL" in found
    assert "SCRATCH" not in found


# --- docstring / triple-quoted false positives ----------------------------


def test_env_reads_inside_docstrings_are_ignored(project):
    code = (
        "def f():\n"
        '    """Example usage:\n\n'
        '        db = os.environ["DOC_ONLY_VAR"]\n'
        '    """\n'
        "    return 1\n"
    )
    write(project, "src/app.py", code)
    assert "DOC_ONLY_VAR" not in env_scan.scan_code(project)
