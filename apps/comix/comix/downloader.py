"""The download worker: takes chapters from the queue and makes CBZ files.

Per chapter:
  1. open the reader, note how many pages it has;
  2. pass over every page not yet saved: capture, check it decodes, is not
     blank and not truncated, save it to the chapter's work folder;
  3. pages still missing? wait (longer each pass), reload the reader, pass
     again, up to ``page_passes`` times;
  4. every page saved -> build ``Chapter_NNNN.cbz`` and delete the work folder;
     otherwise leave the good pages on disk and put the chapter back in the
     queue for later (5 min, 10, 20 ... up to 6 h), "failed" after
     ``chapter_attempts`` tries.

Pages already saved are never fetched again, so a crash, a stop or a restart
loses at most the page being fetched.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape

from comix import settings as settings_mod
from comix import sources
from comix.session import read_cookies
from comix.store import Store

import forge_mangafetch as mf

Log = Callable[[str], None]


def safe_name(text: str, limit: int = 80) -> str:
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", text).strip().strip(".")
    return re.sub(r"\s+", " ", text)[:limit] or "Untitled"


def chapter_stem(number: float) -> str:
    whole = int(number)
    rest = f"{number:g}"[len(str(whole)) :] if number != whole else ""
    return f"Chapter_{whole:04d}{rest}"


def cbz_path(root: Path, series: str, group: str, number: float) -> Path:
    return (
        root
        / safe_name(series)
        / safe_name(group or "Unknown group")
        / f"{chapter_stem(number)}.cbz"
    )


def retry_delay(attempts: int) -> float:
    """Seconds before a chapter that is still missing pages is tried again."""
    return float(min(6 * 3600, 300 * 2 ** max(0, attempts - 1)))


def pass_wait(pass_no: int) -> float:
    """Pause before re-reading a chapter's missing pages (the site may be busy)."""
    return float(min(60, 5 * 2 ** (pass_no - 1)))


def build_cbz(
    dest: Path, pages: list[Path], series: str, group: str, number: float
) -> None:
    """Write the CBZ atomically: a half-written file never looks finished."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    info = (
        '<?xml version="1.0" encoding="utf-8"?>\n<ComicInfo>'
        f"<Series>{escape(series)}</Series><Number>{number:g}</Number>"
        f"<Translator>{escape(group)}</Translator><PageCount>{len(pages)}</PageCount>"
        "<Manga>YesAndRightToLeft</Manga></ComicInfo>\n"
    )
    tmp = dest.with_suffix(".cbz.part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        for n, page in enumerate(pages, 1):
            z.write(page, f"{n:04d}{page.suffix}")
        z.writestr("ComicInfo.xml", info)
    tmp.replace(dest)


BROWSER_MARK = (
    "comix-fetch-"  # + instance tag, in every worker Chrome's --user-data-dir
)


def stray_browsers(mark: str, proc: Path = Path("/proc")) -> list[int]:
    """Processes still using one of Comix's own Chrome profiles.

    A crash or a hard kill of the backend leaves its headless Chrome running;
    ``mark`` carries this backend's instance tag, so a second Comix (a test
    copy, say) never stops the browsers of the first.
    """
    found = []
    for entry in proc.glob("[0-9]*"):
        try:
            cmd = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(a.startswith(b"--user-data-dir=") and mark.encode() in a for a in cmd):
            found.append(int(entry.name))
    return [pid for pid in found if pid != os.getpid()]


def stop_stray_browsers(mark: str, proc: Path = Path("/proc"), kill=os.kill) -> int:
    pids = stray_browsers(mark, proc)
    for pid in pids:
        try:
            kill(pid, signal.SIGTERM)
        except OSError:
            pass
    return len(pids)


class Worker:
    """Background threads that drain the queue. ``reader_factory`` is the source's
    ``reader`` (tests pass a fake), ``sleep`` is swappable so tests do not wait."""

    def __init__(
        self,
        store: Store,
        log: Log,
        reader_factory: Callable | None = None,
        cookie_reader: Callable[[str], list[dict]] = read_cookies,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.store = store
        self.log = log
        self.reader_factory = reader_factory
        self.cookie_reader = cookie_reader
        self.sleep = sleep
        self.paused = threading.Event()
        self.stopping = threading.Event()
        self.current: dict[int, dict] = {}
        self._threads: list[threading.Thread] = []
        # one tag per database, so each Comix instance owns its browser profiles
        self.tag = hashlib.sha1(str(Path(store.path).resolve()).encode()).hexdigest()[
            :8
        ]
        self.mark = f"{BROWSER_MARK}{self.tag}-"

    # --- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        stale = stop_stray_browsers(self.mark)
        if stale:
            self.log(f"closed {stale} headless browser process(es) left by a crash")
        requeued = self.store.reset_running()
        if requeued:
            self.log(f"resumed {requeued} chapter(s) that were mid-download")
        self._threads = [
            threading.Thread(target=self._loop, args=(slot,), daemon=True)
            for slot in range(2)
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self.stopping.set()
        stop_stray_browsers(self.mark)

    def _loop(self, slot: int) -> None:
        while not self.stopping.is_set():
            conf = settings_mod.load()
            if self.paused.is_set() or slot >= conf["chapters_at_once"]:
                self.stopping.wait(2)
                continue
            ch = self.store.claim_next()
            if ch is None:
                self.stopping.wait(3)
                continue
            try:
                self.run_chapter(ch, conf, slot)
            except Exception as e:  # a crash in one chapter must not kill the worker
                self.log(f"{ch['series_title']} ch {ch['number']:g}: {e}")
                self.store.give_up_for_now(
                    ch["id"],
                    str(e)[:300],
                    time.time() + retry_delay(ch["attempts"] + 1),
                    conf["chapter_attempts"],
                )
            finally:
                self.current.pop(slot, None)
            self.stopping.wait(conf["pause_seconds"])

    # --- one chapter ------------------------------------------------------------

    def run_chapter(self, ch: dict, conf: dict, slot: int = 0) -> str:
        """Download one claimed chapter; returns its new state."""
        cid = ch["id"]
        name = f"{ch['series_title']} ch {ch['number']:g} ({ch['grp'] or 'no group'})"
        root = Path(conf["download_dir"]).expanduser()
        work = root / ".work" / str(cid)
        work.mkdir(parents=True, exist_ok=True)
        src_name = sources.find_for_url(ch["url"])
        if src_name is None:
            raise ValueError(f"no source handles {ch['url']}")
        src = sources.get(src_name)
        factory = self.reader_factory or src.reader
        cookies = self.cookie_reader(src.DOMAIN)

        saved = {
            p["idx"]: Path(p["file"])
            for p in self.store.pages(cid)
            if p["state"] == "ok" and Path(p["file"]).exists()
        }
        with factory(cookies, f"{self.tag}-{slot}") as reader:
            total = reader.load(ch["url"])
            if total <= 0:
                total = reader.reload()
            if total <= 0:
                raise RuntimeError("the reader showed no pages (chapter removed?)")
            self.store.set_total(cid, total)
            self.current[slot] = {"chapter": cid, "name": name, "total": total}
            for pass_no in range(1, conf["page_passes"] + 1):
                missing = [i for i in range(1, total + 1) if i not in saved]
                if not missing:
                    break
                if pass_no > 1:
                    self.log(f"{name}: {len(missing)} page(s) missing, pass {pass_no}")
                    self.sleep(pass_wait(pass_no - 1))
                    reader.reload()
                for idx in missing:
                    if self.stopping.is_set():
                        break
                    self.current[slot]["page"] = idx
                    data, ext, why = reader.capture(idx)
                    if data is not None:
                        check = mf.verify_page_bytes(data)
                        if not check.ok:
                            data, why = None, check.reason
                    if data is None:
                        self.store.page_failed(cid, idx, why)
                        continue
                    f = work / f"{idx:04d}.{ext}"
                    f.write_bytes(data)
                    self.store.page_ok(cid, idx, str(f))
                    saved[idx] = f
                if self.stopping.is_set():
                    break

        missing = [i for i in range(1, total + 1) if i not in saved]
        if missing:
            state = self.store.give_up_for_now(
                cid,
                f"{len(missing)} of {total} pages still missing",
                time.time() + retry_delay(ch["attempts"] + 1),
                conf["chapter_attempts"],
            )
            self.log(f"{name}: {len(missing)} page(s) still missing, {state}")
            return state
        dest = cbz_path(root, ch["series_title"], ch["grp"], ch["number"])
        build_cbz(
            dest,
            [saved[i] for i in range(1, total + 1)],
            ch["series_title"],
            ch["grp"],
            ch["number"],
        )
        self.store.finish(cid, str(dest))
        shutil.rmtree(work, ignore_errors=True)
        self.log(f"{name}: saved {total} pages")
        return "done"
