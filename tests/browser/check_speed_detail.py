"""Settings > Speed and detail and the Power app, end to end in headless Chrome
(Emerson, 2026-09-27: the speed sliders in Settings and Power "update
properly also when unplugged", the auto-switch moves the slider, and one
section collects every frame rate and detail slider).

    apps/dossier/.venv/bin/python tests/browser/check_speed_detail.py

Not collected by pytest (it needs the Flatpak Chrome). Both backends run on
free ports with HOME pointed at a sandbox, so they share a sandbox
settings.json. Each page sits in a same-origin frame, as inside the hub, and
the check sends it the hub's theme message. Nothing is saved through the
APIs: a POST would rewrite the real hub/theme.js, so a change "made
elsewhere" is written straight into the sandbox file, and Settings' own save
is stubbed out. Prints PASS/FAIL lines, saves two screenshots to ~/.cache and
exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from cdp_driver import Page, chrome_page, reap, serve  # noqa: E402

results: list[str] = []
SECTION = "speed-and-detail"


def check(name: str, ok: bool, extra: object = "") -> None:
    note = f" :: {extra}" if extra != "" and not ok else ""
    results.append(f"{'PASS' if ok else 'FAIL'} :: {name}{note}")


def frame_page(path: str) -> str:
    """Replace the page with a frame of `path` on the same origin."""
    return (
        'document.open(); document.write(\'<body style="margin:0">'
        f'<iframe id=f src="{path}" style="width:100vw;height:100vh;border:0"></iframe>'
        "'); document.close(); true"
    )


def in_frame(expr: str) -> str:
    """An expression run in the frame's own global scope (its let/const too)."""
    return f"document.getElementById('f').contentWindow.eval({json.dumps(expr)})"


def hub_says(on_battery: bool) -> str:
    theme = {"on_battery": on_battery, "max_fps": 60}
    return (
        "document.getElementById('f').contentWindow.postMessage("
        f"{{forge: 'theme', theme: {json.dumps(theme)}}}, '*'); true"
    )


async def settings_page(p: Page, port: int, config: Path, shot: Path) -> None:
    await p.go(f"http://127.0.0.1:{port}/?outer")
    await p.js(frame_page(f"/#{SECTION}"))
    ok = await p.wait(
        in_frame("state.settings !== null && !!document.querySelector('.slider.item')"),
        15,
    )
    check("Settings loads in a frame", ok)
    # never POST (see the docstring); like the real one it takes the pending change
    await p.js(in_frame("flush = async () => { state.pending = {}; }; true"))
    await p.js(in_frame(f"showSection('{SECTION}'); true"))
    labels = await p.js(
        in_frame(
            f"[...document.querySelectorAll('section[data-section=\"{SECTION}\"] .what label')]"
            ".map((l) => l.textContent)"
        )
    )
    labels = labels or []
    for want in (
        "Frame rate cap",
        "Frame rate on battery",
        "Particles on battery",
        "Browser video frame rate",
        "Browser video frame rate on battery",
        "Browser video quality",
        "Browser video quality on battery",
        "Smooth scrolling",
        "Smooth scrolling on battery",
        "Home screen: Particle frame rate",
        "Home screen: Particle amount",
        "Desktop particles: Frame rate",
        "Desktop particles: Amount",
    ):
        check(f"Speed and detail shows {want}", want in labels, labels)

    # the copy and the original are one setting
    copy = f"set-particle_fps-in-{SECTION}"
    await p.js(
        in_frame(
            f"const c = document.getElementById('{copy}'); c.value = 25;"
            " c.dispatchEvent(new Event('input')); true"
        )
    )
    original = await p.js(in_frame("document.getElementById('set-particle_fps').value"))
    check(
        "moving the copy moves the original on its own page", original == "25", original
    )

    # a change made elsewhere (the Power app) shows after the hub's message
    config.write_text(json.dumps({"max_fps": 33, "battery_fps": 17}))
    await p.js(hub_says(False))
    ok = await p.wait(
        in_frame("document.getElementById('set-max_fps').value === '33'"), 5
    )
    check("a cap changed in Power shows in Settings", ok)
    now = in_frame(
        "[...new Set([...document.querySelectorAll('.item.now [data-key]')]"
        ".map((i) => i.dataset.key))].sort()"
    )
    plugged = await p.js(now)
    check(
        "plugged in, the plugged-in rows are marked in use",
        "max_fps" in plugged and "battery_fps" not in plugged,
        plugged,
    )
    await p.js(hub_says(True))
    await p.wait(
        in_frame("!!document.querySelector('.item.now [data-key=battery_fps]')"), 3
    )
    unplugged = await p.js(now)
    check(
        "unplugged, the battery rows are marked instead",
        "battery_fps" in unplugged
        and "battery_smooth_scroll" in unplugged
        and "max_fps" not in unplugged,
        unplugged,
    )
    await p.screenshot(shot)


async def power_page(p: Page, port: int, config: Path, shot: Path) -> None:
    await p.go(f"http://127.0.0.1:{port}/?outer")
    await p.js(frame_page("/"))
    ok = await p.wait(
        in_frame(
            "MODES.length > 1 && document.getElementById('fps-slider').value === '33'"
        ),
        15,
    )
    check("Power loads and shows the saved cap", ok)

    config.write_text(json.dumps({"max_fps": 40, "battery_fps": 12}))
    await p.js(hub_says(True))
    ok = await p.wait(
        in_frame(
            "document.getElementById('fps-slider').value === '40'"
            " && document.getElementById('bat-fps-slider').value === '12'"
        ),
        5,
    )
    check("caps changed in Settings show in Power", ok)
    marked = await p.js(
        in_frame(
            "[document.getElementById('fps-desc').classList.contains('now'),"
            " document.getElementById('bat-fps-desc').classList.contains('now')]"
        )
    )
    check(
        "unplugged, the battery cap is marked in use", marked == [False, True], marked
    )

    # The watcher switching modes on unplugging, faked at /api/modes: the
    # slider follows on the next poll (every 5 s while shown).
    await p.js(
        in_frame(
            "window.fakeMode = MODES[MODES.length - 1].name; const realGet = getJSON;"
            " getJSON = async (u, o) => u === '/api/modes'"
            " ? Object.assign(await realGet(u, o), { current: window.fakeMode }) : realGet(u, o); true"
        )
    )
    ok = await p.wait(
        in_frame(
            "Number(document.getElementById('mode-slider').value) === MODES.length - 1"
        ),
        8,
    )
    state = await p.js(in_frame("document.getElementById('mode-state').textContent"))
    check("an automatic mode switch moves the slider by itself", ok, state)
    await p.js(in_frame("document.getElementById('fps-card').scrollIntoView(); true"))
    await p.screenshot(shot)


async def main() -> int:
    box = Path.home() / ".cache" / "forge-speed-check"
    shutil.rmtree(box, ignore_errors=True)
    config = box / ".config" / "forge" / "settings.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    shots = [
        Path.home() / ".cache" / f"forge-speed-{n}.png" for n in ("settings", "power")
    ]
    env = {"HOME": str(box), "FORGE_SHARED_DIR": str(ROOT / "shared")}
    try:
        with serve(ROOT / "apps/settings", env) as sport, serve(
            ROOT / "apps/power", env
        ) as pport:
            async with chrome_page(box, "1400,1000") as p:
                await settings_page(p, sport, config, shots[0])
                await power_page(p, pport, config, shots[1])
    finally:
        reap(box)
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    print("screenshots: " + " ".join(map(str, shots)))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
