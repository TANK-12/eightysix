"""Work kept off Forge's window thread (2026-10-08).

Emerson: "things in forge keep spazzing only a little bit but everything in
general", and opening an app often froze Forge. Measured that day: the top
bar's 3 s stats read ran on the GTK main loop (temperatures alone 45 ms every
30 s, and a disk read can block on a sleeping USB drive), and the overview
picture taken 0.9 s after every app opened made the page's process repaint
the whole window in software (0.25-0.32 s, page frozen meanwhile) before
encoding a PNG on the main loop.

    /usr/bin/python3 tests/test_off_main_loop.py
"""

import os
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cairo  # noqa: E402

import forge  # noqa: E402


def now_post(fn, *args):
    fn(*args)


def test_a_slow_stats_read_never_holds_the_window():
    release = threading.Event()
    reads, got = [], []

    def read():
        reads.append(1)
        release.wait(5)
        return {"cpu": 1}

    pump = forge.StatsPump(read, got.append, post=now_post)
    started = time.monotonic()
    assert pump.tick() is True  # the GLib timer keeps running
    assert time.monotonic() - started < 0.05
    pump.tick()  # still reading: no second read piles up
    time.sleep(0.05)
    assert len(reads) == 1 and not got
    release.set()
    for _ in range(100):
        if got:
            break
        time.sleep(0.01)
    assert got == [{"cpu": 1}]
    for _ in range(100):  # the pump is free again for the next tick
        if not pump.busy:
            break
        time.sleep(0.01)
    pump.tick()
    for _ in range(100):
        if len(reads) == 2:
            break
        time.sleep(0.01)
    assert len(reads) == 2


def test_a_failed_stats_read_frees_the_pump_and_sends_nothing():
    got = []

    def read():
        raise OSError("drive gone")

    pump = forge.StatsPump(read, got.append, post=now_post)
    pump.tick()
    for _ in range(100):
        if not pump.busy:
            break
        time.sleep(0.01)
    assert not pump.busy and not got


class _View:
    """Just enough of a widget for frame_thumb: a size and a draw()."""

    def __init__(self, paint=True):
        self.paint = paint

    def get_allocated_width(self):
        return 1400

    def get_allocated_height(self):
        return 900

    def draw(self, ctx):
        if not self.paint:
            return
        ctx.set_source_rgb(0, 0, 1)
        ctx.paint()
        ctx.set_source_rgb(1, 0, 0)  # the app's area, in window pixels
        ctx.rectangle(100, 50, 1200, 800)
        ctx.fill()


def pixel(img, x, y):
    data = img.get_data()
    i = y * img.get_stride() + x * 4
    return data[i + 2], data[i + 1], data[i]


def test_the_picture_comes_from_the_frame_on_screen():
    img = forge.frame_thumb(_View(), [100, 50, 1200, 800], width=480)
    assert isinstance(img, cairo.ImageSurface)
    assert (img.get_width(), img.get_height()) == (480, 320)
    assert pixel(img, 5, 5) == (255, 0, 0)
    assert pixel(img, 474, 314) == (255, 0, 0)


def test_page_pixels_are_turned_into_window_pixels():
    # App size 1.25: the page's 80,40 960x640 is the window's 100,50 1200x800
    img = forge.frame_thumb(_View(), [80, 40, 960, 640], width=480, scale=1.25)
    assert img is not None
    assert (img.get_width(), img.get_height()) == (480, 320)
    assert pixel(img, 2, 2) == (255, 0, 0)


def test_a_blank_frame_gives_no_picture():
    assert forge.frame_thumb(_View(paint=False), [100, 50, 1200, 800]) is None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_closing_an_app_while_it_starts_leaves_it_closed():
    """A start still waiting for its port when the app was closed used to
    crash its thread on the emptied proc (or mark the app failed)."""
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".venv", "bin"))
        fake = os.path.join(root, ".venv", "bin", "python")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(fake, 0o755)
        manifest = {"name": "slow", "port": free_port(), "module": "x:app"}
        manifest["ready_timeout"] = 10
        b = forge.Backend(manifest, root)
        manager = forge.BackendManager([b])
        errors = []

        def run():
            try:
                b.start()
            except Exception as e:  # noqa: BLE001 - the bug under test
                errors.append(e)

        t = threading.Thread(target=run)
        t.start()
        for _ in range(100):
            if b.proc is not None:
                break
            time.sleep(0.01)
        assert manager.stop_one("slow") is True
        t.join(5)
        assert not t.is_alive()
        assert not errors, errors
        assert b.state == "idle"


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
