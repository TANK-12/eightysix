"""tools/quiet_window.py: other sessions pause for a power test, within Emerson's 10-minute budget."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import quiet_window as qw  # noqa: E402


def state(pid: int) -> str:
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]


def wait_for(check, limit: float = 5.0) -> bool:
    end = time.monotonic() + limit
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.05)
    return False


def test_targets_freeze_other_sessions_and_sibling_shells_not_me_or_emersons_apps():
    procs = {
        1: (0, "systemd", "/sbin/init"),
        10: (1, "python", "/usr/bin/python3 /home/ejb/Forge/forge.py --background"),
        11: (10, "python", "uvicorn web_app:app --host 127.0.0.1 --port 8445"),
        20: (11, "claude", "claude -p"),  # this session
        21: (20, "bash", "bash -c my command"),
        22: (21, "python3", "python3 tools/quiet_window.py run"),
        23: (20, "bash", "bash -c sibling helper test"),
        24: (23, "chrome", "chrome --headless"),
        25: (20, "python3", "browser_mcp.py"),  # MCP server of this session: left alone
        30: (11, "claude", "claude -p"),  # another session
        31: (30, "python3", "pytest -q"),
        32: (30, "python", "/home/ejb/Forge/forge.py --port 9999"),  # protected by name
        40: (1, "llama-server", "llama-server --port 1337"),
    }
    assert qw.targets(procs, 22) == [23, 24, 30, 31]


def test_window_is_capped_per_pause_and_by_what_is_left():
    data = {"grant": qw.GRANT_ID, "budget_s": 600.0, "windows": []}
    assert qw.window_for(1000, data) == qw.MAX_WINDOW_S
    data["windows"] = [{"seconds": 550.0}]
    assert qw.window_for(120, data) == 50.0
    data["windows"] = [{"seconds": 600.0}]
    assert qw.window_for(120, data) == 0.0


def test_run_freezes_during_the_command_thaws_after_and_charges_the_ledger(tmp_path):
    victim = subprocess.Popen(["sleep", "30"])
    ledger = tmp_path / "ledger.json"
    probe = tmp_path / "seen"
    try:
        command = [
            sys.executable,
            "-c",
            f"open({str(probe)!r}, 'w').write(open('/proc/{victim.pid}/stat').read())",
        ]
        code = qw.run(
            command, 20, "unit", ledger=ledger, pids=[victim.pid], notify=False
        )
        assert code == 0
        assert (
            probe.read_text().rsplit(")", 1)[1].split()[0] == "T"
        )  # frozen while the test ran
        assert wait_for(lambda: state(victim.pid) != "T")  # running again after
        data = qw.load(ledger)
        assert len(data["windows"]) == 1 and data["windows"][0]["label"] == "unit"
        assert data["windows"][0]["frozen"] == 1 and qw.used(data) < 20
    finally:
        victim.kill()


def test_run_refuses_once_the_budget_is_spent(tmp_path):
    ledger = tmp_path / "ledger.json"
    data = qw.load(ledger)
    data["windows"] = [{"label": "old", "seconds": 600.0, "frozen": 1, "at": "x"}]
    ledger.write_text(json.dumps(data))
    assert qw.run(["true"], 60, "late", ledger=ledger, pids=[], notify=False) == 2


def test_command_that_overruns_is_cut_off_and_sessions_still_resume(tmp_path):
    victim = subprocess.Popen(["sleep", "30"])
    try:
        start = time.monotonic()
        code = qw.run(
            ["sleep", "30"],
            5,
            "slow",
            ledger=tmp_path / "l.json",
            pids=[victim.pid],
            notify=False,
        )
        assert code == 124 and time.monotonic() - start < 10
        assert wait_for(lambda: state(victim.pid) != "T")
    finally:
        victim.kill()


def test_watchdog_thaws_even_if_the_runner_dies():
    victim = subprocess.Popen(["sleep", "30"])
    try:
        os.kill(victim.pid, signal.SIGSTOP)
        assert wait_for(lambda: state(victim.pid) == "T")
        qw.watchdog(time.time() + 0.5, [victim.pid])
        assert wait_for(lambda: state(victim.pid) != "T")
    finally:
        victim.kill()
