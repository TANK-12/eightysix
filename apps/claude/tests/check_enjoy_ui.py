"""The Enjoy layout in real headless Chrome, against a scratch copy.

Not a pytest file (it needs Flatpak Chrome and `websockets`); run it with a
venv that has websockets, from the app folder:

    ../files/.venv/bin/python tests/check_enjoy_ui.py

The copy gets its own data folder (FORGE_CLAUDE_DATA, never the real one) and
the fake Claude (tests/fake_claude.py), so nothing is spent. It checks the
2026-09-27 additions: the task's model / effort / permission pickers save and
become the start for new tasks, a loose task dragged onto a project is filed
there (and dragged back is loose again), a file dropped on the chat becomes a
chip, and views open without page errors.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import (
    chrome_page,
    free_port,
    wait_http,
)  # noqa: E402

H = {"Content-Type": "application/json", "X-Forge": "1"}


def call(port: int, path: str, body: dict | None = None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=None if body is None else json.dumps(body).encode(),
        headers=H,
        method="GET" if body is None else "POST",
    )
    return json.load(urllib.request.urlopen(req, timeout=30))


# a drag between two elements, with the DataTransfer the page reads
DRAG_JS = """(src, dst) => {
  const dt = new DataTransfer();
  const at = (n, type) => n.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt}));
  at(src, 'dragstart'); at(dst, 'dragenter'); at(dst, 'dragover');
  const lit = dst.classList.contains('e-drop-ok');
  at(dst, 'drop'); at(src, 'dragend');
  return lit;
}"""


async def run(port: int, sandbox: Path) -> list[str]:
    fails: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    call(port, "/api/projects", {"name": "cosmos", "cwd": str(sandbox)})
    loose = call(port, "/api/conversations", {"cwd": str(sandbox)})["id"]
    call(port, f"/api/conversations/{loose}/settings", {"title": "tidy the notes"})

    async with chrome_page(sandbox, "1400,900") as page:
        base = f"http://127.0.0.1:{port}/enjoy.html"
        await page.go(base + "#projects")
        await page.wait(
            "document.querySelectorAll('#e-loose-list li[draggable]').length"
        )
        await page.js(
            "window.__e=[];addEventListener('error',e=>__e.push(String(e.message)));1"
        )
        stag = await page.js("document.querySelector('#e-loose-list').className")
        check("e-stagger" in stag, "rows rise in when the view opens")
        await page.screenshot(sandbox / "enjoy_projects.png")

        lit = await page.js(
            f"({DRAG_JS})(document.querySelector('#e-loose-list li[draggable]'),"
            " document.querySelector('#e-project-grid .e-project'))"
        )
        check(lit, "a project card lights up under a dragged task")
        await asyncio.sleep(1.2)
        filed = call(port, "/api/projects")
        cosmos = next(p for p in filed["projects"] if p["name"] == "cosmos")
        check(
            any(t["id"] == loose for t in cosmos.get("tasks", [])),
            "the dropped task is filed into the project",
        )
        toast = await page.js("document.querySelector('#e-toast').textContent")
        check("filed into cosmos" in toast, f"a toast says so: {toast!r}")

        await page.go(base + f"#project/{cosmos['id']}/tasks")
        await page.wait(
            "document.querySelectorAll('#e-task-list li[draggable]').length"
        )
        # back out: the loose tasks section is a drop zone (it sits on the
        # projects view, hidden here, which does not matter to the events)
        await page.js(
            f"({DRAG_JS})(document.querySelector('#e-task-list li[draggable]'),"
            " document.getElementById('e-loose'))"
        )
        await asyncio.sleep(1.2)
        back = call(port, "/api/projects")
        check(
            any(t["id"] == loose for t in back.get("loose", [])),
            "dragged onto loose tasks, it is loose again",
        )

        await page.go(base + f"#task/{loose}")
        await page.wait("document.querySelectorAll('#e-t-model option').length", 20)
        opts = json.loads(
            await page.js(
                "JSON.stringify(['e-t-model','e-t-effort','e-t-mode'].map(i=>document.getElementById(i).options.length))"
            )
        )
        check(all(n > 1 for n in opts), f"model, effort and permission lists: {opts}")
        await page.js(
            "(()=>{const m=document.getElementById('e-t-model');m.value='sonnet';m.dispatchEvent(new Event('change'));"
            "const e=document.getElementById('e-t-effort');e.value='high';e.dispatchEvent(new Event('change'));"
            "const p=document.getElementById('e-t-mode');p.value='plan';p.dispatchEvent(new Event('change'));})();1"
        )
        await asyncio.sleep(1.2)
        meta = call(port, f"/api/conversations/{loose}/events?after=-1")["meta"]
        check(
            (meta.get("model"), meta.get("effort"), meta.get("mode"))
            == ("sonnet", "high", "plan"),
            f"the pickers save: {meta.get('model')}, {meta.get('effort')}, {meta.get('mode')}",
        )
        note = await page.js("document.getElementById('e-t-knob-note').textContent")
        check(note.startswith("saved"), f"a note confirms it: {note!r}")

        await page.js(
            "(()=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array([137,80,78,71])],'shot.png',{type:'image/png'}));"
            "const c=document.getElementById('e-t-chat');"
            "for (const t of ['dragenter','dragover','drop']) c.dispatchEvent(new DragEvent(t,{bubbles:true,cancelable:true,dataTransfer:dt}));})();1"
        )
        await asyncio.sleep(1.2)
        chips = await page.js("document.querySelectorAll('#e-t-chips .chip').length")
        check(chips == 1, f"a dropped file becomes a chip ({chips})")
        await page.screenshot(sandbox / "enjoy_task.png")

        await page.go(base + "#projects")
        await page.wait("document.querySelector('#e-project-grid .e-project')")
        await page.go(base + f"#project/{cosmos['id']}/tasks")
        await page.wait("document.querySelector('#e-new-task')")
        await page.js("document.getElementById('e-new-task').click();1")
        await page.wait(
            "location.hash.startsWith('#task/') && location.hash.slice(6)!=="
            + json.dumps(loose),
            10,
        )
        await asyncio.sleep(1)
        fresh = (await page.js("location.hash"))[len("#task/") :]
        meta2 = call(port, f"/api/conversations/{fresh}/events?after=-1")["meta"]
        check(
            (meta2.get("model"), meta2.get("effort"), meta2.get("mode"))
            == ("sonnet", "high", "plan"),
            f"a new task starts with the last picks: {fresh} {meta2.get('model')}, {meta2.get('effort')}, {meta2.get('mode')}",
        )
        errs = await page.js("JSON.stringify(window.__e||[])")
        check(errs == "[]", f"no page errors: {errs}")
    return fails


def start(env: dict) -> tuple[subprocess.Popen, int]:
    """The app on a free port. Its own start and stop rather than cdp_driver's
    serve(): a waiting long-poll can hold uvicorn past serve()'s 10 s."""
    port = free_port()
    proc = subprocess.Popen(
        [str(APP / ".venv/bin/python"), "-m", "uvicorn", "web_app:app"]
        + ["--port", str(port)],
        cwd=APP,
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_http(f"http://127.0.0.1:{port}/")
    return proc, port


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(10)


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="enjoy-"))
    try:
        env = {
            "FORGE_CLAUDE_DATA": str(sandbox / "data"),
            "FORGE_CLAUDE_BIN": f"{sys.executable} {APP / 'tests/fake_claude.py'}",
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
        proc, port = start(env)
        try:
            fails = asyncio.run(run(port, sandbox))
        finally:
            stop(proc)
        if "--keep" in sys.argv:
            for name in ("enjoy_projects.png", "enjoy_task.png"):
                if (sandbox / name).exists():
                    shutil.copy(sandbox / name, Path(sys.argv[-1]) / name)
        print("all passed" if not fails else f"{len(fails)} failed")
        return 1 if fails else 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
