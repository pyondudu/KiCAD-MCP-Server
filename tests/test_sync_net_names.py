"""
sync_schematic_to_board must name nets the way eeschema does.

The built-in walker named a sheet-local label "LED_A" where eeschema says
"/LED_A", so a synced board failed DRC schematic parity on every net. The
kicad-cli netlist is now the source of truth, and a net that was renamed in
the schematic carries its tracks and zones along like KiCad's F8 does.
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

NETLIST_XML = """<?xml version="1.0"?>
<export version="E">
  <components>
    <comp ref="R1"><value>330</value><footprint>R:R_0805</footprint></comp>
  </components>
  <nets>
    <net code="1" name="+5V">
      <node ref="J1" pin="1"/><node ref="R1" pin="1"/>
    </net>
    <net code="2" name="/LED_A">
      <node ref="R1" pin="2"/><node ref="D1" pin="2"/>
    </net>
    <net code="3" name="">
      <node ref="X1" pin="1"/>
    </net>
  </nets>
</export>
"""


def _interface() -> Any:
    from kicad_interface import KiCADInterface

    return KiCADInterface()


def _fake_export(xml: str):
    def run(cmd, **kwargs):
        Path(cmd[cmd.index("--output") + 1]).write_text(xml, encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    return run


@pytest.mark.unit
class TestCliPadNetMap:
    def test_uses_eeschema_net_names(self, tmp_path):
        iface = _interface()
        with (
            patch.object(iface.__class__, "_find_kicad_cli_static", return_value="/fake/kicad-cli"),
            patch("subprocess.run", side_effect=_fake_export(NETLIST_XML)),
        ):
            pad_map, names = iface._cli_pad_net_map(str(tmp_path / "x.kicad_sch"))

        assert pad_map[("R1", "2")] == "/LED_A"
        assert pad_map[("J1", "1")] == "+5V"
        assert names == {"+5V", "/LED_A"}
        assert ("X1", "1") not in pad_map, "unnamed nets are skipped"

    def test_none_without_kicad_cli(self, tmp_path):
        iface = _interface()
        with patch.object(iface.__class__, "_find_kicad_cli_static", return_value=None):
            assert iface._cli_pad_net_map(str(tmp_path / "x.kicad_sch")) is None

    def test_none_when_export_fails(self, tmp_path):
        iface = _interface()
        with (
            patch.object(iface.__class__, "_find_kicad_cli_static", return_value="/fake/kicad-cli"),
            patch("subprocess.run", return_value=MagicMock(returncode=3, stdout="", stderr="bad")),
        ):
            assert iface._cli_pad_net_map(str(tmp_path / "x.kicad_sch")) is None


def _item(net: str) -> MagicMock:
    item = MagicMock()
    item.GetNetname.return_value = net
    return item


def _board(pad_nets, tracks, zones, net_names):
    pads = [_item(n) for n in pad_nets]
    fp = MagicMock()
    fp.Pads.return_value = pads
    board = MagicMock()
    board.GetFootprints.return_value = [fp]
    board.GetTracks.return_value = tracks
    board.Zones.return_value = zones
    nets = {n: MagicMock(name=f"net_{n}") for n in net_names}
    by_name = MagicMock()
    by_name.has_key.side_effect = lambda n: n in nets
    by_name.__getitem__.side_effect = lambda n: nets[n]
    board.GetNetInfo.return_value.NetsByName.return_value = by_name
    return board, nets


@pytest.mark.unit
class TestCarryRenamedNets:
    def test_moves_copper_and_removes_old_net(self):
        iface = _interface()
        track, other, zone = _item("LED_A"), _item("GND"), _item("LED_A")
        board, nets = _board(
            ["/LED_A", "/LED_A", "GND"], [track, other], [zone], ["LED_A", "/LED_A", "GND"]
        )

        renamed = iface._carry_renamed_nets(board, {"LED_A": {"/LED_A"}}, {"/LED_A", "GND"})

        assert renamed == {"LED_A": "/LED_A"}
        track.SetNet.assert_called_once_with(nets["/LED_A"])
        zone.SetNet.assert_called_once_with(nets["/LED_A"])
        other.SetNet.assert_not_called()
        board.Remove.assert_called_once_with(nets["LED_A"])

    def test_split_net_is_left_alone(self):
        iface = _interface()
        track = _item("OLD")
        board, _ = _board(["A", "B"], [track], [], ["OLD", "A", "B"])

        assert iface._carry_renamed_nets(board, {"OLD": {"A", "B"}}, {"A", "B"}) == {}
        track.SetNet.assert_not_called()
        board.Remove.assert_not_called()

    def test_net_still_on_a_pad_is_left_alone(self):
        iface = _interface()
        track = _item("OLD")
        board, _ = _board(["OLD", "NEW"], [track], [], ["OLD", "NEW"])

        assert iface._carry_renamed_nets(board, {"OLD": {"NEW"}}, {"NEW"}) == {}
        track.SetNet.assert_not_called()
