"""
New schematics must carry the header of the installed KiCad.

KiCad 9 rejects a KiCad 10 header (``(version 20260101)``) with a bare
"Failed to load schematic", so on a KiCad 9 install create_project /
create_schematic must write the KiCad 9 tokens instead.
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("pcbnew", MagicMock())
sys.modules.setdefault("skip", MagicMock())

_PYTHON_DIR = Path(__file__).parent.parent / "python"
sys.path.insert(0, str(_PYTHON_DIR))

from utils import kicad_version  # noqa: E402


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(_PYTHON_DIR, "commands", filename)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _fresh_cache():
    kicad_version.reset_cache()
    yield
    kicad_version.reset_cache()


@pytest.mark.parametrize(
    "major, expected",
    [("9", (20250114, "9.0")), ("10", (20260101, "10.0")), ("11", (20260101, "10.0"))],
)
def test_sch_format_follows_override(monkeypatch, major, expected):
    monkeypatch.setenv("KICAD_MCP_KICAD_MAJOR", major)
    assert kicad_version.sch_format() == expected


def test_detects_version_from_kicad_cli(monkeypatch):
    monkeypatch.delenv("KICAD_MCP_KICAD_MAJOR", raising=False)
    run = MagicMock(return_value=MagicMock(stdout="9.0.2\n"))
    with (
        patch("utils.kicad_cli.resolve_kicad_cli", return_value="/usr/bin/kicad-cli"),
        patch.object(kicad_version.subprocess, "run", run),
    ):
        assert kicad_version.kicad_major_version() == 9
        assert kicad_version.kicad_major_version() == 9
    assert run.call_count == 1, "detected version must be cached"


def test_unknown_version_uses_newest_format(monkeypatch):
    monkeypatch.delenv("KICAD_MCP_KICAD_MAJOR", raising=False)
    with patch("utils.kicad_cli.resolve_kicad_cli", return_value=None):
        assert kicad_version.sch_format() == kicad_version.SCH_FORMATS[10]


def test_apply_sch_format_rewrites_header_only(monkeypatch):
    monkeypatch.setenv("KICAD_MCP_KICAD_MAJOR", "9")
    src = (
        '(kicad_sch (version 20260101) (generator "eeschema") (generator_version "10.0")\n'
        '  (symbol (lib_id "x") (version 7) (generator_version "keep"))\n)'
    )
    out = kicad_version.apply_sch_format(src)
    assert out.startswith(
        '(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0")'
    )
    assert '(version 7) (generator_version "keep")' in out


def test_create_project_writes_kicad9_header(monkeypatch, tmp_path):
    monkeypatch.setenv("KICAD_MCP_KICAD_MAJOR", "9")
    proj = _load("project_module_v9", "project.py")
    with patch.object(proj, "pcbnew", MagicMock()):
        result = proj.ProjectCommands().create_project({"name": "P", "path": str(tmp_path)})
    assert result["success"] is True, result
    text = (tmp_path / "P.kicad_sch").read_text(encoding="utf-8")
    assert "(version 20250114)" in text
    assert '(generator_version "9.0")' in text
    assert "20260101" not in text


def test_create_schematic_writes_kicad9_header(monkeypatch, tmp_path):
    monkeypatch.setenv("KICAD_MCP_KICAD_MAJOR", "9")
    sch = _load("schematic_module_v9", "schematic.py")
    with patch.object(sch, "Schematic", MagicMock()):
        sch.SchematicManager.create_schematic("s", path=str(tmp_path))
    text = (tmp_path / "s.kicad_sch").read_text(encoding="utf-8")
    assert "(version 20250114)" in text
    assert "20260101" not in text
