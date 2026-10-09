"""Runs the feeders in the background, fires reminders, and keeps settings.

Each feeder runs every INTERVAL seconds, if it is switched on and logging is
not paused. Its state (read positions, what was running) is saved to
<data>/feeders.json after every read, so a restart resumes where it left off
and logs nothing twice. Due reminders pop up with notify-send and are
marked done.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import sources as sources_mod
from store import Store

DEFAULTS = {"paused": False, "keep_days": 365, "enabled": {}}


class Collector:
    def __init__(self, store: Store, data_dir: Path, feeders: dict | None = None):
        self.store = store
        self.data_dir = Path(data_dir)
        self.feeders = sources_mod.load() if feeders is None else feeders
        self.state_path = self.data_dir / "feeders.json"
        self.settings_path = self.data_dir / "settings.json"
        self.states: dict = self._read(self.state_path, {})
        self.next_run: dict[str, float] = {}
        self.last: dict[str, dict] = {}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _read(path: Path, default: dict) -> dict:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return json.loads(json.dumps(default))

    # settings -----------------------------------------------------------------
    def settings(self) -> dict:
        s = {**DEFAULTS, **self._read(self.settings_path, DEFAULTS)}
        s["enabled"] = {
            name: bool(s.get("enabled", {}).get(name, getattr(f, "DEFAULT_ON", True)))
            for name, f in self.feeders.items()
        }
        return s

    def save_settings(self, changes: dict) -> dict:
        s = self.settings()
        if "paused" in changes:
            s["paused"] = bool(changes["paused"])
        if "keep_days" in changes:
            try:
                keep = int(changes["keep_days"])
            except (TypeError, ValueError, OverflowError):
                raise ValueError("keep_days must be a whole number")
            if keep < 0:
                # 0 already means keep forever: a negative number is a typo
                raise ValueError("keep_days must be 0 (forever) or more")
            s["keep_days"] = max(0, min(3650, keep))
        enabled = changes.get("enabled") or {}
        if not isinstance(enabled, dict):
            raise ValueError("enabled must map feeder names to true or false")
        for name, on in enabled.items():
            if name in self.feeders:
                s["enabled"][name] = bool(on)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(s, indent=1))
        return s

    def describe(self) -> list[dict]:
        s = self.settings()
        return [
            {
                "name": name,
                "label": getattr(f, "LABEL", name),
                "description": getattr(f, "DESCRIPTION", ""),
                "interval": getattr(f, "INTERVAL", 60),
                "enabled": s["enabled"][name],
                "last": self.last.get(name),
            }
            for name, f in self.feeders.items()
        ]

    # running --------------------------------------------------------------------
    def run_feeder(self, name: str) -> int:
        feeder = self.feeders[name]
        with self._lock:
            state = self.states.setdefault(name, {})
            started = time.time()
            try:
                events = feeder.collect(state)
                added = self.store.add_many(events)
                self.last[name] = {"at": started, "added": added, "error": ""}
            except Exception as e:  # a broken feeder must not stop the others
                added = 0
                self.last[name] = {
                    "at": started,
                    "added": 0,
                    "error": f"{type(e).__name__}: {e}",
                }
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self.states))
        return added

    def tick(self, now: float | None = None) -> None:
        now = now or time.time()
        s = self.settings()
        if not s["paused"]:
            for name, feeder in self.feeders.items():
                if s["enabled"][name] and now >= self.next_run.get(name, 0):
                    self.next_run[name] = now + getattr(feeder, "INTERVAL", 60)
                    self.run_feeder(name)
        self.fire_reminders(now)
        if now >= self.next_run.get("_prune", 0):
            self.next_run["_prune"] = now + 3600
            self.store.prune(s["keep_days"], now)

    def fire_reminders(self, now: float) -> list[dict]:
        due = self.store.due_reminders(now)
        for r in due:
            notify(r["title"], r.get("body") or "")
            self.store.update(r["id"], {"done": True})
        return due

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        self._stop.wait(2)  # let the app finish starting first
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(5)

    def stop(self) -> None:
        self._stop.set()


def notify(title: str, body: str) -> None:
    try:
        subprocess.Popen(
            [
                "notify-send",
                "--app-name=Forge Calendar",
                "-u",
                "normal",
                f"⏰ {title}",
                body,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass
