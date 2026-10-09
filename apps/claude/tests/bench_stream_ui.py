"""How hard the Claude page works while a reply streams in (Emerson #185).

Not a pytest file (it needs Flatpak Chrome and `websockets`). Run it from the
app folder with a venv that has websockets:

    ../files/.venv/bin/python tests/bench_stream_ui.py [--webkit]

Sends "pace 400" to the fake CLI (400 words at 40 a second, about 10 s) and
reads Chrome's own main-thread counters over the stream, then over 3 s of a
turn that is busy but silent ("slow"). Prints the share of one core each
window used; headless Chrome is not WebKitGTK, so compare runs, not machines.
--webkit then repeats the stream in a real on-screen WebKitGTK window (what
Forge uses) and reports the CPU of its processes from /proc.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tests"))
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import chrome_page  # noqa: E402
from check_enjoy_ui import start, stop  # noqa: E402

KEYS = ("TaskDuration", "ScriptDuration", "LayoutDuration", "RecalcStyleDuration")


async def metrics(page) -> dict:
    got = await page.call("Performance.getMetrics")
    return {m["name"]: m["value"] for m in got["metrics"] if m["name"] in KEYS}


def share(a: dict, b: dict, wall: float) -> str:
    return "  ".join(
        f"{k.replace('Duration', '')} {100 * (b[k] - a[k]) / wall:5.1f}%" for k in KEYS
    )


async def send(page, text: str) -> None:
    await page.js(
        f"(() => {{ const i = document.getElementById('input'); i.value = {text!r};"
        " i.dispatchEvent(new Event('input')); document.getElementById('send').click(); return 1 })()"
    )


async def run(port: int, sandbox: Path) -> None:
    async with chrome_page(sandbox, "1300,800") as page:
        await page.go(f"http://127.0.0.1:{port}/")
        await page.wait("!!document.querySelector('.tab')", 15)
        await page.call("Performance.enable")
        await asyncio.sleep(1)
        await send(page, "pace 400")
        await page.wait("document.body.innerText.includes('word1 ')", 10)
        a, t0 = await metrics(page), time.time()
        await page.wait("document.body.innerText.includes('word398')", 30)
        b, t1 = await metrics(page), time.time()
        print(f"streaming {t1 - t0:4.1f}s: {share(a, b, t1 - t0)}")
        await page.wait("!document.querySelector('.tab .busy')", 10)
        await send(page, "slow")
        await page.wait("!!document.querySelector('.tab .busy')", 10)
        await asyncio.sleep(0.5)
        a, t0 = await metrics(page), time.time()
        await asyncio.sleep(3)
        b, t1 = await metrics(page), time.time()
        print(f"busy, silent {t1 - t0:3.1f}s: {share(a, b, t1 - t0)}")


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="bench-"))
    try:
        env = {
            "FORGE_CLAUDE_DATA": str(sandbox / "data"),
            "FORGE_CLAUDE_BIN": f"{sys.executable} {APP / 'tests/fake_claude.py'}",
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
        proc, port = start(env)
        try:
            asyncio.run(run(port, sandbox))
            if "--webkit" in sys.argv:
                subprocess.run(
                    ["/usr/bin/python3", str(APP / "tests/bench_stream_webkit.py")]
                    + [f"http://127.0.0.1:{port}/"],
                    timeout=90,
                )
        finally:
            stop(proc)
        return 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
