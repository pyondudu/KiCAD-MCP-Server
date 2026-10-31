"""sync_schematic_to_board warns when it leaves a part off the board."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from commands.schematic_handlers import _skipped_footprint_warning  # noqa: E402

pytestmark = pytest.mark.unit


def test_nothing_skipped_means_no_warning():
    assert _skipped_footprint_warning([]) is None


def test_every_skipped_part_is_named_with_its_reason():
    msg = _skipped_footprint_warning(
        [
            {
                "reference": "U1",
                "footprint": "Package_SO:SOIJ-8",
                "reason": "footprint not found in library",
            },
            {"reference": "R3", "footprint": ""},
        ]
    )
    assert msg.startswith("2 part(s) NOT placed on the board")
    assert "U1 (footprint not found in library)" in msg
    assert "R3 (skipped)" in msg
