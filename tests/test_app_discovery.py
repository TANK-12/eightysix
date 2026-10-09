"""Forge picks up an app added to apps/ after the window is already open.

WHY THIS EXISTS
    Discovery used to run exactly once, at launch. Foresight was written while
    a Forge window was already running, so it was simply absent from the
    sidebar for the rest of that session -- which read, from the outside, as
    the app having disappeared. forge.py now rescans apps/ on the liveness
    poll that was already running every 15 seconds.

HOW TO RUN
    /usr/bin/python3 tests/test_app_discovery.py

    The system python on purpose: forge.py imports gi/Gtk at module level and
    there is no virtualenv for the hub itself. pytest can collect this file
    too, if it is ever run under an interpreter that has both pytest and
    PyGObject.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forge  # noqa: E402


def _make_app(apps_dir, name, port, order, **extra):
    """The smallest thing forge.discover_backends() will accept: a manifest,
    a venv with a python in it, and a source directory. `extra` adds optional
    manifest fields."""
    root = os.path.join(apps_dir, name)
    os.makedirs(os.path.join(root, ".venv", "bin"), exist_ok=True)
    open(os.path.join(root, ".venv", "bin", "python"), "w").close()
    with open(os.path.join(root, "forge_app.json"), "w") as f:
        json.dump(
            {
                "name": name,
                "label": name.title(),
                "tagline": f"{name} tagline",
                "port": port,
                "module": "web_app:app",
                "order": order,
                **extra,
            },
            f,
        )


def test_an_app_added_after_launch_is_adopted():
    with tempfile.TemporaryDirectory() as apps_dir:
        forge.APPS_DIR = apps_dir
        _make_app(apps_dir, "alpha", 9001, 1)
        _make_app(apps_dir, "gamma", 9003, 3)

        manager = forge.BackendManager(forge.discover_backends())
        assert [b.name for b in manager.backends] == ["alpha", "gamma"]

        # A poll with nothing new must not churn.
        assert manager.adopt_new(lambda: None) == []

        # An app is written while the window is open, as Foresight was.
        _make_app(apps_dir, "beta", 9002, 2, fullscreen="auto")

        started = []

        def record(on_change, only=None):
            started.extend(b.name for b in only or [])

        manager.start_all_async = record
        fresh = manager.adopt_new(lambda: None)

        assert [b.name for b in fresh] == ["beta"]
        # In its manifest "order", not appended on the end.
        assert [b.name for b in manager.backends] == ["alpha", "beta", "gamma"]
        # The ten already running are left alone.
        assert started == ["beta"]

        snap = manager.snapshot()
        assert snap["beta"]["label"] == "Beta"
        assert snap["beta"]["tagline"] == "beta tagline"
        assert snap["beta"]["url"] == "http://127.0.0.1:9002"
        # The hub's smart full screen reads this; an app that says nothing
        # keeps its bar.
        assert snap["beta"]["fullscreen"] == "auto"
        assert snap["alpha"]["fullscreen"] == ""

        started.clear()
        assert manager.adopt_new(lambda: None) == []
        assert started == []


def test_on_demand_nothing_starts_until_the_hub_asks():
    with tempfile.TemporaryDirectory() as apps_dir:
        forge.APPS_DIR = apps_dir
        _make_app(apps_dir, "alpha", 9001, 1)
        _make_app(apps_dir, "gamma", 9003, 3)

        manager = forge.BackendManager(forge.discover_backends(), lazy=True)
        started = []
        manager.start_all_async = lambda on_change, only=None: started.extend(
            b.name for b in only or manager.backends
        )
        snap = manager.snapshot()
        assert snap["alpha"]["state"] == "idle" and not snap["alpha"]["available"]

        # An app added while open waits to be opened too.
        _make_app(apps_dir, "beta", 9002, 2)
        assert [b.name for b in manager.adopt_new(lambda: None)] == ["beta"]
        assert started == [] and manager.snapshot()["beta"]["state"] == "idle"

        # Opening one starts that one, once.
        assert manager.start_one("beta", lambda: None) is True
        assert started == ["beta"]
        assert manager.snapshot()["beta"]["state"] == "starting"
        assert manager.start_one("beta", lambda: None) is False
        assert manager.start_one("nope", lambda: None) is False
        assert started == ["beta"]


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS :: {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL :: {name} :: {e}")
    print()
    print("ALL PASS" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
