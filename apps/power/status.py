"""Live, password-free readings of what the CPU and battery are doing right now."""

from __future__ import annotations

import glob
import os
import subprocess


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="ascii", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _int(path: str) -> int | None:
    value = _read(path)
    return int(value) if value and value.lstrip("-").isdigit() else None


def _watts(microwatts: int | None) -> float | None:
    return None if microwatts is None else round(microwatts / 1e6, 1)


def _package_temp() -> float | None:
    for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
        if _read(os.path.join(zone, "type")) == "x86_pkg_temp":
            milli = _int(os.path.join(zone, "temp"))
            return None if milli is None else round(milli / 1000, 1)
    return None


def _fan_rpm() -> int | None:
    for path in sorted(glob.glob("/sys/class/hwmon/hwmon*/fan*_input")):
        rpm = _int(path)
        if rpm is not None:
            return rpm
    return None


def _battery() -> dict | None:
    bats = sorted(glob.glob("/sys/class/power_supply/BAT*"))
    if not bats:
        return None
    bat = bats[0]
    power = _int(os.path.join(bat, "power_now"))
    if power is None:
        current = _int(os.path.join(bat, "current_now"))
        voltage = _int(os.path.join(bat, "voltage_now"))
        if current is not None and voltage is not None:
            power = abs(current) * voltage // 1_000_000
    return {
        "percent": _int(os.path.join(bat, "capacity")),
        "state": _read(os.path.join(bat, "status")),
        "draw_watts": _watts(power),
    }


def _cpu_mhz(filename: str, combine) -> int | None:
    pattern = f"/sys/devices/system/cpu/cpu[0-9]*/cpufreq/{filename}"
    values = [v for v in (_int(p) for p in glob.glob(pattern)) if v is not None]
    return round(combine(values) / 1000) if values else None


def snapshot() -> dict:
    cpu0 = "/sys/devices/system/cpu/cpu0/cpufreq"
    rapl = "/sys/class/powercap/intel-rapl:0"
    aspm = _read("/sys/module/pcie_aspm/parameters/policy") or ""
    aspm_active = next((w[1:-1] for w in aspm.split() if w.startswith("[")), None)
    no_turbo = _read("/sys/devices/system/cpu/intel_pstate/no_turbo")
    return {
        "governor": _read(f"{cpu0}/scaling_governor"),
        "epp": _read(f"{cpu0}/energy_performance_preference"),
        "turbo": None if no_turbo is None else no_turbo == "0",
        "platform_profile": _read("/sys/firmware/acpi/platform_profile"),
        "sustained_watts": _watts(_int(f"{rapl}/constraint_0_power_limit_uw")),
        "burst_watts": _watts(_int(f"{rapl}/constraint_1_power_limit_uw")),
        "aspm": aspm_active,
        "avg_mhz": _cpu_mhz("scaling_cur_freq", lambda v: sum(v) / len(v)),
        "freq_cap_mhz": _cpu_mhz("scaling_max_freq", max),
        "nmi_watchdog": _read("/proc/sys/kernel/nmi_watchdog") == "1",
        "temp_c": _package_temp(),
        "fan_rpm": _fan_rpm(),
        "battery": _battery(),
        "on_ac": _read("/sys/class/power_supply/AC/online") == "1",
    }


def top_processes(limit: int = 8) -> list[dict]:
    proc = subprocess.Popen(
        ["ps", "-eo", "pid=,comm=,%cpu=,rss=", "--sort=-%cpu"],
        stdout=subprocess.PIPE,
        text=True,
    )
    out, _ = proc.communicate(timeout=10)
    rows = []
    for line in out.splitlines():
        if len(rows) == limit:
            break
        parts = line.split()
        # ps itself always looks busy in its own snapshot; leave it out.
        if len(parts) < 4 or int(parts[0]) == proc.pid:
            continue
        pid, cpu, rss = parts[0], parts[-2], parts[-1]
        rows.append(
            {
                "pid": int(pid),
                "name": " ".join(parts[1:-2]),
                "cpu_percent": float(cpu),
                "memory_mb": round(int(rss) / 1024),
            }
        )
    return rows
