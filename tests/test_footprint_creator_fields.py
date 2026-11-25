"""create_footprint writes the Datasheet field hidden, as KiCad's own footprints do.

sync_schematic_to_board copies the symbol's datasheet URL into that field. While it
was visible, the URL was printed across the board on F.Fab.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from commands.footprint import FootprintCreator  # noqa: E402


def _property_block(text: str, name: str) -> str:
    start = text.index(f'(property "{name}"')
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"unterminated property {name}")


def test_datasheet_field_is_hidden(tmp_path):
    lib = tmp_path / "T.pretty"
    result = FootprintCreator().create_footprint(
        str(lib),
        "R_0805",
        pads=[
            {"number": "1", "type": "smd", "at": {"x": -0.9, "y": 0}, "size": {"w": 1, "h": 1.4}},
            {"number": "2", "type": "smd", "at": {"x": 0.9, "y": 0}, "size": {"w": 1, "h": 1.4}},
        ],
    )
    assert result["success"], result
    text = (lib / "R_0805.kicad_mod").read_text()
    assert re.search(r"\(hide yes\)", _property_block(text, "Datasheet"))
    # Reference and Value stay visible.
    assert "hide" not in _property_block(text, "Reference")
    assert "hide" not in _property_block(text, "Value")
