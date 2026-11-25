"""autoroute refuses a boardPath that is not the loaded board.

It routes the loaded board and saves it to boardPath, so a boardPath naming
another file was overwritten with the loaded board's copper.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from commands.freerouting import FreeroutingCommands  # noqa: E402


def _cmds(loaded: Path) -> FreeroutingCommands:
    cc = FreeroutingCommands.__new__(FreeroutingCommands)
    board = MagicMock(name="board")
    board.GetFileName.return_value = str(loaded)
    cc.board = board
    return cc


def test_other_board_path_is_refused_and_left_untouched(tmp_path):
    loaded = tmp_path / "a" / "a.kicad_pcb"
    other = tmp_path / "b" / "b.kicad_pcb"
    for p in (loaded, other):
        p.parent.mkdir()
        p.write_text("(kicad_pcb)")
    cc = _cmds(loaded)
    with patch.dict(sys.modules, {"pcbnew": MagicMock()}):
        result = cc.autoroute({"boardPath": str(other)})
    assert result["success"] is False
    assert "not the loaded board" in result["message"]
    assert "open_board" in result["errorDetails"]
    cc.board.Save.assert_not_called()
    assert other.read_text() == "(kicad_pcb)"


def test_same_board_through_another_spelling_is_accepted(tmp_path):
    loaded = tmp_path / "a" / "a.kicad_pcb"
    loaded.parent.mkdir()
    loaded.write_text("(kicad_pcb)")
    cc = _cmds(loaded)
    spelled = tmp_path / "a" / ".." / "a" / "a.kicad_pcb"
    with patch.dict(sys.modules, {"pcbnew": MagicMock()}):
        # A missing jar is the next check: reaching it means the path passed.
        result = cc.autoroute({"boardPath": str(spelled), "freeroutingJar": "/nonexistent.jar"})
    assert result["message"] == "Freerouting JAR not found"
