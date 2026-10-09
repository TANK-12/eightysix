"""Drive the real Terminal page in headless Chrome: typing, keys, htop, tabs, split
panes, reload.

    .venv/bin/python tests/check_ui.py [--shots DIR]

Not collected by pytest (it needs the Flatpak Chrome). Starts its own backend
on a free port; prints PASS/FAIL lines and exits non-zero on any FAIL. With
--shots it saves a screenshot of htop running and of a coloured prompt.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import CTRL, SHIFT, Page, chrome_page, serve  # noqa: E402

results: list[str] = []

SCREEN = """(() => { const b = S.active.term.buffer.active; let s = "";
  for (let i = 0; i < b.length; i++) s += b.getLine(i).translateToString(true) + "\\n";
  return s; })()"""


def check(name: str, ok: bool, extra: str = "") -> None:
    tail = f" :: {extra[-300:]!r}" if extra and not ok else ""
    results.append(f"{'PASS' if ok else 'FAIL'} :: {name}{tail}")


async def screen_has(p: Page, text: str, timeout: float = 6) -> bool:
    return await p.wait(f"{SCREEN}.includes({text!r})", timeout)


async def run_cmd(p: Page, cmd: str) -> None:
    await p.type(cmd)
    await p.key("Enter", "Enter", 0, 13)


async def run(p: Page, port: int, shots: Path | None) -> None:
    await p.go(f"http://127.0.0.1:{port}/")
    ok = await p.wait("S.active && S.active.ws && S.active.ws.readyState === 1", 10)
    check("a tab opens and its socket connects", ok)
    check("the shell prompt shows", await screen_has(p, "$"))

    await run_cmd(p, "echo answer=$((6*7))")
    check("typed command runs", await screen_has(p, "answer=42"))

    # Plain Ctrl+V must reach the program (Claude Code reads images itself).
    # Raw mode, as Claude Code reads keys: the byte must arrive as 0x16.
    await run_cmd(
        p,
        "python3 -c 'import sys,tty,termios;o=termios.tcgetattr(0);tty.setraw(0);b=sys.stdin.buffer.read(1);termios.tcsetattr(0,termios.TCSADRAIN,o);print(\"got\",b.hex())'",
    )
    await asyncio.sleep(0.5)
    await p.key("v", "KeyV", CTRL, 86)
    check("Ctrl+V goes through to the program", await screen_has(p, "got 16"))
    await run_cmd(p, "sleep 30")
    await asyncio.sleep(0.3)
    await p.key("c", "KeyC", CTRL, 67)
    await run_cmd(p, "echo after-ctrl-c")
    check("Ctrl+C interrupts", await screen_has(p, "after-ctrl-c"))

    # The pty size follows the page.
    cols, rows = await p.js("[S.active.term.cols, S.active.term.rows]")
    await run_cmd(p, "stty size")
    check(
        "stty size matches the page",
        await screen_has(p, f"{rows} {cols}"),
        f"{rows} {cols}",
    )

    await run_cmd(p, "printf '\\e[31mred \\e[32mgreen \\e[1;34mbold-blue\\e[0m\\n'")
    await screen_has(p, "bold-blue")
    if shots:
        await p.screenshot(shots / "term-colours.png")

    # A full-screen program.
    await run_cmd(p, "htop")
    ok = await p.wait("S.active.term.buffer.active.type === 'alternate'", 6)
    ok = ok and await screen_has(p, "Load average")
    check("htop draws on the alternate screen", ok)
    await asyncio.sleep(1.2)
    label = await p.js("document.querySelector('.tab.active .label').textContent")
    check("tab is named after the running program", label == "htop", label)
    if shots:
        await p.screenshot(shots / "term-htop.png")
    await p.key("q", "KeyQ", 0, 81)
    check(
        "q leaves htop",
        await p.wait("S.active.term.buffer.active.type === 'normal'", 5),
    )

    # Tabs.
    await p.key("T", "KeyT", CTRL | SHIFT, 84)
    ok = await p.wait(
        "S.tabs.length === 2 && S.tab === S.tabs[1] && S.active.ws?.readyState === 1",
        6,
    )
    check("Ctrl+Shift+T opens a second tab", ok)
    await p.key("W", "KeyW", CTRL | SHIFT, 87)
    check("Ctrl+Shift+W closes it", await p.wait("S.tabs.length === 1", 5))

    await split_panes(p, port, shots)

    # Font size.
    before = await p.js("S.active.term.cols")
    await p.key("=", "Equal", CTRL, 187)
    await p.key("=", "Equal", CTRL, 187)
    ok = await p.wait(f"S.fontSize === 16 && S.active.term.cols < {before}", 4)
    now = await p.js(
        "JSON.stringify([S.fontSize, S.active.term.cols,"
        " document.activeElement.className, localStorage.getItem('term.font')])"
    )
    check("Ctrl+= makes text bigger", ok, f"{now} (cols before {before})")

    # Find in scrollback (Ctrl+Shift+F, the xterm search add-on).
    await run_cmd(p, "for i in 1 2 3; do echo findme-$i; done")
    await screen_has(p, "findme-3")
    await p.key("F", "KeyF", CTRL | SHIFT, 70)
    ok = await p.wait(
        "!$('find').classList.contains('hidden') && document.activeElement.id === 'find-q'",
        4,
    )
    check("Ctrl+Shift+F opens the find bar with the box focused", ok)
    await p.type("findme-")
    # The typed command line holds one more "findme-" than the three output lines.
    count = "$('find-count').textContent"
    ok = await p.wait(f"/ of 4$/.test({count})", 4)
    check("find counts every match", ok, await p.js(count))
    ok = await p.wait("S.active.term.getSelection() === 'findme-'", 3)
    check("the current match is selected", ok)
    before = await p.js(count)
    await p.key("Enter", "Enter", 0, 13)
    ok = await p.wait(f"{count} !== {before!r} && / of 4$/.test({count})", 3)
    check("Enter moves to another match", ok, await p.js(count))
    await p.js("$('find-regex').click()")
    await p.js("$('find-q').select()")
    await p.type("findme-[23]$")
    ok = await p.wait(f"/ of 2$/.test({count})", 4)
    check("regular expression search", ok, await p.js(count))
    if shots:
        await p.screenshot(shots / "term-find.png")
    await p.key("Escape", "Escape", 0, 27)
    ok = await p.wait(
        "$('find').classList.contains('hidden') && "
        "document.activeElement.classList.contains('xterm-helper-textarea')",
        3,
    )
    check("Escape closes find and gives the keyboard back", ok)
    await p.js("$('find-regex').click()")
    await run_cmd(p, "echo typing-works-after-find")
    check(
        "typing reaches the shell after find",
        await screen_has(p, "typing-works-after-find"),
    )

    # Reload keeps the shell and its screen.
    tid = await p.js("S.active.id")
    await p.go(f"http://127.0.0.1:{port}/")
    ok = await p.wait(
        f"S.active && S.active.id === {tid!r} && S.active.ws?.readyState === 1", 10
    )
    check("reload reattaches to the same shell", ok)
    check("reload brings the old screen back", await screen_has(p, "answer=42"))

    # `exit` marks the tab dead; Enter closes it and a fresh one appears.
    await run_cmd(p, "exit")
    check("exit is shown", await screen_has(p, "press Enter to close"))
    await p.key("Enter", "Enter", 0, 13)
    ok = await p.wait(
        f"S.tabs.length === 1 && S.active.id !== {tid!r} && !S.active.dead", 6
    )
    check("closing the last tab opens a new one", ok)


PANES = "panesOf(S.tab.root)"
LIVE = f"{PANES}.every(x => x.ws?.readyState === 1)"


def pane_screen(i: int) -> str:
    return (
        f"(() => {{ const b = {PANES}[{i}].term.buffer.active; let s = '';"
        " for (let i = 0; i < b.length; i++) s += b.getLine(i).translateToString(true) + '\\n';"
        " return s; })()"
    )


async def drag(p: Page, x0: float, y0: float, x1: float, y1: float) -> None:
    mouse = "Input.dispatchMouseEvent"
    await p.call(mouse, type="mouseMoved", x=x0, y=y0)
    await p.call(
        mouse, type="mousePressed", x=x0, y=y0, button="left", buttons=1, clickCount=1
    )
    for k in range(1, 6):
        x, y = x0 + (x1 - x0) * k / 5, y0 + (y1 - y0) * k / 5
        await p.call(mouse, type="mouseMoved", x=x, y=y, button="left", buttons=1)
    await p.call(
        mouse, type="mouseReleased", x=x1, y=y1, button="left", buttons=0, clickCount=1
    )


async def split_panes(p: Page, port: int, shots: Path | None) -> None:
    """Split right and down, each pane its own shell; focus moves; the
    divider drags; a reload keeps the layout; closing a pane frees its space."""
    await p.key("D", "KeyD", CTRL | SHIFT, 68)
    ok = await p.wait(f"S.tabs.length === 1 && {PANES}.length === 2 && {LIVE}", 6)
    check("Ctrl+Shift+D splits right into a second live shell", ok)
    await screen_has(p, "$")
    await run_cmd(p, "echo pane-two")
    check("the new pane runs its own input", await screen_has(p, "pane-two"))
    side = await p.js(
        f"(() => {{ const [a, b] = {PANES}.map(x => x.el.getBoundingClientRect());"
        " return a.right <= b.left + 1 && Math.abs(a.top - b.top) < 2; })()"
    )
    check("it sits to the right", side is True)
    await p.key("E", "KeyE", CTRL | SHIFT, 69)
    ok = await p.wait(f"{PANES}.length === 3 && {LIVE}", 6)
    check("Ctrl+Shift+E splits down into a third", ok)
    await screen_has(p, "$")
    await run_cmd(p, "echo pane-three")
    check("the third pane runs its own input", await screen_has(p, "pane-three"))
    below = await p.js(
        f"(() => {{ const ps = {PANES}; const b = ps[1].el.getBoundingClientRect(),"
        " c = ps[2].el.getBoundingClientRect();"
        " return c.top >= b.bottom - 1 && Math.abs(c.left - b.left) < 2; })()"
    )
    check("it sits below the pane it split", below is True)
    first = await p.js(pane_screen(0))
    check(
        "each pane keeps its own screen",
        "answer=42" in first and "pane-two" not in first and "pane-three" not in first,
        first,
    )
    await p.key("ArrowLeft", "ArrowLeft", CTRL | SHIFT, 37)
    ok = await p.wait(
        f"S.active === {PANES}[0]"
        " && document.activeElement.closest('.pane') === S.active.el",
        3,
    )
    check("Ctrl+Shift+Left moves focus to the left pane", ok)
    await run_cmd(p, "echo back-in-one")
    ok = await p.wait(f"{pane_screen(0)}.includes('back-in-one')", 4)
    check("typing goes to the focused pane", ok)
    await p.key("ArrowRight", "ArrowRight", CTRL | SHIFT, 39)
    check(
        "Ctrl+Shift+Right moves it back",
        await p.wait(f"S.active !== {PANES}[0]", 3),
    )
    if shots:
        await p.screenshot(shots / "term-split.png")

    w0, cols0 = await p.js(
        f"[{PANES}[0].el.getBoundingClientRect().width, {PANES}[0].term.cols]"
    )
    x, y = await p.js(
        "(() => { const r = document.querySelector('.split.row > .divider')"
        ".getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()"
    )
    await drag(p, x, y, x + 180, y)
    ok = await p.wait(
        f"{PANES}[0].el.getBoundingClientRect().width > {w0} + 120"
        f" && {PANES}[0].term.cols > {cols0}",
        3,
    )
    check("dragging the divider resizes the panes", ok)

    ids = await p.js(f"JSON.stringify({PANES}.map(x => x.id))")
    await p.go(f"http://127.0.0.1:{port}/")
    ok = await p.wait(
        f"S.tab && JSON.stringify({PANES}.map(x => x.id)) === {ids!r} && {LIVE}", 10
    )
    check("reload keeps the panes and their shells", ok)
    ratio = await p.js("S.tab.root.ratio")
    check("and the divider where it was dragged", ratio > 0.6, str(ratio))

    covered = (
        "(() => { const s = S.tab.el.getBoundingClientRect();"
        f" return {PANES}.reduce((t, x) => {{ const r = x.el.getBoundingClientRect();"
        " return t + r.width * r.height; }, 0) / (s.width * s.height); })()"
    )
    before = await p.js(covered)
    await p.key("W", "KeyW", CTRL | SHIFT, 87)
    ok = await p.wait(f"{PANES}.length === 2 && {LIVE}", 5)
    check("Ctrl+Shift+W closes the focused pane", ok)
    after = await p.js(covered)
    check(
        "its neighbour takes the space", after > before + 0.001, f"{before} -> {after}"
    )
    ok = await p.wait("document.activeElement.closest('.pane') === S.active.el", 3)
    check("and the keyboard moves to the pane now in focus", ok)
    await p.key("W", "KeyW", CTRL | SHIFT, 87)
    ok = await p.wait(f"S.tabs.length === 1 && {PANES}.length === 1 && {LIVE}", 5)
    check("closing down to one pane leaves a plain tab", ok)
    # the last pane fills the tab and its terminal is refitted to that width
    await p.wait(
        "S.active.el.getBoundingClientRect().width >= S.tab.el.getBoundingClientRect().width - 1",
        3,
    )
    await asyncio.sleep(0.3)


async def drive(box: Path, shots: Path | None) -> None:
    with serve(APP) as port:
        async with chrome_page(box, "1000,600") as page:
            await asyncio.wait_for(run(page, port, shots), 120)


def main() -> int:
    shots = (
        Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
    )
    box = APP / "tests" / f".ui-{os.getpid()}"
    box.mkdir()
    try:
        asyncio.run(drive(box, shots))
    except Exception as e:  # noqa: BLE001 - report, then clean up
        results.append(f"FAIL :: harness error :: {e!r}")
    finally:
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) or not results else 0


if __name__ == "__main__":
    sys.exit(main())
