"""Drive the real Board page in headless Chrome: FYI posts, grouped replies,
search and desktop alerts.

    ~/Forge/apps/files/.venv/bin/python tests/check_ui.py

(Any Forge venv with `websockets` runs it; the Board server itself runs from
this app's .venv.) Not collected by pytest, since it needs the Flatpak Chrome.
It uses its own throwaway board (CREW_HOME in a sandbox folder) and a fake
notify-send on PATH that writes to a file, so nothing reaches the real board or
the desktop. Prints PASS/FAIL lines and exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import (
    chrome_page,
    serve,
)  # noqa: E402  # noqa: E402  # pyright: ignore[reportMissingImports]

CREW = [sys.executable, str(Path.home() / ".claude/skills/crew/crew.py")]
results: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append(
        f"{'PASS' if ok else 'FAIL'} :: {name}{' :: ' + extra if extra and not ok else ''}"
    )


def crew(env: dict, *argv: str) -> None:
    subprocess.run(CREW + list(argv), env={**os.environ, **env}, check=True)


async def main(box: Path) -> None:
    bin_dir = box / "bin"
    bin_dir.mkdir(parents=True)
    log = box / "notified.txt"
    fake = bin_dir / "notify-send"
    fake.write_text(f'#!/bin/sh\nprintf "%s|" "$@" >> {log}\necho >> {log}\n')
    fake.chmod(0o755)
    env = {
        "CREW_HOME": str(box / "crews"),
        "CLAUDE_SESSIONS_DIR": str(box / "sessions"),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }
    # a live session (this script's pid) that has launched one agent
    (box / "sessions").mkdir()
    (box / "sessions" / "55.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "sessionId": "sid-55",
                "name": "ejb-55",
                "status": "busy",
            }
        )
    )
    agents = box / "projects" / "-home-ejb" / "sid-55" / "subagents"
    agents.mkdir(parents=True)
    (box / "projects" / "-home-ejb" / "sid-55.jsonl").write_text("{}\n")
    (agents / "agent-1.meta.json").write_text(
        json.dumps(
            {"agentType": "Explore", "description": "Find the hooks", "model": "haiku"}
        )
    )
    (agents / "agent-1.jsonl").write_text("{}\n")
    crew(env, "join", "forge", "ejb-55", "--role", "solo")
    crew(env, "post", "forge", "ejb-55", "which names?", "--to", "Emerson")
    for i, who in enumerate(["Emerson", "ejb-55", "Emerson", "ejb-55"], 1):
        to = "ejb-55" if who == "Emerson" else "Emerson"
        crew(env, "post", "forge", who, f"answer {i}", "--to", to, "--re", str(i))
    crew(env, "post", "forge", "ejb-55", "fyi for you", "--to", "Emerson", "--fyi")

    with serve(APP, env) as port:
        async with chrome_page(box / "profile") as page:
            await page.go(f"http://127.0.0.1:{port}/")
            await page.wait("document.querySelectorAll('.note').length >= 5")
            persona = json.loads(
                subprocess.run(
                    CREW + ["dump", "forge"],
                    env={**os.environ, **env},
                    capture_output=True,
                    text=True,
                ).stdout
            )["members"]["ejb-55"].get("persona", "")
            check(
                "a session is shown by its persona name (B27)",
                bool(persona)
                and await page.js(
                    f"document.body.innerText.includes({json.dumps(persona + ' (ejb-55)')})"
                ),
                persona,
            )
            check(
                "replies fold under the first note of their chain",
                await page.js("document.querySelectorAll('.thread').length") == 2
                and await page.js("document.querySelectorAll('.replies .note').length")
                == 3,
            )
            await page.js("document.querySelector('[data-more]').click()")
            check(
                "Show earlier answers opens the whole chain",
                await page.wait(
                    "document.querySelectorAll('.replies .note').length === 4"
                ),
            )
            check(
                "an FYI note is labelled and not counted as waiting on Emerson",
                await page.js("!!document.querySelector('#n6 .pill.fyi')")
                and await page.js("!document.querySelector('#n6 [data-done]')")
                and await page.js("document.getElementById('meBadge').textContent")
                == "3",
            )
            await page.js(
                "{ const s = document.getElementById('search');"
                "s.value = 'fyi'; s.dispatchEvent(new Event('input')) }"
            )
            check(
                "search narrows the notes",
                await page.wait("document.querySelectorAll('.note').length === 1"),
            )
            await page.js(
                "{ const s = document.getElementById('search');"
                "s.value = ''; s.dispatchEvent(new Event('input')) }"
            )
            await page.js(
                "document.getElementById('fyi').checked = true;"
                "document.getElementById('text').value = 'heads up';"
                "document.getElementById('composer').requestSubmit()"
            )
            await page.wait("document.querySelectorAll('.note').length >= 7")
            dump = subprocess.run(
                CREW + ["dump", "forge"],
                env={**os.environ, **env},
                capture_output=True,
                text=True,
            ).stdout
            last = json.loads(dump)["notes"][-1]
            check(
                "the FYI tick sends an FYI note and then clears",
                last["text"] == "heads up"
                and last.get("fyi") is True
                and await page.js("!document.getElementById('fyi').checked"),
            )
            # Out of sight: the Board is on another tab, so a new note to
            # Emerson becomes a desktop notification.
            await page.js("document.querySelector('[data-tab=sessions]').click()")
            check(
                "a session card shows it is active and the agent it launched",
                await page.wait(
                    "document.getElementById('sessions').innerText.includes('Find the hooks')"
                )
                and await page.js(
                    "document.getElementById('sessions').innerText.includes('active')"
                    " && document.getElementById('sessBadge').textContent.includes('1 agent')"
                ),
            )
            crew(env, "post", "forge", "ejb-55", "need your pick", "--to", "Emerson")
            for _ in range(60):
                if log.exists() and "need your pick" in log.read_text():
                    break
                await asyncio.sleep(0.2)
            text = log.read_text() if log.exists() else ""
            check(
                "a new note to Emerson out of sight sends one desktop alert",
                f"{persona} (ejb-55) on the Board|need your pick" in text
                and "which names?" not in text,
                text,
            )
            await page.screenshot(box / "board.png")


if __name__ == "__main__":
    box = Path.home() / ".cache" / "board-check"
    shutil.rmtree(box, ignore_errors=True)
    box.mkdir(parents=True)
    try:
        asyncio.run(main(box))
    finally:
        print("\n".join(results))
        print(f"screenshot: {box / 'board.png'}")
    sys.exit(0 if results and all(r.startswith("PASS") for r in results) else 1)
