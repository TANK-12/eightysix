"""Command-line front for PanelForge's site fetchers, for other Forge apps.

    .venv/bin/python tools/fetch_cli.py list <title_url> [--group NAME | --all]
        -> one JSON line: {"title": ..., "groups": [...], "chapters":
           [{"number", "title", "group", "url"}]}, one entry per chapter
           number (the named scan group where the chapter has it); with
           --all, every row the site lists, one per chapter *and* group, so
           the caller can show who scanned what and let the user choose
    .venv/bin/python tools/fetch_cli.py get <chapter_url> <out_dir> <name>
        -> saves the chapter's pages as <out_dir>/<name>_001.png ... and
           prints LOG lines, then one JSON line {"pages": N, "problems": [...]}

MediaForge's manga downloader calls this for comix.to, whose reader draws
pages on a canvas that a plain page scrape never sees; PanelForge's fetcher
captures them through headless Chrome. One engine, used from both apps.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from panelforge.sources import find_for_url, get as get_source  # noqa: E402


class _Job:
    def log(self, msg: str) -> None:
        print("LOG " + msg, flush=True)

    def progress(self, frac: float) -> None:
        print(f"PROGRESS {frac:.3f}", flush=True)

    def check(self) -> None:
        pass


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, url = argv[0], argv[1]
    group = argv[argv.index("--group") + 1] if "--group" in argv else None
    src = get_source(find_for_url(url) or "generic")
    job = _Job()
    if cmd == "list":
        from panelforge.library.fetch import pick_group

        info = src.fetch_title(url, job)
        if not info.get("chapters"):
            job.log(
                f"no chapters at {url} (title {info.get('title')!r}): use the "
                "title page's link, like https://comix.to/title/3nlg-bad-born-blood"
            )
        groups = info.get("groups") or []
        if groups:
            job.log(
                "scan groups: "
                + ", ".join(groups)
                + (f" (using {group})" if group else "")
            )
        chapters = (
            info["chapters"]
            if "--all" in argv
            else pick_group(info["chapters"], group, job)
        )
        print(
            json.dumps({"title": info["title"], "groups": groups, "chapters": chapters})
        )
        return 0
    if cmd == "get":
        out_dir, name = Path(argv[2]), argv[3]
        work = out_dir / ".panelforge-fetch"
        pages = src.fetch_chapter(url, work, job)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for p in sorted(pages, key=lambda p: p["idx"]):
            f = work / "pages" / Path(p["file"]).name
            if f.exists():
                shutil.move(str(f), str(out_dir / f"{name}_{p['idx']:03d}{f.suffix}"))
                saved += 1
        shutil.rmtree(work, ignore_errors=True)
        print(json.dumps({"pages": saved}))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
