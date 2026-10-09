"""comix.to fetcher.

Chapter list: scraped from the title page's own paginated "Chapters" list
(``section.mpage__chapters``), clicking through ``.npager__num`` pages -- the
site's JSON API (``/api/v1/manga/...``) returns its payloads encrypted
client-side, so the rendered DOM is the reliable source, exactly the way the
in-page JS itself gets the data.

Chapter pages: the reader lists one ``.rpage-page[data-page=N]`` slot per
page. A slot holds either a plain ``<img>`` (downloaded directly, with a
Referer header) or a ``<canvas>`` (the site's scramble/anti-scrape path --
this is what CONTRACTS.md's "scramble flag s==1" means in practice here: the
reader decides per page whether to draw through canvas, and canvas presence
*is* that flag from the client's point of view). Canvas pages are captured
with a clipped, stability-checked screenshot -- see
``forge_mangafetch.capture_canvas_stable`` and HANDOFF.md for why
``canvas.toDataURL()`` cannot be used here.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared")
)
import forge_mangafetch as mf  # noqa: E402

SITE = "comix.to"
_CHAP_RE = re.compile(r"-chapter-([0-9]+(?:\.[0-9]+)?)$")


def matches(url: str) -> bool:
    return "comix.to" in urlparse(url).netloc


def _num_from_href(href: str) -> Optional[float]:
    m = _CHAP_RE.search(href)
    return float(m.group(1)) if m else None


def fetch_title(url: str, job) -> dict:
    with mf.ChromeCDP() as chrome:
        chrome.navigate(url, settle=6.0)
        title = (
            chrome.eval(
                "(document.querySelector('h1')||{}).textContent && "
                "document.querySelector('h1').textContent.trim()"
            )
            or "Untitled"
        )
        chapters: dict[tuple[float, str], dict] = {}
        seen_pages = 0
        # The list is paged with ?page=N. Clicking the pager's "Next" button
        # is not reliable: on some pages the site renders the pager without
        # it (only "First", "Previous" and a window of numbers), which ended
        # every walk at page 8 of 10 and never listed chapters 1-21. Loading
        # each numbered page directly until one adds nothing new is.
        base = url.split("?")[0]
        for page in range(1, 200):
            job.check() if hasattr(job, "check") else None
            if page > 1:
                chrome.navigate(f"{base}?page={page}", settle=2.5)
            # one row per chapter *and* scan group: the same chapter is
            # listed once per group (Bad Born Blood: "Asura Scans" and
            # "WebToon"); keeping only the first lost the one Emerson wanted
            rows = (
                chrome.eval(
                    "[...document.querySelectorAll('li.mchap-item')].map(li=>{"
                    "const a=li.querySelector('a.mchap-row__primary')||li.querySelector('a[href*=chapter]');"
                    "return a?{href:a.getAttribute('href'),"
                    "ch:(li.querySelector('.mchap-row__ch')||a).textContent.trim().slice(0,40),"
                    "group:(li.querySelector('a.mchap-row__group')||{textContent:''}).textContent.trim().slice(0,60)}:null"
                    "}).filter(Boolean)"
                )
                or []
            )
            new = 0
            for r in rows:
                num = _num_from_href(r["href"])
                if num is None:
                    continue
                group = r.get("group") or ""
                key = (num, group)
                if key in chapters:
                    continue
                chapters[key] = {
                    "number": num,
                    "title": r["ch"][:40] + (f" ({group})" if group else ""),
                    "group": group,
                    "url": (
                        "https://comix.to" + r["href"]
                        if r["href"].startswith("/")
                        else r["href"]
                    ),
                }
                new += 1
            seen_pages += 1
            if new == 0:
                break
        (
            job.log(f"found {len(chapters)} chapters over {seen_pages} list page(s)")
            if hasattr(job, "log")
            else None
        )
    ordered = [chapters[k] for k in sorted(chapters)]
    groups = sorted({c["group"] for c in ordered if c["group"]})
    return {"title": title, "chapters": ordered, "groups": groups}


def fetch_chapter(url: str, out_dir: Path, job) -> list[dict]:
    pages_dir = Path(out_dir) / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, dict] = {}

    with mf.ChromeCDP() as chrome:
        chrome.navigate(url, settle=8.0)
        chrome.eval(
            "(()=>{const st=document.createElement('style');"
            "st.textContent='body *{visibility:hidden !important} "
            "canvas.rpage-page__img, img.rpage-page__img{visibility:visible !important}';"
            "document.head.appendChild(st)})()"
        )
        total = chrome.eval("document.querySelectorAll('.rpage-page').length") or 0
        job.log(f"comix: {total} page slots")
        ua = chrome.user_agent()

        def fetch_one(idx: int) -> Optional[dict]:
            chrome.eval(
                f"document.querySelector('.rpage-page[data-page=\"{idx}\"]')"
                f".scrollIntoView({{block:'center'}})"
            )
            info = None
            for _ in range(40):
                info = chrome.eval(
                    f"""(()=>{{const p=document.querySelector('.rpage-page[data-page="{idx}"]');
                      const c=p&&p.querySelector('canvas.rpage-page__img');
                      const i=p&&p.querySelector('img.rpage-page__img');
                      if(c&&c.width>0&&!p.classList.contains('is-loading')){{
                        const r=c.getBoundingClientRect();
                        return {{kind:'canvas',x:r.left+scrollX,y:r.top+scrollY,w:r.width,h:r.height,cw:c.width,ch:c.height}};
                      }}
                      if(i&&i.complete&&i.naturalWidth>0) return {{kind:'img',src:i.currentSrc||i.src,w:i.naturalWidth,h:i.naturalHeight}};
                      return null}})()"""
                )
                if info:
                    break
                time.sleep(0.25)
            if not info:
                return None
            if info["kind"] == "canvas":
                rect_js = (
                    f"document.querySelector('.rpage-page[data-page=\"{idx}\"]')"
                    f".scrollIntoView({{block:'start'}});"
                    f"(()=>{{const c=document.querySelector('.rpage-page[data-page=\"{idx}\"] canvas');"
                    "if(!c)return null;const b=c.getBoundingClientRect();"
                    "return {x:b.left+scrollX,y:b.top+scrollY,w:b.width,h:b.height,cw:c.width}})()"
                )
                data = mf.capture_canvas_stable(chrome, rect_js)
                if data is None:
                    return None
                return {"data": data, "ext": "png", "capture": "canvas-screenshot"}
            try:
                data = mf.download_image(info["src"], "https://comix.to/", ua)
            except Exception as e:
                job.log(f"page {idx}: download failed: {e}")
                return None
            return {"data": data, "ext": mf.sniff_ext(data), "capture": "download"}

        # two full passes: first pass tries every page, second pass retries
        # only what's missing or failed verification.
        pending = list(range(1, total + 1))
        for pass_no in (1, 2):
            still = []
            for idx in pending:
                job.progress((pass_no - 1) * 0.5 + 0.5 * idx / max(1, total))
                got = fetch_one(idx)
                if got is None:
                    still.append(idx)
                    continue
                chk = mf.verify_page_bytes(got["data"])
                if not chk.ok:
                    job.log(f"page {idx} pass {pass_no}: {chk.reason}, will retry")
                    still.append(idx)
                    continue
                results[idx] = {
                    "idx": idx,
                    "data": got["data"],
                    "ext": got["ext"],
                    "w": chk.width,
                    "h": chk.height,
                    "capture": got["capture"],
                }
            pending = still
            if not pending:
                break
            job.log(f"pass {pass_no} done, {len(pending)} page(s) need a retry")

    for idx in pending:
        job.log(f"page {idx}: MISSING after two passes")

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
                "capture": r["capture"],
            }
        )
    return pages
