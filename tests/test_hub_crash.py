"""The hub's page crashing (task 63, 2026-10-07).

WHY THIS EXISTS
    Emerson saw a blank Forge after changing looks in Alt+Shift+M. The hub's
    WebKit web process had died (coredumps: a SIGSEGV inside the mesa GPU
    driver, then a SIGABRT) and nothing loaded the page again. forge.py now
    loads it again (hub_crash_reloader), with the heavy looks held off after a
    second crash within two minutes (?safe=1, read by hub/index.html), and
    stops after a fourth so a crash loop cannot spin.

HOW TO RUN
    python3 -m pytest tests/test_hub_crash.py
    /usr/bin/python3 tests/browser/check_hub_crash_webkit.py   (real WebKit:
        kills the hub's page process four times and checks each reload)
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge  # noqa: E402


def test_shell_url_carries_the_safe_flag():
    assert forge.shell_url(safe=True) == forge.SHELL_URL + "?safe=1"
    assert (
        forge.shell_url("cosmos", True, True)
        == forge.SHELL_URL + "?background=1&safe=1#app=cosmos"
    )
    assert forge.shell_url(background=True) == forge.SHELL_URL + "?background=1"


def test_a_second_crash_soon_after_turns_safe_mode_on_for_good():
    state: dict = {}
    assert forge.after_hub_crash(state, 0) == "reload"
    assert forge.after_hub_crash(state, 200) == "reload", "a lone crash, long after"
    assert forge.after_hub_crash(state, 250) == "safe", "again within two minutes"
    assert forge.after_hub_crash(state, 1000) == "safe", "safe stays on for the run"


def test_a_crash_loop_stops_reloading():
    state: dict = {}
    got = [forge.after_hub_crash(state, t) for t in (0, 10, 20, 30, 40)]
    assert got == ["reload", "safe", "safe", "stop", "stop"]
    assert forge.after_hub_crash(state, 500) == "safe", "after a quiet spell, retry"


class FakeView:
    def __init__(self):
        self.calls = []

    def load_uri(self, uri):
        self.calls.append(("uri", uri))

    def load_html(self, html, base):
        self.calls.append(("html", html))


class FakeWin:
    def __init__(self, visible):
        self.visible = visible

    def get_visible(self):
        return self.visible


class FakeHost:
    def __init__(self):
        self.owner = "dossier"

    def set_owner(self, owner):
        self.owner = owner


class Reason:
    value_nick = "crashed"


def test_the_reloader_loads_the_hub_again_and_hides_app_views():
    view, host = FakeView(), FakeHost()
    on_crashed = forge.hub_crash_reloader(FakeWin(True), {}, {"host": host})
    for _ in range(4):
        on_crashed(view, Reason())
    assert view.calls[0] == ("uri", forge.SHELL_URL)
    assert view.calls[1] == ("uri", forge.SHELL_URL + "?safe=1")
    assert view.calls[2] == ("uri", forge.SHELL_URL + "?safe=1")
    assert view.calls[3][0] == "html" and "keeps crashing" in view.calls[3][1]
    assert host.owner is None, "an app's web views must not float over home"


def test_a_hidden_window_keeps_its_music_held_and_quitting_does_nothing():
    view = FakeView()
    forge.hub_crash_reloader(FakeWin(False), {}, {"host": None})(view, Reason())
    assert view.calls == [("uri", forge.SHELL_URL + "?background=1")]
    quiet = FakeView()
    forge.hub_crash_reloader(FakeWin(True), {"quitting": True}, {"host": None})(
        quiet, Reason()
    )
    assert quiet.calls == []
