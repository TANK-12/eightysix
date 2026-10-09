import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "helper"))

import forge_power as fp  # noqa: E402

GOOD = {
    "governor": "powersave",
    "turbo": "off",
    "max_freq_mhz": 1600,
    "epp": "power",
    "platform_profile": "cool",
    "pl1_watts": 12,
    "pl2_watts": 20,
    "pl1_duration_s": 60,
    "aspm": "powersupersave",
    "nmi_watchdog": False,
    "dirty_writeback_cs": 1500,
    "audio_power_save": 1,
    "wifi_power_save": True,
}

THROTTLED = """[GENERAL]
Enabled: True
Sysfs_Power_Path: /sys/class/power_supply/AC*/online
[BATTERY]
Update_Rate_s: 30
PL1_Tdp_W: 45
PL2_Tdp_W: 55
PL1_Duration_s: 28
HWP_Mode: False
[AC]
Update_Rate_s: 5
PL1_Tdp_W: 60
PL2_Tdp_W: 60
EPP_Mode: performance
HWP_Mode: True
[UNDERVOLT]
CORE: 0
GPU: 0
[ICCMAX]
CORE.AC: 105
"""

NOOP = lambda argv: None  # noqa: E731
CPU = "sys/devices/system/cpu"
CPU0_MAX = f"{CPU}/cpu0/cpufreq/scaling_max_freq"
CPU4_MAX = f"{CPU}/cpu4/cpufreq/scaling_max_freq"
CPU0_GOV = f"{CPU}/cpu0/cpufreq/scaling_governor"
CPU4_GOV = f"{CPU}/cpu4/cpufreq/scaling_governor"
NO_TURBO = f"{CPU}/intel_pstate/no_turbo"


def test_good_settings_pass():
    assert fp.validate(dict(GOOD)) == GOOD


@pytest.mark.parametrize(
    "key,value",
    [
        ("pl1_watts", 61),
        ("pl2_watts", 4),
        ("pl1_watts", "12"),
        ("pl1_watts", True),
        ("platform_profile", "turbo"),
        ("governor", "ondemand; rm -rf /"),
        ("governor", "schedutil"),
        ("turbo", "never"),
        ("turbo", True),
        ("epp", ""),
        ("dirty_writeback_cs", 10),
        ("nmi_watchdog", "no"),
        ("max_freq_mhz", 399),
        ("max_freq_mhz", 5001),
        ("max_freq_mhz", "fast"),
        ("max_freq_mhz", True),
        ("pl1_duration_s", 0),
        ("pl1_duration_s", 3601),
        ("pl1_duration_s", "60"),
        ("pl1_duration_s", True),
    ],
)
def test_bad_values_rejected(key, value):
    s = dict(GOOD)
    s[key] = value
    with pytest.raises(ValueError):
        fp.validate(s)


def test_auto_cpufreq_setting_is_gone():
    with pytest.raises(ValueError):
        fp.validate({"governor_force": "powersave"})


def test_max_freq_accepts_max():
    assert fp.validate({"max_freq_mhz": "max"}) == {"max_freq_mhz": "max"}


def test_unknown_key_rejected():
    with pytest.raises(ValueError):
        fp.validate({**GOOD, "exec": "sh"})


def test_burst_below_sustained_rejected():
    with pytest.raises(ValueError):
        fp.validate({**GOOD, "pl1_watts": 30, "pl2_watts": 20})


def test_partial_settings_allowed():
    assert fp.validate({"turbo": "on"}) == {"turbo": "on"}


def test_throttled_rewrite_changes_only_limits():
    out = fp.rewrite_throttled(THROTTLED, {"PL1_Tdp_W": 12, "PL2_Tdp_W": 20})
    assert out.count("PL1_Tdp_W: 12") == 2
    assert out.count("PL2_Tdp_W: 20") == 2
    assert "HWP_Mode: True" not in out
    assert out.count("HWP_Mode: False") == 2
    tail = THROTTLED[THROTTLED.index("[UNDERVOLT]") :]
    assert out.endswith(tail)
    assert out.split("[BATTERY]")[0] == THROTTLED.split("[BATTERY]")[0]
    assert "PL1_Duration_s: 28" in out and "EPP_Mode: performance" in out


def test_throttled_rewrite_duration_only_leaves_wattage_and_hwp_alone():
    out = fp.rewrite_throttled(THROTTLED, {"PL1_Duration_s": 3600})
    assert out.count("PL1_Duration_s: 3600") == 1
    assert "PL1_Tdp_W: 45" in out and "PL2_Tdp_W: 55" in out
    assert "HWP_Mode: False" in out and "HWP_Mode: True" in out


def _fake_sys(tmp_path):
    files = {
        f"{CPU}/cpu0/cpufreq/energy_performance_preference": "balance_power",
        f"{CPU}/cpu4/cpufreq/energy_performance_preference": "balance_power",
        CPU0_MAX: "2500000",
        CPU4_MAX: "1900000",
        CPU0_GOV: "performance",
        CPU4_GOV: "performance",
        NO_TURBO: "0",
        "sys/firmware/acpi/platform_profile": "balanced",
        "sys/module/pcie_aspm/parameters/policy": "[default] performance",
        "proc/sys/kernel/nmi_watchdog": "1",
        "proc/sys/vm/dirty_writeback_centisecs": "500",
        "sys/module/snd_hda_intel/parameters/power_save": "10",
        "etc/throttled.conf": THROTTLED,
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_apply_writes_into_root(tmp_path):
    root = _fake_sys(tmp_path)
    calls = []
    results = fp.apply(dict(GOOD), root=str(root), run=lambda argv: calls.append(argv))
    epp = root / f"{CPU}/cpu4/cpufreq/energy_performance_preference"
    assert epp.read_text() == "power"
    assert (root / CPU0_GOV).read_text() == "powersave"
    assert (root / CPU4_GOV).read_text() == "powersave"
    assert (root / NO_TURBO).read_text() == "1"
    assert (root / CPU0_MAX).read_text() == "1600000"
    assert (root / CPU4_MAX).read_text() == "1600000"
    assert (root / "sys/firmware/acpi/platform_profile").read_text() == "cool"
    assert (root / "proc/sys/kernel/nmi_watchdog").read_text() == "0"
    assert (root / "proc/sys/vm/dirty_writeback_centisecs").read_text() == "1500"
    assert "PL1_Tdp_W: 12" in (root / "etc/throttled.conf").read_text()
    assert ["systemctl", "restart", "throttled.service"] in calls
    assert not any(argv[0] == "auto-cpufreq" for argv in calls), calls
    assert all(r["ok"] for r in results), results


def test_turbo_on_and_governor_before_energy_preference(tmp_path):
    root = _fake_sys(tmp_path)
    (root / NO_TURBO).write_text("1")
    results = fp.apply(
        {"epp": "performance", "governor": "performance", "turbo": "on"},
        root=str(root),
        run=NOOP,
    )
    assert (root / NO_TURBO).read_text() == "0"
    order = [r["setting"] for r in results]
    assert order.index("turbo") < order.index("governor") < order.index("epp")


def test_max_freq_max_lifts_the_cap(tmp_path):
    root = _fake_sys(tmp_path)
    results = fp.apply({"max_freq_mhz": "max"}, root=str(root), run=NOOP)
    assert (root / CPU0_MAX).read_text() == str(fp.NO_CAP_KHZ)
    assert (root / CPU4_MAX).read_text() == str(fp.NO_CAP_KHZ)
    assert results == [{"setting": "max_freq_mhz", "ok": True}]


def test_settings_without_power_limits_leave_throttled_alone(tmp_path):
    root = _fake_sys(tmp_path)
    calls = []
    settings = {
        k: v
        for k, v in GOOD.items()
        if k not in ("pl1_watts", "pl2_watts", "pl1_duration_s")
    }
    fp.apply(settings, root=str(root), run=lambda argv: calls.append(argv))
    assert (root / "etc/throttled.conf").read_text() == THROTTLED
    assert ["systemctl", "restart", "throttled.service"] not in calls


def test_apply_reports_failed_write_without_stopping(tmp_path):
    root = _fake_sys(tmp_path)
    (root / "sys/firmware/acpi/platform_profile").unlink()
    results = fp.apply(
        {"platform_profile": "cool", "nmi_watchdog": False},
        root=str(root),
        run=NOOP,
    )
    by = {r["setting"]: r for r in results}
    assert by["platform_profile"]["ok"] is False
    assert by["nmi_watchdog"]["ok"] is True


def test_apply_refuses_invalid_before_writing(tmp_path):
    root = _fake_sys(tmp_path)
    with pytest.raises(ValueError):
        fp.apply({**GOOD, "pl1_watts": 99}, root=str(root), run=NOOP)
    assert (root / "proc/sys/kernel/nmi_watchdog").read_text() == "1"


def test_pci_runtime_pm_lets_every_device_sleep(tmp_path):
    controls = []
    for dev in ("0000:00:12.0", "0000:00:1f.6"):
        control = tmp_path / "sys/bus/pci/devices" / dev / "power/control"
        control.parent.mkdir(parents=True)
        control.write_text("on")
        controls.append(control)
    results = fp.apply({"pci_runtime_pm": "auto"}, root=str(tmp_path), run=NOOP)
    assert [c.read_text() for c in controls] == ["auto", "auto"]
    assert results == [{"setting": "pci_runtime_pm", "ok": True}]
    with pytest.raises(ValueError):
        fp.validate({"pci_runtime_pm": "off"})


def _card(root, rp0="1200", cur_max="1200"):
    card = root / "sys/class/drm/card1"
    card.mkdir(parents=True, exist_ok=True)
    (card / "gt_RP0_freq_mhz").write_text(rp0)
    (card / "gt_max_freq_mhz").write_text(cur_max)
    return card


def test_gpu_cap_and_lift(tmp_path):
    card = _card(tmp_path)
    fp.apply({"gpu_max_freq_mhz": 500}, root=str(tmp_path), run=NOOP)
    assert (card / "gt_max_freq_mhz").read_text() == "500"
    results = fp.apply({"gpu_max_freq_mhz": "max"}, root=str(tmp_path), run=NOOP)
    assert (card / "gt_max_freq_mhz").read_text() == "1200"
    assert results == [{"setting": "gpu_max_freq_mhz", "ok": True}]


@pytest.mark.parametrize("value", [50, 5000, "1200", True, "fast"])
def test_gpu_cap_rejects_bad_values(value):
    with pytest.raises(ValueError):
        fp.validate({"gpu_max_freq_mhz": value})


def test_keyboard_backlight_is_clamped_to_the_leds_max(tmp_path):
    led = tmp_path / "sys/class/leds/dell::kbd_backlight"
    led.mkdir(parents=True)
    (led / "max_brightness").write_text("2\n")
    (led / "brightness").write_text("1")
    fp.apply({"kbd_backlight": 0}, root=str(tmp_path), run=NOOP)
    assert (led / "brightness").read_text() == "0"
    fp.apply({"kbd_backlight": 3}, root=str(tmp_path), run=NOOP)
    assert (led / "brightness").read_text() == "2"


def test_usb_autosuspend_skips_mice_and_keyboards(tmp_path):
    usb = tmp_path / "sys/bus/usb/devices"
    controls = {}
    for dev, iface_class in (("1-3", "0e"), ("1-4", "03"), ("usb1", "09")):
        (usb / dev / "power").mkdir(parents=True)
        (usb / dev / "power/control").write_text("on")
        iface = usb / f"{dev}:1.0"
        iface.mkdir()
        (iface / "bInterfaceClass").write_text(iface_class + "\n")
        controls[dev] = usb / dev / "power/control"
    fp.apply({"usb_autosuspend": True}, root=str(tmp_path), run=NOOP)
    assert controls["1-3"].read_text() == "auto"  # webcam
    assert controls["usb1"].read_text() == "auto"  # hub
    assert controls["1-4"].read_text() == "on"  # mouse stays awake
    fp.apply({"usb_autosuspend": False}, root=str(tmp_path), run=NOOP)
    assert controls["1-3"].read_text() == "on"
