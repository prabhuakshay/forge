"""Tests for the version-bump release tool (bin/bump.py).

bump.py is loaded by file path: bin/ is not an importable package, and naming it
explicitly keeps it isolated from the like-named modules elsewhere in the repo."""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

_BUMP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "bump.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("forge_bump", _BUMP_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bump = _load()


# --- resolve(): explicit version and bump arithmetic ---------------------


def test_resolve_explicit_version_passthrough():
    assert bump.resolve("2.3.4", "0.1.0") == "2.3.4"


@pytest.mark.parametrize(
    "level,expected",
    [("patch", "0.1.8"), ("minor", "0.2.0"), ("major", "1.0.0")],
)
def test_resolve_bump_levels(level, expected):
    assert bump.resolve(level, "0.1.7") == expected


def test_resolve_rejects_garbage():
    with pytest.raises(SystemExit):
        bump.resolve("not-a-version", "0.1.0")


# --- _sub(): version-field rewriting --------------------------------------


def test_sub_rewrites_single_json_version(tmp_path):
    p = tmp_path / "plugin.json"
    p.write_text('{\n  "version": "0.0.1"\n}\n')
    n = bump._sub(str(p), bump._JSON_VERSION, "9.9.9")
    assert n == 1
    assert json.loads(p.read_text())["version"] == "9.9.9"


def test_sub_rewrites_every_json_version(tmp_path):
    # The marketplace manifest carries the version twice (top-level + plugin).
    p = tmp_path / "marketplace.json"
    p.write_text('{"version": "0.0.1", "plugins": [{"version": "0.0.1"}]}')
    assert bump._sub(str(p), bump._JSON_VERSION, "9.9.9") == 2
    data = json.loads(p.read_text())
    assert data["version"] == "9.9.9"
    assert data["plugins"][0]["version"] == "9.9.9"


def test_sub_rewrites_only_project_version_in_toml(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[project]\nversion = "0.0.1"\nrequires-python = ">=3.10"\n')
    assert bump._sub(str(p), bump._TOML_VERSION, "9.9.9") == 1
    text = p.read_text()
    assert 'version = "9.9.9"' in text
    assert 'requires-python = ">=3.10"' in text  # untouched


# --- main(): end-to-end across all three manifests ------------------------


def test_main_bumps_all_manifests(tmp_path, monkeypatch, capsys):
    plugin = tmp_path / "plugin.json"
    market = tmp_path / "marketplace.json"
    pyproject = tmp_path / "pyproject.toml"
    plugin.write_text('{\n  "version": "0.1.0"\n}\n')
    market.write_text('{"version": "0.1.0", "plugins": [{"version": "0.1.0"}]}')
    pyproject.write_text('[project]\nversion = "0.1.0"\n')

    monkeypatch.setattr(bump, "PLUGIN", str(plugin))
    monkeypatch.setattr(bump, "MARKET", str(market))
    monkeypatch.setattr(bump, "PYPROJECT", str(pyproject))
    monkeypatch.setattr("sys.argv", ["bump.py", "minor"])

    assert bump.main() == 0

    assert json.loads(plugin.read_text())["version"] == "0.2.0"
    md = json.loads(market.read_text())
    assert md["version"] == "0.2.0" and md["plugins"][0]["version"] == "0.2.0"
    assert 'version = "0.2.0"' in pyproject.read_text()
    assert "0.1.0 -> 0.2.0" in capsys.readouterr().out


def test_main_requires_exactly_one_arg(monkeypatch):
    monkeypatch.setattr("sys.argv", ["bump.py"])
    with pytest.raises(SystemExit):
        bump.main()
