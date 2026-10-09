import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import modes  # noqa: E402


def test_shipped_modes_load_and_validate():
    loaded = modes.load_modes()
    names = [m["name"] for m in loaded]
    assert names == ["saver", "cool", "auto", "performance"]
    for m in loaded:
        assert m["label"] and m["settings"]


def test_new_mode_file_is_picked_up(tmp_path):
    (tmp_path / "b.json").write_text(
        json.dumps({"name": "b", "label": "B", "order": 2, "settings": {"turbo": "on"}})
    )
    (tmp_path / "a.json").write_text(
        json.dumps(
            {"name": "a", "label": "A", "order": 1, "settings": {"epp": "power"}}
        )
    )
    assert [m["name"] for m in modes.load_modes(str(tmp_path))] == ["a", "b"]


def test_mode_with_bad_setting_is_rejected(tmp_path):
    (tmp_path / "x.json").write_text(
        json.dumps(
            {"name": "x", "label": "X", "order": 1, "settings": {"pl1_watts": 200}}
        )
    )
    with pytest.raises(ValueError, match="x.json"):
        modes.load_modes(str(tmp_path))


def test_apply_mode_pipes_settings_to_helper():
    seen = {}

    def fake_run(argv, stdin_text):
        seen["argv"] = argv
        seen["stdin"] = json.loads(stdin_text)
        return {"mode": "cool", "results": []}

    modes.apply_mode("cool", run=fake_run, set_refresh=lambda hz: "ok")
    assert seen["argv"] == ["sudo", "-n", modes.HELPER, "apply", "--mode", "cool"]
    assert seen["stdin"]["max_freq_mhz"] == 1600


def test_apply_unknown_mode():
    with pytest.raises(KeyError):
        modes.apply_mode("ludicrous", run=lambda a, s: {})


def test_shipped_modes_keep_the_users_power_limits():
    # The 45/55 W throttled limits are deliberate; no shipped mode may rewrite them.
    by_name = {m["name"]: m["settings"] for m in modes.load_modes()}
    for name, settings in by_name.items():
        assert "pl1_watts" not in settings and "pl2_watts" not in settings, name
    assert by_name["cool"]["max_freq_mhz"] == 1600
    assert by_name["auto"]["max_freq_mhz"] == "max"
    assert by_name["performance"]["max_freq_mhz"] == "max"
    assert by_name["cool"]["pl1_duration_s"] == 28
    assert by_name["auto"]["pl1_duration_s"] == 28
    assert by_name["performance"]["pl1_duration_s"] == 3600


def test_shipped_modes_do_not_need_auto_cpufreq():
    by_name = {m["name"]: m["settings"] for m in modes.load_modes()}
    for name, settings in by_name.items():
        assert "governor_force" not in settings, name
    assert by_name["cool"]["turbo"] == "off"
    assert by_name["performance"]["turbo"] == "on"
    assert by_name["performance"]["governor"] == "performance"


def test_apply_mode_sets_refresh_after_the_helper():
    calls = []

    def helper(argv, stdin_text):
        calls.append("helper")
        return {"mode": "performance", "results": []}

    def refresh(hz):
        calls.append(hz)
        return f"switched to {hz} Hz"

    out = modes.apply_mode("performance", run=helper, set_refresh=refresh)
    assert calls == ["helper", 60]
    assert out["display"] == "switched to 60 Hz"


def test_mode_without_display_leaves_the_screen_alone():
    seen = []
    out = modes.apply_mode(
        "auto", run=lambda a, s: {"results": []}, set_refresh=seen.append
    )
    assert seen == []
    assert "display" not in out


@pytest.mark.parametrize(
    "display", [{"refresh_hz": 1000}, {"refresh_hz": "60"}, {"refresh_hz": 60, "x": 1}]
)
def test_bad_display_block_is_rejected(tmp_path, display):
    (tmp_path / "x.json").write_text(
        json.dumps(
            {
                "name": "x",
                "label": "X",
                "order": 1,
                "settings": {"turbo": "on"},
                "display": display,
            }
        )
    )
    with pytest.raises(ValueError, match="x.json"):
        modes.load_modes(str(tmp_path))


def test_saver_is_the_most_frugal_mode_and_others_lift_its_caps():
    by_name = {m["name"]: m for m in modes.load_modes()}
    saver = by_name["saver"]["settings"]
    assert modes.load_modes()[0]["name"] == "saver"
    assert saver["turbo"] == "off" and saver["max_freq_mhz"] < 1600
    assert saver["gpu_max_freq_mhz"] != "max" and saver["usb_autosuspend"] is True
    assert by_name["saver"]["display"]["refresh_hz"] == 48
    for name in ("cool", "auto", "performance"):
        assert by_name[name]["settings"]["gpu_max_freq_mhz"] == "max", name


@pytest.mark.parametrize(
    "block",
    [{"nice": 25}, {"nice": "19"}, {"nice": 19, "efficiency_cores_only": 1}, {"x": 1}],
)
def test_bad_background_block_is_rejected(tmp_path, block):
    good = json.load(open(os.path.join(modes.MODES_DIR, "saver.json")))
    (tmp_path / "m.json").write_text(json.dumps({**good, "background_tasks": block}))
    with pytest.raises(ValueError):
        modes.load_modes(str(tmp_path))


def test_saver_squeezes_background_tasks():
    saver = next(m for m in modes.load_modes() if m["name"] == "saver")
    assert saver["background_tasks"] == {"nice": 19, "efficiency_cores_only": True}
