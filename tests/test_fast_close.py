"""Closing Forge stops every backend at once, and the top bar's stats read.

WHY THIS EXISTS
    stop_all() used to stop backends one after another, waiting on each. Every
    backend exits 0.15-0.2 s after SIGTERM (measured with all thirteen), so
    closing took about 2.2 s with the window still on screen. It now signals
    them all together and waits once.

HOW TO RUN
    /usr/bin/python3 tests/test_fast_close.py

    The system python, for the same reason as test_app_discovery.py: forge.py
    imports gi/Gtk at module level.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forge  # noqa: E402

POLITE = [sys.executable, "-c", "import time; time.sleep(30)"]
STUBBORN = [
    sys.executable,
    "-c",
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
]


class _Stub:
    """Just enough of a Backend for stop_all(): a process in its own session."""

    def __init__(self, command):
        self.proc = subprocess.Popen(command, start_new_session=True)


def test_every_backend_is_stopped_together():
    stubs = [_Stub(POLITE) for _ in range(6)]
    time.sleep(0.3)
    manager = forge.BackendManager(stubs)
    started = time.time()
    manager.stop_all(timeout=3.0)
    took = time.time() - started
    assert all(s.proc.poll() is not None for s in stubs), "a backend survived"
    # One at a time would be six separate waits; together it is one.
    assert took < 1.0, f"stopping six took {took:.2f}s"


def test_a_backend_that_ignores_sigterm_is_killed_at_the_deadline():
    polite, stubborn = _Stub(POLITE), _Stub(STUBBORN)
    time.sleep(0.3)
    started = time.time()
    forge.BackendManager([polite, stubborn]).stop_all(timeout=0.5)
    took = time.time() - started
    assert polite.proc.poll() is not None and stubborn.proc.poll() is not None
    assert 0.4 < took < 1.5, f"took {took:.2f}s"


def test_backends_that_never_started_are_skipped():
    class NeverStarted:
        proc = None

    forge.BackendManager([NeverStarted()]).stop_all(timeout=0.1)


def test_the_top_bar_stats_come_from_proc():
    stats, sample = forge.system_stats()
    assert stats["cpu"] is None, "one sample cannot give a CPU percentage"
    mem = stats["mem"]
    assert mem is not None and 0 <= mem <= 100
    time.sleep(0.2)
    stats, _ = forge.system_stats(sample)
    cpu = stats["cpu"]
    assert cpu is not None and 0 <= cpu <= 100


def test_plugged_in_comes_from_the_mains_adapter_not_the_battery():
    import tempfile

    def supply(root, name, **files):
        os.makedirs(os.path.join(root, name))
        for key, value in files.items():
            with open(os.path.join(root, name, key), "w") as f:
                f.write(value + "\n")

    saved = forge.POWER_SUPPLY
    try:
        with tempfile.TemporaryDirectory() as root:
            forge.POWER_SUPPLY = root
            supply(root, "BAT0", type="Battery", capacity="80", status="Not charging")
            supply(root, "AC", type="Mains", online="1")
            stats, _ = forge.system_stats()
            assert stats["battery"] == 80 and stats["charging"] is False
            assert stats["plugged"] is True, "held at a charge limit, on the wall"
            with open(os.path.join(root, "AC", "online"), "w") as f:
                f.write("0\n")
            assert forge.system_stats()[0]["plugged"] is False
        with tempfile.TemporaryDirectory() as root:
            forge.POWER_SUPPLY = root
            stats, _ = forge.system_stats()
            assert stats["battery"] is None and stats["plugged"] is None
    finally:
        forge.POWER_SUPPLY = saved


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"PASS :: {name}")
            except Exception as e:  # noqa: BLE001 - report every failure
                failures += 1
                print(f"FAIL :: {name} :: {type(e).__name__}: {e}")
    print("ALL PASS" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
