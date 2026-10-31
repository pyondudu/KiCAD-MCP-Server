"""autoroute says whether every connection got routed.

The reply used to carry only track and via counts, so a run that left a net
unrouted looked the same as a finished board until DRC was run.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from commands.freerouting import _unrouted_connection_count  # noqa: E402

pytestmark = pytest.mark.unit


def _board(count):
    board = MagicMock()
    board.GetConnectivity.return_value.GetUnconnectedCount.return_value = count
    return board


def test_count_comes_from_the_rebuilt_connectivity():
    board = _board(3)
    assert _unrouted_connection_count(board) == 3
    board.BuildConnectivity.assert_called_once()
    board.GetConnectivity.return_value.GetUnconnectedCount.assert_called_once_with(False)


def test_zero_means_fully_routed():
    assert _unrouted_connection_count(_board(0)) == 0


def test_unwrapped_swig_pointer_gives_none_not_a_crash():
    board = MagicMock()
    board.GetConnectivity.return_value = object()  # no GetUnconnectedCount
    assert _unrouted_connection_count(board) is None
