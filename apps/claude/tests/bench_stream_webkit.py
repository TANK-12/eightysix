"""The Claude page in a real on-screen WebKitGTK window while a reply
streams in (Emerson #185): CPU of the window's own process and its WebKit
helpers, read from /proc. Run by bench_stream_ui.py --webkit with the
system Python (it needs gi):  /usr/bin/python3 tests/bench_stream_webkit.py URL
"""

import os
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

TICK = os.sysconf("SC_CLK_TCK")
SEND = (
    "(() => { const i = document.getElementById('input'); i.value = '%s';"
    " i.dispatchEvent(new Event('input')); document.getElementById('send').click(); return 1 })()"
)


def family() -> dict[int, str]:
    """Our pid and every descendant, pid -> command name."""
    parent, names = {}, {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                stat = open(f"/proc/{d}/stat").read()
            except OSError:
                continue
            names[int(d)] = stat[stat.index("(") + 1 : stat.rindex(")")]
            parent[int(d)] = int(stat[stat.rindex(")") + 2 :].split()[1])
    mine, grew = {os.getpid()}, True
    while grew:
        grew = False
        for pid, pp in parent.items():
            if pp in mine and pid not in mine:
                mine.add(pid)
                grew = True
    return {p: names[p] for p in mine}


def cpu() -> dict[str, float]:
    out: dict[str, float] = {}
    for pid, name in family().items():
        try:
            f = open(f"/proc/{pid}/stat").read()
        except OSError:
            continue
        fields = f[f.rindex(")") + 2 :].split()
        out[name] = out.get(name, 0.0) + (int(fields[11]) + int(fields[12])) / TICK
    return out


def report(label: str, a: dict, b: dict, wall: float) -> None:
    parts = {k: 100 * (b.get(k, 0) - a.get(k, 0)) / wall for k in b}
    total = sum(parts.values())
    detail = "  ".join(f"{k} {v:.0f}%" for k, v in sorted(parts.items()) if v >= 0.5)
    print(f"webkit {label} {wall:4.1f}s: total {total:5.1f}% of a core  ({detail})")


win = Gtk.Window()
win.set_default_size(1300, 800)
view = WebKit2.WebView()
win.add(view)
win.show_all()
view.load_uri(sys.argv[1])
state = {"stage": "boot", "at": time.time()}


def ask(expr, then):
    def done(v, res):
        try:
            then(v.evaluate_javascript_finish(res).to_boolean())
        except GLib.Error:
            then(False)

    view.evaluate_javascript(expr, -1, None, None, None, done)


def step():
    s = state["stage"]
    if time.time() - state["at"] > 40:
        print("webkit: timed out at", s)
        Gtk.main_quit()
        return False
    if s == "boot":
        ask("!!document.querySelector('.tab')", lambda ok: ok and go("sent", SEND % "pace 400"))
    elif s == "sent":
        ask("document.body.innerText.includes('word1 ')", lambda ok: ok and mark("streaming"))
    elif s == "streaming":
        ask("document.body.innerText.includes('word398')", lambda ok: ok and finish("stream"))
    elif s == "idle":
        if time.time() - state["t0"] >= 3:
            finish("idle")
    return True


def go(stage, js):
    state["stage"] = stage
    view.evaluate_javascript(js, -1, None, None, None, None)


def mark(stage):
    state.update(stage=stage, t0=time.time(), c0=cpu())


def finish(label):
    report(label, state["c0"], cpu(), time.time() - state["t0"])
    if label == "stream":
        mark("idle")  # 3 s after the reply, nothing streaming
    else:
        Gtk.main_quit()


GLib.timeout_add(150, step)
Gtk.main()
