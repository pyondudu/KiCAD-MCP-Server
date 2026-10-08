"""
Reference/Value placement must read like an eeschema-placed symbol.

Before: field angle 0 on rotated symbols (text drawn vertically), text placed
on connector pins / LED arrows, power-symbol values mirrored below the wire,
and #PWR references un-hidden.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from commands.field_autoplace import autoplace_fields  # noqa: E402
from commands.schematic_text_utils import (  # noqa: E402
    _extract_property_position,
    _extract_property_visible,
)

LIB = """(kicad_sch (version 20250114)
  (lib_symbols
    (symbol "Device:R"
      (property "Reference" "R" (at 2.032 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "R" (at 0 0 90) (effects (font (size 1.27 1.27))))
      (symbol "R_0_1"
        (rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254)) (fill (type none))))
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27) (name "~") (number "1"))
        (pin passive line (at 0 -3.81 90) (length 1.27) (name "~") (number "2"))))
    (symbol "Device:LED"
      (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "LED" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (symbol "LED_0_1"
        (polyline (pts (xy -1.27 -1.27) (xy -1.27 1.27)))
        (polyline (pts (xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27)))
        (polyline (pts (xy -3.048 -0.762) (xy -4.572 -2.286)))
        (polyline (pts (xy -1.778 -0.762) (xy -3.302 -2.286))))
      (symbol "LED_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54) (name "K") (number "1"))
        (pin passive line (at 3.81 0 180) (length 2.54) (name "A") (number "2"))))
    (symbol "power:+5V"
      (power)
      (property "Reference" "#PWR" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Value" "+5V" (at 0 3.556 0) (effects (font (size 1.27 1.27))))
      (symbol "+5V_0_1"
        (polyline (pts (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27)))
        (polyline (pts (xy 0 0) (xy 0 2.54))))
      (symbol "+5V_1_1"
        (pin power_in line (at 0 0 90) (length 0) (name "~") (number "1")))))
"""


def _placed(lib_id, ref, value, x, y, rot, extra="", ref_flags="", mirror=""):
    return (
        f'(symbol (lib_id "{lib_id}") (at {x} {y} {rot}){mirror} (unit 1)\n'
        f'  (property "Reference" "{ref}" (at {x} {y} 0){ref_flags}\n'
        f"    (effects (font (size 1.27 1.27))))\n"
        f'  (property "Value" "{value}" (at {x} {y} 0){extra}\n'
        f"    (effects (font (size 1.27 1.27))))\n"
        f")"
    )


def _place(block, pins):
    return autoplace_fields(block, LIB + block + "\n)", pins)


def _pos(block, prop):
    return _extract_property_position(block, prop)


def test_vertical_resistor_fields_right_of_body():
    b = _place(_placed("Device:R", "R1", "330", 50, 50, 0), {"1": (50, 46.19), "2": (50, 53.81)})
    ref, val = _pos(b, "Reference"), _pos(b, "Value")
    assert ref["x"] > 51.016 and val["x"] == ref["x"]
    assert ref["y"] < val["y"]
    assert ref["angle"] == 0 and val["angle"] == 0
    assert "(justify left)" in b


def test_horizontal_resistor_fields_above_and_below_read_horizontally():
    b = _place(_placed("Device:R", "R2", "10k", 50, 50, 90), {"1": (46.19, 50), "2": (53.81, 50)})
    ref, val = _pos(b, "Reference"), _pos(b, "Value")
    assert ref["y"] < 50 - 1.016 and val["y"] > 50 + 1.016
    assert ref["x"] == pytest.approx(50) and val["x"] == pytest.approx(50)
    assert ref["angle"] == 90 and val["angle"] == 90, "angle 90 draws horizontally at rot 90"
    assert "justify" not in b


def test_led_rotated_90_clears_arrows_and_compensates_justify():
    b = _place(_placed("Device:LED", "D1", "LED", 50, 50, 90), {"1": (50, 53.81), "2": (50, 46.19)})
    ref = _pos(b, "Reference")
    # rot 90 maps the arrows (lib x -4.572) to the right of the body
    assert ref["x"] > 50 + 2.286
    assert ref["angle"] == 90
    # eeschema mirrors justification at rot 90, so "right" is stored to draw left-aligned
    assert "(justify right)" in b


def test_power_symbol_value_above_arrow_and_reference_stays_hidden():
    block = _placed("power:+5V", "#PWR01", "+5V", 50, 50, 0, ref_flags=" (hide yes)")
    b = _place(block, {"1": (50, 50)})
    assert _pos(b, "Value")["y"] == pytest.approx(50 - 3.556)
    assert _extract_property_visible(b, "Reference") is False
    assert _extract_property_visible(b, "Value") is True


def test_hidden_value_is_not_unhidden():
    block = _placed("Device:R", "R3", "1k", 50, 50, 0, extra=" (hide yes)")
    b = _place(block, {"1": (50, 46.19), "2": (50, 53.81)})
    assert _extract_property_visible(b, "Value") is False
    assert _pos(b, "Reference")["y"] == pytest.approx(50), "single shown field is centred"


def test_do_not_autoplace_field_is_left_alone():
    block = _placed("Device:R", "R4", "1k", 50, 50, 0, extra=" (do_not_autoplace yes)")
    b = _place(block, {"1": (50, 46.19), "2": (50, 53.81)})
    assert _pos(b, "Value") == {"x": 50.0, "y": 50.0, "angle": 0.0}
    assert _pos(b, "Reference")["x"] > 51


def test_unknown_lib_symbol_leaves_block_unchanged():
    block = _placed("Nope:X", "U1", "x", 50, 50, 0)
    assert _place(block, {}) == block
