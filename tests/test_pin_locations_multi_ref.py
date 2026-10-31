"""get_schematic_pin_locations takes several references in one call.

Wiring a five-part circuit took five calls just to learn the pin positions;
``references`` returns them all, and lists the ones that were not found.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from test_issue_404_pin_transform import (  # noqa: E402
    _make_iface,
    _schematic_with,
    _symbol_sexp,
)

pytestmark = pytest.mark.unit


def _two_parts() -> Path:
    return _schematic_with(
        _symbol_sexp("Device:R", "R1", 100.0, 100.0, 0)
        + _symbol_sexp("Device:LED", "D1", 120.0, 100.0, 90)
    )


def test_references_returns_every_part_and_lists_missing():
    path = _two_parts()
    result = _make_iface()._handle_get_schematic_pin_locations(
        {"schematicPath": str(path), "references": ["R1", "D1", "U9"]}
    )
    assert result["success"] is True
    comps = result["components"]
    assert set(comps) == {"R1", "D1"}
    assert (comps["R1"]["1"]["x"], comps["R1"]["1"]["y"]) == (100.0, 96.19)
    assert (comps["D1"]["2"]["x"], comps["D1"]["2"]["y"]) == (120.0, 96.19)
    assert result["missing"] == ["U9"]


def test_single_reference_keeps_the_old_reply_shape():
    path = _two_parts()
    result = _make_iface()._handle_get_schematic_pin_locations(
        {"schematicPath": str(path), "reference": "R1"}
    )
    assert result["success"] is True
    assert result["reference"] == "R1"
    assert set(result["pins"]) == {"1", "2"}


def test_no_reference_at_all_is_an_error():
    result = _make_iface()._handle_get_schematic_pin_locations({"schematicPath": "x"})
    assert result["success"] is False
