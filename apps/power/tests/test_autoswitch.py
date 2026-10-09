import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import autoswitch  # noqa: E402

MODES = ["cool", "auto", "performance"]
ON = {"enabled": True, "battery": "cool", "ac": "performance"}


def test_default_when_no_file(tmp_path):
    cfg = autoswitch.load_config(str(tmp_path / "auto.json"))
    assert cfg == {"enabled": False, "battery": "cool", "ac": "auto"}


def test_save_then_load(tmp_path):
    path = str(tmp_path / "sub" / "auto.json")
    autoswitch.save_config(path, dict(ON), MODES)
    assert autoswitch.load_config(path) == ON


@pytest.mark.parametrize(
    "cfg",
    [
        {**ON, "battery": "ludicrous"},
        {**ON, "enabled": "yes"},
        {**ON, "extra": 1},
        {"enabled": True, "battery": "cool"},
    ],
)
def test_save_rejects_bad_config(tmp_path, cfg):
    with pytest.raises(ValueError):
        autoswitch.save_config(str(tmp_path / "auto.json"), cfg, MODES)


def test_corrupt_file_falls_back_to_default(tmp_path):
    path = tmp_path / "auto.json"
    path.write_text("{not json")
    assert autoswitch.load_config(str(path))["enabled"] is False


def test_decides_only_when_the_power_source_changes():
    assert autoswitch.decide(ON, on_ac=True, last_source=None) == "performance"
    assert autoswitch.decide(ON, on_ac=True, last_source="ac") is None
    assert autoswitch.decide(ON, on_ac=False, last_source="ac") == "cool"
    assert autoswitch.decide(ON, on_ac=False, last_source="battery") is None


def test_disabled_never_decides():
    off = {**ON, "enabled": False}
    assert autoswitch.decide(off, on_ac=True, last_source=None) is None
    assert autoswitch.decide(off, on_ac=False, last_source="ac") is None


def test_saved_file_is_plain_json(tmp_path):
    path = tmp_path / "auto.json"
    autoswitch.save_config(str(path), dict(ON), MODES)
    assert json.loads(path.read_text()) == ON
