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
