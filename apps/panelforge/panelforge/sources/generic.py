"""Generic long-strip fetcher for sites without a dedicated module (e.g.
manhuaus-style readers): scroll the page collecting every large image in DOM
order, same approach as MediaForge's Manga Downloader scroll mode, rebuilt on
the shared CDP driver. Two passes: scroll-collect once, then re-check and
retry anything that failed verification.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared")
)
import forge_mangafetch as mf  # noqa: E402

SITE = "generic"

_MIN_W, _MIN_H = 300, 300  # skip icons/avatars while collecting


def matches(url: str) -> bool:
    return True  # fallback source; registry tries named sources first


def fetch_title(url: str, job) -> dict:
    """No universal chapter-list convention, so this returns the single page
    given as one "chapter" -- callers can still fetch_chapter() any URL they
    already have."""
    with mf.ChromeCDP() as chrome:
        chrome.navigate(url, settle=5.0)
        title = chrome.eval("document.title") or "Untitled"
    return {"title": title, "chapters": [{"number": 1, "title": title, "url": url}]}


def _collect_image_urls(chrome: mf.ChromeCDP) -> list[str]:
    return chrome.eval(f"""[...document.querySelectorAll('img')]
          .filter(i=>i.naturalWidth>={_MIN_W}&&i.naturalHeight>={_MIN_H})
          .map(i=>i.currentSrc||i.src)""") or []


def fetch_chapter(url: str, out_dir: Path, job) -> list[dict]:
    pages_dir = Path(out_dir) / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"

    ordered_urls: list[str] = []
    with mf.ChromeCDP() as chrome:
        chrome.navigate(url, settle=5.0)
        ua = chrome.user_agent()
        seen = set()
        stall = 0
        last_h = -1
        for _ in range(400):  # hard cap on scroll steps
            for src in _collect_image_urls(chrome):
                if src not in seen:
                    seen.add(src)
                    ordered_urls.append(src)
            h = chrome.eval("document.body.scrollHeight") or 0
            at_bottom = chrome.eval(
                "(window.innerHeight+window.scrollY)>=document.body.scrollHeight-4"
            )
            chrome.eval("window.scrollBy(0, window.innerHeight*0.85)")
            time.sleep(0.4)
            if at_bottom and h == last_h:
                stall += 1
                if stall > 2:
                    break
            else:
                stall = 0
            last_h = h

        def download_all(urls: list[str]) -> dict[int, dict]:
            out = {}
            for i, src in enumerate(urls, start=1):
                full = urljoin(base, src)
                try:
                    data = mf.download_image(full, url, ua)
                except Exception as e:
                    job.log(f"page {i}: download failed: {e}")
                    continue
                chk = mf.verify_page_bytes(data)
                if not chk.ok:
                    job.log(f"page {i}: {chk.reason}")
                    continue
                out[i] = {
                    "data": data,
                    "ext": mf.sniff_ext(data),
                    "w": chk.width,
                    "h": chk.height,
                }
            return out

        results = download_all(ordered_urls)
        missing = [i for i in range(1, len(ordered_urls) + 1) if i not in results]
        if missing:
            job.log(f"pass 2: retrying {len(missing)} page(s)")
            retry = download_all([ordered_urls[i - 1] for i in missing])
            for offset, i in enumerate(missing, start=0):
                if (offset + 1) in retry:
                    results[i] = retry[offset + 1]

    pages = []
    for idx in sorted(results):
        r = results[idx]
        fname = f"{idx:03d}.{r['ext']}"
        (pages_dir / fname).write_bytes(r["data"])
        pages.append(
            {
                "idx": idx,
                "file": f"pages/{fname}",
                "w": r["w"],
                "h": r["h"],
                "capture": "download",
            }
        )
    for i in range(1, len(ordered_urls) + 1):
        if i not in results:
            job.log(f"page {i}: MISSING after two passes")
    return pages
