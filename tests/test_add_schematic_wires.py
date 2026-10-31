"""
add_schematic_wires draws many wires in one call, and an endpoint that lands
on another wire or a label is not reported as floating.

Drawing a 3-part regulator schematic took 21 add_schematic_wire calls, and
every T-junction endpoint came back with "the wire may be floating" because
only pins were checked.
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

EMPTY = """(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "9.0")
\t(uuid "bbbb2222-2222-2222-2222-bbbbbbbbbbbb")
\t(paper "A4")
\t(lib_symbols)
\t(label "OUT"
\t\t(at 150 50 0)
\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t(uuid "cccc3333-3333-3333-3333-cccccccccccc")
\t)
\t(sheet_instances (path "/" (page "1")))
)
"""


def _iface() -> Any:
    with patch("kicad_interface.USE_IPC_BACKEND", False):
        from kicad_interface import KiCADInterface

        iface = KiCADInterface.__new__(KiCADInterface)
    iface._reload_kicad_schematic = lambda *a, **k: None
    return iface


def _sch(tmp_path: Path) -> Path:
    f = tmp_path / "w.kicad_sch"
    f.write_text(EMPTY, encoding="utf-8")
    return f


@pytest.mark.unit
class TestAddSchematicWires:
    def test_t_and_corner_endpoints_are_not_floating(self, tmp_path):
        sch = _sch(tmp_path)
        r = _iface()._handle_add_schematic_wires(
            {
                "schematicPath": str(sch),
                "wires": [
                    [[100, 50], [120, 50]],  # rail
                    [[110, 50], [110, 60]],  # T off the middle of the rail
                    [[120, 50], [120, 40], [130, 40]],  # continues from the rail end
                    [[130, 40], [150, 40], [150, 50]],  # ends on the OUT label
                ],
            }
        )
        assert r["success"] is True and r["added_count"] == 4
        floating = {w["index"]: w.get("warnings", []) for w in r["wires"]}
        # Only the open ends (rail start, T foot) touch nothing else.
        assert [i for i, w in floating.items() if w] == [0, 1]
        assert len(floating[0]) == 1 and "start point [100, 50]" in floating[0][0]
        assert len(floating[1]) == 1 and "end point [110, 60]" in floating[1][0]
        assert r["floating_endpoints"] == 2
        assert sch.read_text(encoding="utf-8").count("(wire") >= 4

    def test_rejects_empty_list(self, tmp_path):
        r = _iface()._handle_add_schematic_wires(
            {"schematicPath": str(_sch(tmp_path)), "wires": []}
        )
        assert r["success"] is False

    def test_short_wire_is_reported_not_raised(self, tmp_path):
        r = _iface()._handle_add_schematic_wires(
            {"schematicPath": str(_sch(tmp_path)), "wires": [[[1, 1]], [[0, 0], [5, 0]]]}
        )
        assert r["failed_count"] == 1 and r["added_count"] == 1
        assert r["wires"][0]["success"] is False


@pytest.mark.unit
def test_single_wire_ending_on_existing_wire_is_not_floating(tmp_path):
    sch = _sch(tmp_path)
    iface = _iface()
    iface._handle_add_schematic_wire(
        {"schematicPath": str(sch), "waypoints": [[100, 50], [120, 50]]}
    )
    r = iface._handle_add_schematic_wire(
        {"schematicPath": str(sch), "waypoints": [[110, 70], [110, 50]]}
    )
    assert r["success"] is True
    warnings = r.get("warnings", [])
    assert len(warnings) == 1 and "start point [110, 70]" in warnings[0]
    assert "end point" not in " ".join(warnings)
