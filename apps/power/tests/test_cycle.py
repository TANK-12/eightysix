import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from cycle import next_mode  # noqa: E402

NAMES = ["cool", "auto", "performance"]


def test_steps_in_slider_order():
    assert next_mode(NAMES, "cool") == "auto"
    assert next_mode(NAMES, "auto") == "performance"


def test_wraps_back_to_the_start():
    assert next_mode(NAMES, "performance") == "cool"


def test_unknown_or_no_mode_starts_at_the_first():
    assert next_mode(NAMES, None) == "cool"
    assert next_mode(NAMES, "deleted-mode") == "cool"
