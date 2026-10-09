"""shared/forge_sysinfo.py (S25): what the widgets show about the laptop,
shared by forge.py and the desktop's widgets (desktop/particles.py)."""

import subprocess
import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

import forge_sysinfo  # noqa: E402

MOUNTS = """\
/dev/nvme0n1p2 / btrfs rw,relatime 0 0
proc /proc proc rw 0 0
tmpfs /tmp tmpfs rw 0 0
/dev/nvme0n1p2 /home btrfs rw,relatime,subvol=/@home 0 0
/dev/nvme0n1p1 /boot vfat rw 0 0
/dev/sda1 /run/media/ejb/AN3 exfat rw 0 0
/dev/sdb1 /run/media/ejb/My\\040Drive ntfs3 rw 0 0
/dev/loop0 /var/lib/snapd/snap/core squashfs ro 0 0
"""


def test_mounts_keeps_real_drives_once_each():
    found = forge_sysinfo.mounts(MOUNTS)
    assert [w for _d, w, _f in found] == [
        "/",
        "/run/media/ejb/AN3",
        "/run/media/ejb/My Drive",
    ]


def test_disks_names_and_fills(tmp_path):
    f = tmp_path / "mounts"
    f.write_text(MOUNTS)
    Usage = namedtuple("Usage", "total used free")
    sizes = {
        "/": Usage(250e9, 150e9, 100e9),
        "/run/media/ejb/AN3": Usage(256e9, 240e9, 16e9),
        "/run/media/ejb/My Drive": Usage(0, 0, 0),
    }
    disks = forge_sysinfo.disks(str(f), usage=lambda w: sizes[w])
    assert disks == [
        {
            "mount": "/",
            "name": "System",
            "used": 60,
            "free_gb": 100.0,
            "total_gb": 250.0,
        },
        {
            "mount": "/run/media/ejb/AN3",
            "name": "AN3",
            "used": 94,
            "free_gb": 16.0,
            "total_gb": 256.0,
        },
    ]
    assert forge_sysinfo.disks(str(tmp_path / "missing")) == []


def test_net_meter_turns_two_readings_into_speeds(tmp_path, monkeypatch):
    dev = tmp_path / "dev"
    head = "Inter-| Receive\n face |bytes packets errs drop fifo frame compressed multicast|bytes\n"
    row = "{n}: {rx} 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0\n"
    dev.write_text(
        head
        + row.format(n="lo", rx=999999, tx=999999)
        + row.format(n="wlan0", rx=1000, tx=500)
        + row.format(n="docker0", rx=5, tx=5)
    )
    clock = iter([10.0, 12.0, 100.0])
    meter = forge_sysinfo.NetMeter(str(dev), clock=lambda: next(clock))
    monkeypatch.setattr(meter, "ssid", lambda: "home")
    first = meter.read()
    assert first == {"down": None, "up": None, "ifaces": ["wlan0"], "wifi": "home"}
    dev.write_text(
        head + row.format(n="lo", rx=5, tx=5) + row.format(n="wlan0", rx=5000, tx=1500)
    )
    second = meter.read()
    assert second["down"] == 2000 and second["up"] == 500
    assert forge_sysinfo.NetMeter(str(tmp_path / "none")).read()["down"] is None


def test_jan_status_reads_proc_only(tmp_path):
    (tmp_path / "12").mkdir()
    (tmp_path / "12" / "comm").write_text("Jan\n")
    (tmp_path / "13").mkdir()
    (tmp_path / "13" / "comm").write_text("bash\n")
    status = forge_sysinfo.jan_status(str(tmp_path))
    assert status["running"] is True and status["loaded"] == []
    (tmp_path / "12" / "comm").write_text("firefox\n")
    assert forge_sysinfo.jan_status(str(tmp_path))["running"] is False


def test_snapshot_merges_the_slow_parts():
    stats, sample = forge_sysinfo.snapshot(None, None, {"disks": [], "jan": {}})
    assert {"cpu", "mem", "battery", "disks", "jan"} <= set(stats)
    stats2, _ = forge_sysinfo.snapshot(sample)
    assert stats2["cpu"] is None or 0 <= stats2["cpu"] <= 100


def test_forge_py_uses_the_shared_reader():
    text = (ROOT / "forge.py").read_text()
    assert "forge_sysinfo.system_stats(previous, POWER_SUPPLY)" in text
    assert '"disks": forge_sysinfo.disks()' in text


def test_wifi_name_from_nmcli_active_connections():
    out = "meloncherry:802-11-wireless\nlo:loopback\n"
    assert forge_sysinfo.wifi_from_nmcli(out) == "meloncherry"
    # a colon in the name comes escaped
    assert forge_sysinfo.wifi_from_nmcli("Cafe\\: 2:802-11-wireless\n") == "Cafe: 2"
    # wired only: no Wi-Fi name
    assert forge_sysinfo.wifi_from_nmcli("Wired connection 1:802-3-ethernet\n") == ""


def test_wifi_name_never_scans(monkeypatch):
    """nmcli's Wi-Fi list starts a scan (6 s measured), which froze Forge."""
    calls = []

    def fake_run(argv, **_kw):
        calls.append(argv)
        out = "" if argv[0] == "iwgetid" else "home:802-11-wireless\n"
        return subprocess.CompletedProcess(argv, 0, out, "")

    monkeypatch.setattr(forge_sysinfo.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(forge_sysinfo.subprocess, "run", fake_run)
    assert forge_sysinfo.NetMeter().ssid() == "home"
    assert not any("wifi" in argv for argv in calls), calls
