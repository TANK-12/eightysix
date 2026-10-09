import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from history import History  # noqa: E402


def test_keeps_only_the_newest_points():
    h = History(max_points=3)
    for i in range(5):
        h.add({"t": i})
    assert [p["t"] for p in h.points()] == [2, 3, 4]


def test_points_is_a_copy():
    h = History(max_points=3)
    h.add({"t": 1})
    h.points().clear()
    assert len(h.points()) == 1
