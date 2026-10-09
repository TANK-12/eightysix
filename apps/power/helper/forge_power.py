#!/usr/bin/python3 -I
"""Root helper for the Forge Power app: applies a checked set of power settings.

Installed root-owned as /usr/local/bin/forge-power and run through a single
NOPASSWD sudoers line, so every argument and stdin value is treated as hostile:
only the settings named in CHOICES / RANGES / FLAGS are accepted, and nothing
here ever builds a shell command.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from typing import Callable

CHOICES = {
    "governor": ("powersave", "performance"),
    "turbo": ("on", "off"),
    "epp": ("default", "performance", "balance_performance", "balance_power", "power"),
    "platform_profile": ("cool", "quiet", "balanced", "performance"),
    "aspm": ("default", "performance", "powersave", "powersupersave"),
    "pci_runtime_pm": ("auto", "on"),
}
RANGES = {
    "pl1_watts": (5, 55),
    "pl2_watts": (5, 55),
    "pl1_duration_s": (1, 3600),
    "dirty_writeback_cs": (100, 6000),
    "audio_power_save": (0, 60),
    "kbd_backlight": (0, 3),
}
FLAGS = ("nmi_watchdog", "wifi_power_save", "usb_autosuspend")
# USB interface class for mice and keyboards: these stay awake so input never lags.
USB_HID_CLASS = "03"

STATE_FILE = "/var/lib/forge-power/last.json"
MODE_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")
RAPL = "sys/class/powercap/intel-rapl:0"
# Above any real frequency: the kernel clamps it to each core's own hardware max,
# which also follows turbo being switched on or off later.
NO_CAP_KHZ = 9_999_999

Runner = Callable[[list[str]], object]


def validate(settings: object) -> dict:
    if not isinstance(settings, dict):
        raise ValueError("settings must be a JSON object")
    for key, value in settings.items():
        if key == "max_freq_mhz":
            if value != "max" and (type(value) is not int or not 400 <= value <= 5000):
                raise ValueError(
                    'max_freq_mhz must be "max" or a whole number from 400 to 5000'
                )
        elif key == "gpu_max_freq_mhz":
            if value != "max" and (type(value) is not int or not 100 <= value <= 2000):
                raise ValueError(
                    'gpu_max_freq_mhz must be "max" or a whole number from 100 to 2000'
                )
        elif key in CHOICES:
            if not isinstance(value, str) or value not in CHOICES[key]:
                raise ValueError(f"{key} must be one of {', '.join(CHOICES[key])}")
        elif key in RANGES:
            lo, hi = RANGES[key]
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{key} must be a whole number from {lo} to {hi}")
        elif key in FLAGS:
            if type(value) is not bool:
                raise ValueError(f"{key} must be true or false")
        else:
            raise ValueError(f"unknown setting {key!r}")
    if ("pl1_watts" in settings) != ("pl2_watts" in settings):
        raise ValueError("pl1_watts and pl2_watts must be set together")
    if "pl1_watts" in settings and settings["pl2_watts"] < settings["pl1_watts"]:
        raise ValueError("pl2_watts (burst) cannot be below pl1_watts (sustained)")
    return settings


def rewrite_throttled(text: str, overrides: dict[str, object]) -> str:
    """Set the given keys in throttled's [BATTERY] and [AC] sections. Every
    other line is kept byte-for-byte. When PL1_Tdp_W/PL2_Tdp_W are among the
    overrides, HWP handling is also turned off, since HWP otherwise overrides
    the energy preference set here."""
    forcing_power = "PL1_Tdp_W" in overrides or "PL2_Tdp_W" in overrides
    out = []
    section = ""
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
        elif section in ("BATTERY", "AC"):
            key = stripped.split(":", 1)[0].strip()
            ending = "\n" if line.endswith("\n") else ""
            if key in overrides:
                line = f"{key}: {overrides[key]}{ending}"
            elif key == "HWP_Mode" and forcing_power:
                line = f"HWP_Mode: False{ending}"
        out.append(line)
    return "".join(out)


def _run(argv: list[str]) -> object:
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60)


def _write(path: str, value: str) -> None:
    # No O_CREAT: a missing control file must fail, not be created as root.
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(value)


def _write_all(pattern: str, value: str) -> None:
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(pattern)
    for path in paths:
        _write(path, value)


def _read(path: str) -> str:
    with open(path, encoding="ascii") as handle:
        return handle.read().strip()


def _gpu_cap(root: str, cap: object) -> None:
    cards = sorted(glob.glob(os.path.join(root, "sys/class/drm/card*/gt_max_freq_mhz")))
    if not cards:
        raise FileNotFoundError("no Intel GPU frequency control")
    for path in cards:
        top = _read(os.path.join(os.path.dirname(path), "gt_RP0_freq_mhz"))
        _write(path, top if cap == "max" else str(min(int(str(cap)), int(top))))


def _kbd_backlight(root: str, level: int) -> str | None:
    leds = sorted(glob.glob(os.path.join(root, "sys/class/leds/*kbd_backlight")))
    for led in leds:
        top = int(_read(os.path.join(led, "max_brightness")))
        _write(os.path.join(led, "brightness"), str(min(level, top)))
    return None if leds else "no keyboard backlight"


def _usb_autosuspend(root: str, on: bool) -> str | None:
    kept = 0
    for control in sorted(
        glob.glob(os.path.join(root, "sys/bus/usb/devices/*/power/control"))
    ):
        dev = os.path.dirname(os.path.dirname(control))
        classes = {
            _read(c) for c in glob.glob(dev + ":*/bInterfaceClass") if os.path.isfile(c)
        }
        if USB_HID_CLASS in classes:
            kept += 1
            continue
        _write(control, "auto" if on else "on")
    return f"{kept} mouse/keyboard device(s) kept awake" if on and kept else None


def apply(settings: dict, root: str = "/", run: Runner = _run) -> list[dict]:
    settings = validate(dict(settings))
    at = lambda rel: os.path.join(root, rel)  # noqa: E731
    results: list[dict] = []

    def attempt(name: str, action: Callable[[], object]) -> None:
        try:
            note = action()
            row = {"setting": name, "ok": True}
            if isinstance(note, str):
                row["note"] = note
            results.append(row)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            detail = getattr(exc, "stderr", None) or str(exc)
            results.append({"setting": name, "ok": False, "error": str(detail).strip()})

    def throttled(overrides: dict[str, object]) -> None:
        path = at("etc/throttled.conf")
        with open(path, encoding="utf-8") as handle:
            new = rewrite_throttled(handle.read(), overrides)
        tmp = path + ".forge-power.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(new)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        run(["systemctl", "restart", "throttled.service"])

    def wifi(on: bool) -> str | None:
        ifaces = [
            os.path.basename(os.path.dirname(p))
            for p in glob.glob(at("sys/class/net/*/wireless"))
        ]
        for iface in ifaces:
            run(["iw", "dev", iface, "set", "power_save", "on" if on else "off"])
        return None if ifaces else "no wireless interface"

    s = settings
    # Turbo first (it changes each core's ceiling), and the governor before the
    # energy preference, which intel_pstate refuses to change under "performance".
    if "turbo" in s:
        no_turbo = "0" if s["turbo"] == "on" else "1"
        attempt(
            "turbo",
            lambda: _write(
                at("sys/devices/system/cpu/intel_pstate/no_turbo"), no_turbo
            ),
        )
    if "governor" in s:
        attempt(
            "governor",
            lambda: _write_all(
                at("sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"),
                s["governor"],
            ),
        )
    if "max_freq_mhz" in s:
        cap = s["max_freq_mhz"]
        khz = str(NO_CAP_KHZ if cap == "max" else cap * 1000)
        pattern = at("sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq")
        attempt("max_freq_mhz", lambda: _write_all(pattern, khz))
    if "pl1_watts" in s or "pl2_watts" in s or "pl1_duration_s" in s:
        overrides: dict[str, object] = {}
        if "pl1_watts" in s:
            overrides["PL1_Tdp_W"] = s["pl1_watts"]
        if "pl2_watts" in s:
            overrides["PL2_Tdp_W"] = s["pl2_watts"]
        if "pl1_duration_s" in s:
            overrides["PL1_Duration_s"] = s["pl1_duration_s"]
        attempt("power_limits", lambda: throttled(overrides))
    if "epp" in s:
        pattern = at(
            "sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference"
        )
        attempt("epp", lambda: _write_all(pattern, s["epp"]))
    if "platform_profile" in s:
        attempt(
            "platform_profile",
            lambda: _write(
                at("sys/firmware/acpi/platform_profile"), s["platform_profile"]
            ),
        )
    if "aspm" in s:
        attempt(
            "aspm",
            lambda: _write(at("sys/module/pcie_aspm/parameters/policy"), s["aspm"]),
        )
    if "nmi_watchdog" in s:
        value = "1" if s["nmi_watchdog"] else "0"
        attempt(
            "nmi_watchdog", lambda: _write(at("proc/sys/kernel/nmi_watchdog"), value)
        )
    if "dirty_writeback_cs" in s:
        attempt(
            "dirty_writeback_cs",
            lambda: _write(
                at("proc/sys/vm/dirty_writeback_centisecs"),
                str(s["dirty_writeback_cs"]),
            ),
        )
    if "audio_power_save" in s:
        attempt(
            "audio_power_save",
            lambda: _write(
                at("sys/module/snd_hda_intel/parameters/power_save"),
                str(s["audio_power_save"]),
            ),
        )
    if "wifi_power_save" in s:
        attempt("wifi_power_save", lambda: wifi(s["wifi_power_save"]))
    if "gpu_max_freq_mhz" in s:
        attempt("gpu_max_freq_mhz", lambda: _gpu_cap(root, s["gpu_max_freq_mhz"]))
    if "kbd_backlight" in s:
        attempt("kbd_backlight", lambda: _kbd_backlight(root, s["kbd_backlight"]))
    if "usb_autosuspend" in s:
        attempt("usb_autosuspend", lambda: _usb_autosuspend(root, s["usb_autosuspend"]))
    if "pci_runtime_pm" in s:
        attempt(
            "pci_runtime_pm",
            lambda: _write_all(
                at("sys/bus/pci/devices/*/power/control"), s["pci_runtime_pm"]
            ),
        )
    return results


def measure(seconds: int, root: str = "/") -> dict:
    base = os.path.join(root, RAPL)

    def energy() -> int:
        with open(os.path.join(base, "energy_uj"), encoding="ascii") as handle:
            return int(handle.read())

    with open(os.path.join(base, "max_energy_range_uj"), encoding="ascii") as handle:
        wrap = int(handle.read())
    start, t0 = energy(), time.monotonic()
    time.sleep(seconds)
    end, t1 = energy(), time.monotonic()
    used = end - start if end >= start else end + wrap - start
    return {"package_watts": round(used / 1e6 / (t1 - t0), 2), "seconds": seconds}


def _save_state(mode: str, settings: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), mode=0o755, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(
            {"mode": mode, "settings": settings, "applied_at": time.time()}, handle
        )
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATE_FILE)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="forge-power")
    sub = parser.add_subparsers(dest="command", required=True)
    p_apply = sub.add_parser("apply", help="apply settings read as JSON from stdin")
    p_apply.add_argument("--mode", required=True)
    sub.add_parser("restore", help="re-apply the last saved mode")
    p_measure = sub.add_parser("measure", help="average CPU package watts")
    p_measure.add_argument("--seconds", type=int, default=2)
    args = parser.parse_args(argv)

    try:
        if args.command == "apply":
            if not MODE_NAME.match(args.mode):
                raise ValueError("mode name must be 1-32 of a-z, 0-9, _ or -")
            settings = validate(json.loads(sys.stdin.read(16384)))
            results = apply(settings)
            _save_state(args.mode, settings)
            print(json.dumps({"mode": args.mode, "results": results}))
        elif args.command == "restore":
            if not os.path.exists(STATE_FILE):
                print(json.dumps({"mode": None, "results": []}))
                return 0
            with open(STATE_FILE, encoding="utf-8") as handle:
                state = json.load(handle)
            if not MODE_NAME.match(str(state.get("mode"))):
                raise ValueError("saved mode name is invalid")
            results = apply(validate(state.get("settings")))
            print(json.dumps({"mode": state["mode"], "results": results}))
        else:
            if not 1 <= args.seconds <= 30:
                raise ValueError("seconds must be from 1 to 30")
            print(json.dumps(measure(args.seconds)))
    except ValueError as exc:
        print(f"forge-power: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
