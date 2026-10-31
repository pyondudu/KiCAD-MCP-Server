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


# A 555-like part with pins on all four sides, and a dual op-amp whose power
# pins live in their own unit (3), as in the KiCad library.
LIB_IC = """(kicad_sch (version 20250114)
  (lib_symbols
    (symbol "Timer:NE555D"
      (property "Reference" "U" (at -10.16 8.89 0) (effects (font (size 1.27 1.27))))
      (property "Value" "NE555D" (at 2.54 8.89 0) (effects (font (size 1.27 1.27))))
      (symbol "NE555D_0_1"
        (rectangle (start -8.89 -7.62) (end 8.89 7.62) (stroke (width 0.254)) (fill (type none))))
      (symbol "NE555D_1_1"
        (pin power_in line (at 0 -10.16 90) (length 2.54) (name "GND") (number "1"))
        (pin input line (at -12.7 5.08 0) (length 3.81) (name "TR") (number "2"))
        (pin output line (at 12.7 5.08 180) (length 3.81) (name "Q") (number "3"))
        (pin input line (at -12.7 -5.08 0) (length 3.81) (name "R") (number "4"))
        (pin input line (at -12.7 0 0) (length 3.81) (name "CV") (number "5"))
        (pin input line (at 12.7 -5.08 180) (length 3.81) (name "THR") (number "6"))
        (pin input line (at 12.7 0 180) (length 3.81) (name "DIS") (number "7"))
        (pin power_in line (at 0 10.16 270) (length 2.54) (name "VCC") (number "8"))))
    (symbol "Amplifier_Operational:LM358"
      (property "Reference" "U" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
      (property "Value" "LM358" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
      (symbol "LM358_1_1"
        (polyline (pts (xy -5.08 5.08) (xy 5.08 0) (xy -5.08 -5.08) (xy -5.08 5.08)))
        (pin output line (at 7.62 0 180) (length 2.54) (name "~") (number "1"))
        (pin input line (at -7.62 -2.54 0) (length 2.54) (name "-") (number "2"))
        (pin input line (at -7.62 2.54 0) (length 2.54) (name "+") (number "3")))
      (symbol "LM358_2_1"
        (polyline (pts (xy -5.08 5.08) (xy 5.08 0) (xy -5.08 -5.08) (xy -5.08 5.08)))
        (pin input line (at -7.62 2.54 0) (length 2.54) (name "+") (number "5"))
        (pin input line (at -7.62 -2.54 0) (length 2.54) (name "-") (number "6"))
        (pin output line (at 7.62 0 180) (length 2.54) (name "~") (number "7")))
      (symbol "LM358_3_1"
        (pin power_in line (at -2.54 -7.62 90) (length 3.81) (name "V-") (number "4"))
        (pin power_in line (at -2.54 7.62 270) (length 3.81) (name "V+") (number "8")))))
"""


def _placed_unit(lib_id, ref, value, x, y, unit):
    return _placed(lib_id, ref, value, x, y, 0).replace("(unit 1)", f"(unit {unit})")


def test_ic_with_pins_on_every_side_keeps_fields_off_the_top_and_bottom_pin_wires():
    # NE555D at (101.6, 88.9): VCC at (101.6, 78.74), GND at (101.6, 99.06)
    block = _placed("Timer:NE555D", "U1", "NE555D", 101.6, 88.9, 0)
    b = autoplace_fields(block, LIB_IC + block + "\n)", {})
    ref, val = _pos(b, "Reference"), _pos(b, "Value")
    assert ref["x"] > 101.6 and val["x"] > 101.6, "text starts right of the pin wire"
    assert ref["y"] < 88.9 - 7.62 and val["y"] > 88.9 + 7.62
    assert b.count("(justify left)") == 2


@pytest.mark.parametrize(
    "unit, x, y",
    [(1, 101.6, 88.9), (2, 139.7, 91.44), (3, 73.66, 124.46)],
)
def test_multi_unit_fields_stay_beside_their_own_unit(unit, x, y):
    """Every unit was placed against the pins of all units (they share a
    reference), so U1C's fields landed beside U1A and U1A's Value on R1."""
    all_units_pins = {  # what PinLocator returns for "U1": every unit's pins
        "1": (109.22, 88.9),
        "2": (93.98, 91.44),
        "3": (93.98, 86.36),
        "5": (132.08, 88.9),
        "6": (132.08, 93.98),
        "7": (147.32, 91.44),
        "4": (71.12, 132.08),
        "8": (71.12, 116.84),
    }
    block = _placed_unit("Amplifier_Operational:LM358", "U1", "LM358", x, y, unit)
    b = autoplace_fields(block, LIB_IC + block + "\n)", all_units_pins)
    for prop in ("Reference", "Value"):
        p = _pos(b, prop)
        assert abs(p["x"] - x) < 12 and abs(p["y"] - y) < 12, f"{prop} of unit {unit} at {p}"


def test_power_unit_fields_clear_the_pin_names():
    block = _placed_unit("Amplifier_Operational:LM358", "U1", "LM358", 73.66, 124.46, 3)
    b = autoplace_fields(block, LIB_IC + block + "\n)", {})
    # pin line at x = 71.12; pin names are drawn just right of it
    assert _pos(b, "Reference")["x"] >= 71.12 + 2.54


def test_symbol_extent_covers_body_and_only_this_units_pins():
    from commands.field_autoplace import symbol_extent

    ne = _placed("Timer:NE555D", "U1", "NE555D", 101.6, 88.9, 0)
    box = symbol_extent(ne, LIB_IC + ne + "\n)")
    assert box == {"x_min": 88.9, "y_min": 78.74, "x_max": 114.3, "y_max": 99.06}

    c = _placed_unit("Amplifier_Operational:LM358", "U1", "LM358", 73.66, 124.46, 3)
    box = symbol_extent(c, LIB_IC + c + "\n)")
    assert box["x_min"] == box["x_max"] == 71.12, "power unit: just its two pins"
    assert (box["y_min"], box["y_max"]) == (116.84, 132.08)
