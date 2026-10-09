"""Drive the real page in headless Chrome and check the files on disk afterwards.

    .venv/bin/python tests/check_ui.py

Not collected by pytest (it needs the Flatpak Chrome). It starts its own
backend on a free port, rooted in a sandbox folder on the home drive with its
own trash (XDG_DATA_HOME), so it never touches real files or the real trash.
Prints PASS/FAIL lines and exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import ALT, CTRL, SHIFT, Page, chrome_page, serve  # noqa: E402

results: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append(
        f"{'PASS' if ok else 'FAIL'} :: {name}{' :: ' + extra if extra and not ok else ''}"
    )


async def run(p: Page, port: int, box: Path) -> None:
    files = box / "files"

    await p.go(f"http://127.0.0.1:{port}/#path={files}")
    check(
        "page lists the folder",
        await p.wait("document.querySelectorAll('.item').length === 3"),
    )
    names = await p.js(
        "[...document.querySelectorAll('.item .label')].map(e => e.textContent).join(',')"
    )
    check("folders first, then files", names == "docs,photos,readme.txt", names)

    # Select readme.txt, copy, open docs, paste.
    await p.js(f"selectPath({json.dumps(str(files / 'readme.txt'))})")
    await p.key("c", "KeyC", CTRL, 67)
    await p.js(f"go({json.dumps(str(files / 'docs'))})")
    await p.wait("S.path.endsWith('/docs')")
    await p.key("v", "KeyV", CTRL, 86)
    await p.wait("S.items.some(i => i.name === 'readme.txt')")
    check(
        "Ctrl+C / Ctrl+V copies",
        (files / "docs" / "readme.txt").exists() and (files / "readme.txt").exists(),
    )

    # Paste again in the same folder makes a numbered copy.
    await p.key("v", "KeyV", CTRL, 86)
    await p.wait("S.items.some(i => i.name === 'readme (copy).txt')")
    check(
        "pasting twice makes 'readme (copy).txt'",
        (files / "docs" / "readme (copy).txt").exists(),
    )

    # F2 rename through the dialog.
    await p.js(f"selectPath({json.dumps(str(files / 'docs' / 'readme (copy).txt'))})")
    await p.key("F2", "F2", 0, 113)
    await p.wait("!document.getElementById('dialog').classList.contains('hidden')")
    await p.js("document.getElementById('dialog-input').value = 'notes.txt'")
    await p.js("document.getElementById('dialog-form').requestSubmit()")
    await p.wait("S.items.some(i => i.name === 'notes.txt')")
    check(
        "F2 renames",
        (files / "docs" / "notes.txt").exists()
        and not (files / "docs" / "readme (copy).txt").exists(),
    )

    # Delete sends to the sandbox trash, never removes.
    await p.js(f"selectPath({json.dumps(str(files / 'docs' / 'notes.txt'))})")
    await p.key("Delete", "Delete", 0, 46)
    await p.wait("!S.items.some(i => i.name === 'notes.txt')")
    in_trash = (box / "data" / "Trash" / "files" / "notes.txt").exists()
    check(
        "Delete moves to the trash",
        in_trash and not (files / "docs" / "notes.txt").exists(),
    )

    # Cut + paste moves.
    await p.js(f"selectPath({json.dumps(str(files / 'docs' / 'readme.txt'))})")
    await p.key("x", "KeyX", CTRL, 88)
    await p.js(f"go({json.dumps(str(files / 'photos'))})")
    await p.wait("S.path.endsWith('/photos')")
    await p.key("v", "KeyV", CTRL, 86)
    await p.wait("S.items.some(i => i.name === 'readme.txt')")
    check(
        "Ctrl+X / Ctrl+V moves",
        (files / "photos" / "readme.txt").exists()
        and not (files / "docs" / "readme.txt").exists(),
    )

    # New folder, then back / up navigation.
    await p.key("N", "KeyN", CTRL | SHIFT, 78)
    await p.wait("!document.getElementById('dialog').classList.contains('hidden')")
    await p.js("document.getElementById('dialog-input').value = 'Album'")
    await p.js("document.getElementById('dialog-form').requestSubmit()")
    await p.wait("S.items.some(i => i.name === 'Album')")
    check("Ctrl+Shift+N makes a folder", (files / "photos" / "Album").is_dir())
    await p.key("ArrowUp", "ArrowUp", ALT, 38)  # Alt+Up
    check("Alt+Up goes up", await p.wait(f"S.path === {json.dumps(str(files))}"))

    # Drag readme.txt (top level) onto the docs folder row: a move.
    await p.js("""(() => {
          const src = document.querySelector('.item[data-path$="/readme.txt"]');
          const dst = document.querySelector('.item[data-path$="/docs"]');
          const dt = new DataTransfer();
          src.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
          dst.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
          dst.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
        })()""")
    await p.wait("!S.items.some(i => i.name === 'readme.txt')")
    check(
        "drag onto a folder moves",
        (files / "docs" / "readme.txt").exists()
        and not (files / "readme.txt").exists(),
    )

    # Search finds nested files; hidden toggle.
    await p.js("document.getElementById('search').value = 'readme'; runSearch()")
    await p.wait("S.searching")
    found = await p.js("S.items.map(i => i.name).sort().join(',')")
    check("search finds nested", found == "readme.txt,readme.txt", found)
    await p.js("document.getElementById('search').value = ''; refresh()")
    await p.wait("!S.searching")
    await p.key("h", "KeyH", CTRL, 72)
    check(
        "Ctrl+H shows dotfiles",
        await p.wait("S.items.some(i => i.name === '.hidden')"),
    )

    # Text preview.
    await p.js(f"selectPath({json.dumps(str(files / 'docs' / 'readme.txt'))})")
    await p.js(f"go({json.dumps(str(files / 'docs'))})")
    await p.wait("S.path.endsWith('/docs')")
    await p.js(f"selectPath({json.dumps(str(files / 'docs' / 'readme.txt'))})")
    check(
        "preview shows text",
        await p.wait(
            "(document.querySelector('#preview pre')?.textContent || '').includes('hello from files')"
        ),
    )

    # Compress, extract, and restore from the trash (S17).
    docs = files / "docs"
    await p.js(f"selectPath({json.dumps(str(docs / 'readme.txt'))})")
    await p.js("archive('compress')")
    check(
        "Compress to .zip",
        await p.wait("S.items.some(i => i.name === 'readme.zip')", 10),
    )
    await p.js(f"selectPath({json.dumps(str(docs / 'readme.zip'))})")
    await p.js("itemMenu(10, 10)")
    labels = await p.js(
        "[...document.querySelectorAll('#menu button span')].map(e => e.textContent).join(',')"
    )
    await p.js("hideMenu()")
    check("an archive's menu offers Extract here", "Extract here" in labels, labels)
    await p.js("archive('extract')")
    await p.wait("S.items.some(i => i.name === 'readme' && i.dir)", 10)
    check(
        "Extract here makes a folder with the contents",
        (docs / "readme" / "readme.txt").read_text() == "hello from files\n",
    )
    # notes.txt went to the trash earlier; trash a fresh one too, so the
    # Delete below has a real target (it used to hit the selected folder).
    (docs / "notes.txt").write_text("fresh\n")
    await p.js("refresh()")
    await p.js(f"selectPath({json.dumps(str(docs / 'notes.txt'))})")
    await p.key("Delete", "Delete", 0, 46)
    await p.wait("!S.items.some(i => i.name === 'notes.txt')")
    await p.js("go(placesData.trash)")
    await p.wait("inTrash() && S.items.some(i => i.name === 'notes.txt')")
    trashed = box / "data" / "Trash" / "files" / "notes.txt"
    await p.js(f"selectPath({json.dumps(str(trashed))})")
    await p.js("itemMenu(10, 10)")
    labels = await p.js(
        "[...document.querySelectorAll('#menu button span')].map(e => e.textContent).join(',')"
    )
    await p.js("hideMenu()")
    check("the trash offers Restore", "Restore" in labels, labels)
    await p.js("restoreSel()")
    await p.wait("!S.items.some(i => i.name === 'notes.txt')")
    check(
        "Restore puts the file back where it was",
        (docs / "notes.txt").exists() and not trashed.exists(),
    )
    await p.js(f"go({json.dumps(str(docs))})")
    await p.wait("S.items.some(i => i.name === 'notes.txt')")

    # U1 sweep: two quick Ctrl+V make one copy, not two twin jobs.
    await p.js(f"selectPath({json.dumps(str(docs / 'notes.txt'))})")
    await p.key("c", "KeyC", CTRL, 67)
    await p.key("v", "KeyV", CTRL, 86)
    await p.key("v", "KeyV", CTRL, 86)
    await p.wait("S.items.some(i => i.name === 'notes (copy).txt')")
    await asyncio.sleep(1.5)
    copies = sorted(f.name for f in docs.iterdir() if f.name.startswith("notes"))
    check(
        "a quick double Ctrl+V pastes once",
        copies == ["notes (copy).txt", "notes.txt"],
        str(copies),
    )

    # U1 sweep: the newest folder asked for wins, whatever answers first.
    await p.js(
        f"go({json.dumps(str(files))}); go({json.dumps(str(files / 'photos'))}); 1"
    )
    await asyncio.sleep(1.5)
    check(
        "rapid navigation lands on the last folder",
        (await p.js("S.path")).endswith("/photos"),
        await p.js("S.path"),
    )
    await p.js(f"go({json.dumps(str(docs))})")
    await p.wait("S.items.some(i => i.name === 'notes.txt')")
    await p.screenshot(APP / "tests" / "last_ui.png")


async def drive(box: Path) -> None:
    roots = os.pathsep.join([str(box / "files"), str(box / "data")])
    env = {"FILES_ROOTS": roots, "XDG_DATA_HOME": str(box / "data")}
    with serve(APP, env) as port:
        async with chrome_page(box) as page:
            await asyncio.wait_for(run(page, port, box), 90)


def main() -> int:
    box = APP / "tests" / f".ui-{os.getpid()}"
    files = box / "files"
    (box / "data" / "Trash" / "files").mkdir(parents=True)
    (files / "docs").mkdir(parents=True)
    (files / "photos").mkdir()
    (files / "readme.txt").write_text("hello from files\n")
    (files / ".hidden").write_text("")
    try:
        asyncio.run(drive(box))
    except Exception as e:  # noqa: BLE001 - report, then clean up
        results.append(f"FAIL :: harness error :: {e!r}")
    finally:
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) or not results else 0


if __name__ == "__main__":
    sys.exit(main())
