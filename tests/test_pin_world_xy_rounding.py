"""
pin_world_xy must not leak float noise.

A Device:LED rotated 90 degrees at y=83.82 put its anode at 80.00999999999999,
and a mirrored connector put its pin at 55.879999999999995. Those values went
into tool replies and were written verbatim into wires snapped to the pin.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from commands.wire_dragger import WireDragger  # noqa: E402


@pytest.mark.unit
@pytest.mark.parametrize(
    "pin, sym, rot, mx, my, expected",
    [
        ((3.81, 0.0), (96.52, 83.82), 90, False, False, (96.52, 80.01)),
        ((-3.81, 0.0), (96.52, 83.82), 90, False, False, (96.52, 87.63)),
        ((-5.08, 0.0), (50.8, 76.2), 0, False, True, (55.88, 76.2)),
        ((-5.08, -2.54), (60.96, 81.28), 0, False, True, (66.04, 83.82)),
    ],
)
def test_pin_world_xy_is_exact_to_schematic_resolution(pin, sym, rot, mx, my, expected):
    x, y = WireDragger.pin_world_xy(pin[0], pin[1], sym[0], sym[1], rot, mx, my)
    assert (x, y) == expected
    assert repr(x) == repr(expected[0]) and repr(y) == repr(expected[1])


@pytest.mark.unit
def test_no_negative_zero():
    x, y = WireDragger.pin_world_xy(0.0, 0.0, 0.0, 0.0, 180, False, False)
    assert repr(x) == "0.0" and repr(y) == "0.0"
