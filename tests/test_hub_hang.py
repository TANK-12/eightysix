"""The hub's page hanging (task 63, 2026-10-07).

WHY THIS EXISTS
    Emerson's Forge froze after he picked Frosted or Liquid glass in
    Alt+Shift+M. Not a crash: the page's process stayed alive with WebKit's
    compositor stuck painting live blur behind every tile (0 frames a
    second) and then its main thread stuck waiting on it, so
    web-process-terminated never fired and WebKit's own
    is-web-process-responsive stayed true. forge.py now asks the page every
    few seconds whether it still runs and paints (hub_hang_watchdog); a page
    that stays silent, or paints nothing while Forge is the window in front,
    is ended and loaded again with the heavy looks off.

HOW TO RUN
    python3 -m pytest tests/test_hub_hang.py
    tests/browser/headless_gnome.sh start
    tests/browser/headless_gnome.sh run /usr/bin/python3 \\
        tests/browser/check_hub_hang_webkit.py   (real WebKit, real GL window)
    tests/browser/headless_gnome.sh stop
"""

import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge  # noqa: E402
from gi.repository import GLib, WebKit2  # noqa: E402

LIMIT = forge.HUB_HANG_LIMIT


def test_a_quiet_page_is_asked_and_an_answer_out_is_waited_for():
    state: dict = {"sent": None, "frameless": None}
    assert forge.hub_hang_check(state, 0) == "ping"
    state["sent"] = 0
    for now in (4, 8, LIMIT - 0.1):
        assert forge.hub_hang_check(state, now) == "wait"
    assert forge.hub_hang_check(state, LIMIT) == "hung", "no answer for the limit"


def test_frames_missing_while_watched_count_from_the_first_question():
    state: dict = {"sent": 0, "frameless": None}
    forge.hub_hang_answer(state, 0, False, True)
    assert (state["sent"], state["frameless"]) == (None, 0)
    assert forge.hub_hang_check(state, 4) == "ping", "one miss is not a hang yet"
    forge.hub_hang_answer(state, 4, False, True)
    assert state["frameless"] == 0, "the stall started at the first miss"
    assert forge.hub_hang_check(state, LIMIT) == "hung"


def test_a_painted_frame_or_a_page_out_of_sight_clears_the_count():
    state: dict = {"sent": 4, "frameless": 0}
    forge.hub_hang_answer(state, 4, True, True)
    assert state["frameless"] is None
    state.update(sent=8, frameless=0)
    forge.hub_hang_answer(state, 8, False, False)
    assert state["frameless"] is None, "nothing paints out of sight, rightly"
    state.update(sent=8, frameless=0)
    forge.hub_hang_answer(state, 8, None, True)
    assert state["frameless"] is None, "an error answer is still an answer"


class Value:
    def __init__(self, value):
        self.value = value

    def to_boolean(self):
        return self.value


class FakeView:
    def __init__(self):
        self.handlers = {}
        self.asked = []
        self.variants = []
        self.win: Any = None  # the FakeWin it sits in, set by watchdog()
        self.mapped = True
        self.inside: list = []  # widgets WebKit put inside the view

    def forall(self, callback):
        for widget in self.inside:
            callback(widget)

    def connect(self, signal, handler):
        self.handlers[signal] = handler

    def queue_draw(self):
        self.win.draw()

    def get_mapped(self):
        return self.mapped

    def call_async_javascript_function(self, body, length, args, *rest):
        self.asked.append((body, args.unpack(), rest[-1]))
        self.variants.append(args)

    def call_async_javascript_function_finish(self, result):
        if isinstance(result, GLib.Error):
            raise result
        return Value(result)

    def load(self, event):
        self.handlers["load-changed"](self, event)

    def dialog(self):
        assert self.handlers["script-dialog"](self, object()) is False

    def answer(self, value, index=-1):
        self.asked[index][2](self, value)


class FakeWin:
    """A window and its GTK frame clock. `presenting` is whether the
    desktop sends it frames: false with the screen blanked."""

    def __init__(self, active=True):
        self.active = active
        self.presenting = True
        self.frames = 0
        self.has_clock = True

    def is_active(self):
        return self.active

    def draw(self):
        if self.presenting:
            self.frames += 1

    def get_frame_clock(self):
        return self if self.has_clock else None

    def get_frame_counter(self):
        return self.frames


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def watchdog(win=None, screen=None):
    view, clock, hung = FakeView(), Clock(), []
    view.win = win = win or FakeWin()
    tick = forge.hub_hang_watchdog(
        win,
        view,
        {} if screen is None else screen,
        lambda: hung.append(clock.now),
        clock,
    )
    return view, clock, hung, tick


def test_nothing_is_asked_until_the_page_has_loaded():
    view, clock, hung, tick = watchdog()
    assert tick() is True and view.asked == []
    view.load(WebKit2.LoadEvent.STARTED)
    assert tick() is True and view.asked == [], "no script runs before commit"
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    body, args, _ = view.asked[0]
    assert body == forge.HUB_HANG_ASK
    assert args == {"frames": 1.0, "wait": forge.HUB_HANG_PING * 1000.0}


def test_the_question_only_passes_types_webkit_accepts():
    """call_async_javascript_function takes numbers, strings and
    dictionaries only. A boolean made WebKit refuse every question at once
    ("Invalid parameter frames"), and as an error counts as an answer, the
    first watchdog could never see a hang (found in the headless GNOME)."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    variant = view.variants[0]
    for i in range(variant.n_children()):
        entry = variant.get_child_value(i)
        name = entry.get_child_value(0).get_string()
        kind = entry.get_child_value(1).get_variant().get_type_string()
        assert kind in ("d", "s", "a{sv}"), (name, kind)


def test_a_page_out_of_sight_is_only_asked_whether_it_runs():
    view, clock, hung, tick = watchdog(FakeWin(active=False))
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    assert view.asked[0][1]["frames"] == 0.0


def test_a_silent_page_is_ended_once_and_left_alone_while_it_reloads():
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()  # asks at 0, never answered
    for clock.now in (4.0, 8.0):
        tick()
    assert hung == [] and len(view.asked) == 1, "waits, does not pile up questions"
    clock.now = LIMIT
    tick()
    assert hung == [LIMIT]
    clock.now = 2 * LIMIT
    tick()
    assert hung == [LIMIT] and len(view.asked) == 1, "quiet until the next load"
    view.load(WebKit2.LoadEvent.STARTED)
    view.answer(True, 0)  # the old page's late answer changes nothing
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    assert len(view.asked) == 2


def test_a_page_that_runs_but_paints_nothing_in_front_is_ended():
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    for _ in range(4):
        tick()
        view.answer(False)
        clock.now += forge.HUB_HANG_PING
    assert hung == [3 * forge.HUB_HANG_PING], "after LIMIT seconds of no frames"


def test_a_healthy_page_is_never_ended_and_quitting_stops_the_ticks():
    screen: dict = {}
    view, clock, hung, tick = watchdog(screen=screen)
    view.load(WebKit2.LoadEvent.FINISHED)
    for _ in range(20):
        tick()
        view.answer(True)
        clock.now += forge.HUB_HANG_PING
    assert hung == []
    screen["quitting"] = True
    assert tick() is False


def test_no_frame_while_the_window_lost_focus_meanwhile_does_not_count():
    win = FakeWin()
    view, clock, hung, tick = watchdog(win)
    view.load(WebKit2.LoadEvent.FINISHED)
    for _ in range(5):
        tick()
        win.active = False  # Emerson switched away while the question was out
        view.answer(False)
        win.active = True
        clock.now += forge.HUB_HANG_PING
    assert hung == []


def test_no_frame_while_the_desktop_draws_nothing_does_not_count():
    """A blanked screen sends the window no frames, so the page paints
    none either; that is not a stuck page."""
    win = FakeWin()
    win.presenting = False
    view, clock, hung, tick = watchdog(win)
    view.load(WebKit2.LoadEvent.FINISHED)
    for _ in range(6):
        tick()
        view.answer(False)
        clock.now += forge.HUB_HANG_PING
    assert hung == []
    win.presenting = True  # the screen wakes and the page still paints nothing
    for _ in range(4):
        tick()
        view.answer(False)
        clock.now += forge.HUB_HANG_PING
    assert len(hung) == 1


def test_a_window_without_a_frame_clock_yet_counts_no_missing_frames():
    win = FakeWin()
    win.has_clock = False
    view, clock, hung, tick = watchdog(win)
    view.load(WebKit2.LoadEvent.FINISHED)
    for _ in range(6):
        tick()
        view.answer(False)
        clock.now += forge.HUB_HANG_PING
    assert hung == []


def test_a_silent_page_is_ended_even_with_the_screen_blanked():
    """No answer at all means the page's main thread is stuck, whatever
    the screen does."""
    win = FakeWin()
    win.presenting = False
    view, clock, hung, tick = watchdog(win)
    view.load(WebKit2.LoadEvent.FINISHED)
    for clock.now in (0.0, 4.0, 8.0, LIMIT):
        tick()
    assert hung == [LIMIT]


def test_a_hang_reloads_straight_into_safe_mode():
    """The watchdog sets "safe" in the crash state it shares with the
    reloader, so the first reload after a hang already has the looks off."""

    class View:
        def __init__(self):
            self.uris = []

        def load_uri(self, uri):
            self.uris.append(uri)

    class Win:
        def get_visible(self):
            return True

    class Reason:
        value_nick = "terminated-by-api"

    class Hung(View):
        def terminate_web_process(self):
            reloader(self, Reason())  # WebKit fires web-process-terminated

    crashes: dict = {}
    view = Hung()
    reloader = forge.hub_crash_reloader(Win(), {}, {"host": None}, crashes)
    forge.hub_hang_ender(view, crashes)()
    assert crashes["safe"] is True
    assert view.uris == [forge.SHELL_URL + "?safe=1"]


def test_a_stall_in_forge_itself_gives_the_page_one_more_ping():
    """Forge's main loop blocked for 11 s right after a question: the
    page's answer sat unread in the queue, and the late tick must not
    end a page that answered in time (the critic's run, 2026-10-07)."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()  # asks at 0; the page answers at once, but Forge is stuck
    clock.now = 11.0
    tick()
    assert hung == [], "a late tick is no proof"
    view.answer(True)
    for _ in range(5):
        clock.now += forge.HUB_HANG_PING
        tick()
        view.answer(True)
    assert hung == []


def test_a_hang_that_also_stalls_forge_is_still_caught_a_ping_later():
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    for clock.now in (11.0, 22.0):  # every tick late, the page silent
        tick()
    assert hung == [22.0], "one grace per question, not one per tick"


def test_the_grace_also_covers_the_missing_frame_count():
    state = {"sent": None, "frameless": 0.0, "ticked": 0.0}
    assert forge.hub_hang_check(state, 12.0) == "ping"
    assert state["frameless"] == 12.0 - LIMIT + forge.HUB_HANG_PING


def test_a_dialog_waiting_for_emerson_is_no_hang():
    """confirm() blocks the page's main thread until it is answered, so
    the question goes unanswered; that is not a stuck page (the critic
    saw "Delete every share zip?" ended after 15 s)."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    view.dialog()
    for _ in range(30):
        clock.now += forge.HUB_HANG_PING
        tick()
    assert hung == [] and len(view.asked) == 1, "waits, asks nothing more"
    view.answer(False)  # answered at last, late and with no frame meanwhile
    for _ in range(2):
        clock.now += forge.HUB_HANG_PING
        tick()
        view.answer(True)
    assert hung == []
    clock.now += forge.HUB_HANG_PING
    tick()  # dialog over: a silent page counts again
    for _ in range(3):
        clock.now += forge.HUB_HANG_PING
        tick()
    assert len(hung) == 1


def test_a_dialog_shown_with_no_question_out_still_asks():
    state = {"sent": None, "frameless": None, "dialog": True}
    assert forge.hub_hang_check(state, 0.0) == "ping"
    state["sent"] = 0.0
    assert forge.hub_hang_check(state, 100.0) == "wait"


def test_a_page_stuck_while_it_loads_is_caught_with_a_longer_limit():
    """A page stuck before its load finished was never asked at all (the
    critic's `<script>for(;;){}</script>`), and a start or the safe reload
    is where a stuck look shows first."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.STARTED)
    view.load(WebKit2.LoadEvent.COMMITTED)
    while not hung and clock.now < 60:
        tick()
        clock.now += forge.HUB_HANG_PING
    assert len(view.asked) == 1
    assert hung and forge.HUB_HANG_LOAD_LIMIT <= hung[0] < forge.HUB_HANG_LOAD_LIMIT + 4


def test_a_slow_healthy_load_is_not_ended():
    """While loading, only whether the page runs is asked: a page still
    loading may rightly paint nothing (in the rig a safe reload was ended
    mid-load when frames counted)."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.COMMITTED)
    for _ in range(20):
        tick()
        view.answer(False)
        clock.now += forge.HUB_HANG_PING
    assert hung == []
    assert {args["frames"] for _, args, _ in view.asked} == {0.0}
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    assert view.asked[-1][1]["frames"] == 1.0, "frames count once it has loaded"


class ScriptDialog:
    pass


ScriptDialog.__name__ = "WebKitScriptDialogImpl"


def test_a_page_stuck_right_after_webkits_own_dialog_is_caught():
    """The critic's confirm('x'); for(;;){}: the dialog flag waited for an
    answer the stuck page never gives. WebKit draws its dialog inside the
    view, so once that is gone the count starts afresh."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    view.dialog()
    view.inside.append(ScriptDialog())
    for _ in range(10):
        clock.now += forge.HUB_HANG_PING
        tick()
    assert hung == []
    view.inside.clear()  # Emerson answered it; the page then sticks
    closed = clock.now + forge.HUB_HANG_PING
    for _ in range(5):
        clock.now += forge.HUB_HANG_PING
        tick()
    assert hung and closed + LIMIT <= hung[0] < closed + LIMIT + forge.HUB_HANG_PING


def test_after_webkits_dialog_the_late_answer_counts_no_missing_frame():
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    view.dialog()
    view.inside.append(ScriptDialog())
    for _ in range(10):
        clock.now += forge.HUB_HANG_PING
        tick()
    view.inside.clear()
    clock.now += forge.HUB_HANG_PING
    tick()
    view.answer(False)  # the old question, waited out behind the dialog
    for _ in range(4):
        clock.now += forge.HUB_HANG_PING
        tick()
        view.answer(True)
    assert hung == []


def test_a_print_dialog_pauses_the_count_too():
    """window.print() keeps the page waiting like confirm() (the critic's
    run: a healthy page ended 16 s into the print dialog)."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    assert view.handlers["print"](view, object()) is False
    for _ in range(10):
        clock.now += forge.HUB_HANG_PING
        tick()
    assert hung == []


def test_a_crashed_page_is_asked_nothing_more(capsys):
    """A page that died with a question out answered it with an error,
    logged as the watchdog's own failure; and a crashed page is not
    hung, the reloader has it."""
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    view.handlers["web-process-terminated"](view, object())
    view.answer(GLib.Error("Unsupported result type"))
    for _ in range(10):
        clock.now += forge.HUB_HANG_PING
        tick()
    assert hung == [] and len(view.asked) == 1
    assert "failed" not in capsys.readouterr().out


def test_main_runs_the_watchdog():
    """Taking the watchdog's timer out of main() passed every other test
    (the critic's mutation run)."""
    src = inspect.getsource(forge.main)
    assert re.search(
        r"GLib\.timeout_add_seconds\(\s*HUB_HANG_PING,\s*hub_hang_watchdog\(", src
    )
    assert "web-process-terminated" in src and "hub_crash_reloader(" in src


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_question_waits_for_a_frame_when_asked_to():
    """The question itself, run as WebKit runs it (an async function body
    with frames and wait as arguments): no frame within wait is false, a
    frame is true, and without frames it never waits. A question that
    skipped the frame passed every other test (the critic's run)."""
    script = f"""
const ask = async (frames, wait) => {{ {forge.HUB_HANG_ASK} }};
const out = [];
globalThis.requestAnimationFrame = () => 0;  // a stuck compositor
out.push(await ask(1, 50));
globalThis.requestAnimationFrame = (paint) => setTimeout(paint, 5);
out.push(await ask(1, 2000));
globalThis.requestAnimationFrame = () => {{ throw new Error("asked"); }};
out.push(await ask(0, 50));
console.log(JSON.stringify(out));
"""
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == [False, True, True]


def test_a_new_page_starts_with_a_clean_count():
    view, clock, hung, tick = watchdog()
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()  # asked at 0, never answered: the page is being replaced
    clock.now = 8.0
    view.load(WebKit2.LoadEvent.STARTED)
    view.load(WebKit2.LoadEvent.COMMITTED)
    tick()
    assert len(view.asked) == 2, "the new page is asked at once"
    clock.now = 12.0
    tick()
    assert hung == [], "the old page's question does not count"


def test_a_page_not_drawn_is_only_asked_whether_it_runs():
    view, clock, hung, tick = watchdog()
    view.mapped = False  # an app's real web view, or the window unmapped
    view.load(WebKit2.LoadEvent.FINISHED)
    tick()
    assert view.asked[0][1]["frames"] == 0.0
