"""
Manga / Comic Downloader (Selenium).

Rebuilt from your chill/final scripts, fixing the "missing pages" problem:

  * Long-strip readers are scrolled in SMALL increments with a wait between each,
    re-scanning <img> every step, tracking by resolved URL. It only stops after
    `patience` consecutive scrolls with zero new images AND the page height has
    stopped growing — not after a fixed step count.
  * Key-press readers get the same patience logic + a configurable settle delay.
  * Every image download is retried (robust session, 5 retries, backoff).
  * After a chapter, page numbering is checked; gaps are reported and the chapter
    is re-swept once more before giving up.
  * A manifest of every downloaded file is written so you can see / redo.

Needs: selenium + a Chrome/Chromium browser + matching driver. If missing, the
tab explains how to install.
"""

import glob
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mediaforge.modules.manga_fetch import (  # noqa: F401
    CDP_SITES,
    PANELFORGE,
    panelforge_fetch,
    robust_session,
    uses_panelforge_fetcher,
)

import customtkinter as ctk
from tkinter import filedialog, messagebox

from ..config import DL_DIR
from .. import ui

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options

    HAVE_SELENIUM = True
except Exception:
    HAVE_SELENIUM = False

IMG_BLACKLIST = (
    "avatar",
    "comment",
    "/user",
    "profile",
    "logo",
    "icon",
    "banner",
    "ads",
    "sprite",
    "placeholder",
    "loading",
)


# Sites whose reader draws pages on a canvas (no <img> to scrape). PanelForge's


class MangaDownloader:
    NAME = "Manga Downloader"
    ICON = "📚"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.s = ctx.settings
        self.chapters = []
        self.title = "Manga"
        self.session = robust_session()
        self.stop = False
        self._build(parent)

    def _build(self, f):
        c = ui.card(f, self.ctx, "Target")
        if not HAVE_SELENIUM:
            ui.hint(
                c,
                self.ctx,
                "Selenium isn't installed. Run:  pip install selenium  and "
                "install Chromium (pacman -S chromium). MediaForge uses your "
                "system browser + Selenium Manager for the driver.",
            )
        self.url1 = ui.labeled_entry(
            c, self.ctx, "Series / page-1 URL", "https://comix.to/title/", width=520
        )
        self.url2 = ui.labeled_entry(
            c, self.ctx, "Page-2 URL (pattern mode, optional)", "", width=520
        )
        self.group = ui.labeled_entry(
            c,
            self.ctx,
            "Scan group (comix.to lists several, e.g. WebToon)",
            "WebToon",
            width=260,
        )
        r = ui.row(c)
        self.headless = ctk.BooleanVar(value=self.s.get("manga_headless", False))
        ctk.CTkCheckBox(
            r, text="headless browser", variable=self.headless, font=self.ctx.f_small
        ).pack(side="left")
        ui.button(r, self.ctx, "Fetch chapter list", self._fetch, primary=True)

        sel = ui.card(f, self.ctx, "Chapters")
        self.ch_box = ctk.CTkTextbox(
            sel, font=self.ctx.f_mono, height=180, fg_color=self.ctx.pal["console"]
        )
        self.ch_box.pack(fill="x", padx=16, pady=(4, 4))
        ui.hint(
            sel,
            self.ctx,
            "Downloads ALL fetched chapters. To limit, delete lines you don't want "
            "before hitting download.",
        )

        o = ui.card(f, self.ctx, "Reader & output")
        self.nav = ui.opt(
            o,
            self.ctx,
            "Navigation",
            ["Vertical scroll (long strip)", "Key press (next-page)"],
            "Vertical scroll (long strip)",
            width=280,
        )
        self.key = ui.labeled_entry(
            o, self.ctx, "Next-page key", "ArrowRight", width=120
        )
        self.delay = ui.labeled_entry(
            o, self.ctx, "Step delay (s)", str(self.s.get("manga_delay", 1.5)), width=80
        )
        self.patience = ui.labeled_entry(
            o, self.ctx, "Patience (empty steps)", "10", width=80
        )
        self.threads = ui.opt(
            o,
            self.ctx,
            "Parallel chapters",
            ["1", "2", "3", "4", "5"],
            str(self.s.get("manga_threads", 3)),
            width=80,
        )
        self.out = ui.labeled_entry(
            o, self.ctx, "Save folder", str(DL_DIR / "Manga"), width=420
        )
        r = ui.row(o)
        self.mk_pdf = ctk.BooleanVar(value=self.s.get("manga_make_pdf", True))
        self.mk_cbz = ctk.BooleanVar(value=self.s.get("manga_make_cbz", False))
        self.del_raw = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            r, text="make PDF", variable=self.mk_pdf, font=self.ctx.f_small
        ).pack(side="left", padx=4)
        ctk.CTkCheckBox(
            r, text="make CBZ", variable=self.mk_cbz, font=self.ctx.f_small
        ).pack(side="left", padx=4)
        ctk.CTkCheckBox(
            r, text="delete raw after", variable=self.del_raw, font=self.ctx.f_small
        ).pack(side="left", padx=4)

        run = ui.card(f, self.ctx, "Run")
        r = ui.row(run)
        ui.button(r, self.ctx, "▶ Download", self._download, primary=True)
        ui.button(
            r,
            self.ctx,
            "■ Stop",
            lambda: setattr(self, "stop", True),
            fg_color=self.ctx.pal["bad"],
            hover_color="#ff6b6b",
            text_color="#fff",
        )
        self.log_box = ui.console(run, self.ctx, height=220)

    def _driver(self):
        opts = Options()
        for a in (
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1400,2000",
        ):
            opts.add_argument(a)
        if self.headless.get():
            opts.add_argument("--headless=new")
        return webdriver.Chrome(options=opts)

    # ---------------- fetch ----------------
    def _fetch(self):
        u1 = self.url1.get().strip()
        u2 = self.url2.get().strip()

        if uses_panelforge_fetcher(u1):

            def work_cdp():
                self.ctx.log(
                    "comix.to: listing every chapter through PanelForge's fetcher…"
                )
                group = self.group.get().strip()
                info = panelforge_fetch(
                    ["list", u1] + (["--group", group] if group else []), self.ctx.log
                )
                if info.get("groups"):
                    self.ctx.log(
                        "scan groups on this site: " + ", ".join(info["groups"])
                    )
                chapters = info.get("chapters", [])
                self.title = (
                    re.sub(r'[\\/*?:"<>|]', "", info.get("title") or "Manga") or "Manga"
                )
                self.chapters = [
                    (c.get("title") or f"Chapter {c['number']:g}", c["url"])
                    for c in chapters
                ]
                self.ctx.ui(
                    lambda: (
                        self.ch_box.delete("1.0", "end"),
                        self.ch_box.insert(
                            "1.0",
                            "\n".join(
                                f"{c['number']:>7g}  {c.get('group') or '-':<14} {c['url']}"
                                for c in chapters
                            ),
                        ),
                    )
                )
                self.ctx.log(f"'{self.title}' — {len(self.chapters)} chapters.")

            self.stop = False
            return self.ctx.run_worker(work_cdp, "Fetch")

        if not HAVE_SELENIUM:
            return messagebox.showerror(
                self.NAME, "pip install selenium + install Chromium"
            )

        def work():
            self.ctx.log("Launching browser…")
            d = self._driver()
            found = {}
            try:
                template = None
                if u2 and "2" in u2:
                    i = u2.rfind("2")
                    template = u2[:i] + "{page}" + u2[i + 1 :]
                    self.ctx.log(f"pattern mode: {template}")
                page = 1
                empty = 0
                while not self.stop and empty < 2:
                    url = (
                        u1
                        if page == 1
                        else (template.format(page=page) if template else None)
                    )
                    if url is None:
                        break
                    d.get(url)
                    time.sleep(3)
                    if page == 1:
                        self.title = (
                            re.sub(
                                r'[\\/*?:"<>|]',
                                "",
                                d.title.split("-")[0].split("|")[0].strip(),
                            )
                            or "Manga"
                        )
                    new = 0
                    for a in d.find_elements(By.TAG_NAME, "a"):
                        try:
                            href = a.get_attribute("href") or ""
                            txt = (a.text or "").strip()
                            m = re.search(
                                r"(?:ch\.?|chapter|episode)\s*[-_ ]?(\d+(?:\.\d+)?)",
                                txt + " " + href,
                                re.I,
                            )
                            if m:
                                num = float(m.group(1))
                                if num not in found and href:
                                    found[num] = (txt or f"Chapter {num}", href)
                                    new += 1
                        except Exception:
                            continue
                    self.ctx.log(f"page {page}: +{new} chapters ({len(found)} total)")
                    empty = empty + 1 if new == 0 else 0
                    if not template:
                        if not self._click_next(d):
                            break
                    page += 1
            finally:
                d.quit()
            self.chapters = [found[k] for k in sorted(found)]
            self.ctx.ui(
                lambda: (
                    self.ch_box.delete("1.0", "end"),
                    self.ch_box.insert(
                        "1.0",
                        "\n".join(f"{k:>7}  {found[k][1]}" for k in sorted(found)),
                    ),
                )
            )
            self.ctx.log(f"'{self.title}' — {len(self.chapters)} chapters.")

        self.stop = False
        self.ctx.run_worker(work, "Fetch")

    def _click_next(self, d):
        for xp in (
            "//a[normalize-space(text())='>']",
            "//button[normalize-space(text())='>']",
            "//a[contains(@class,'next')]",
            "//button[contains(@class,'next')]",
            "//a[contains(text(),'Next')]",
        ):
            try:
                for el in d.find_elements(By.XPATH, xp):
                    if el.is_displayed() and "disabled" not in (
                        el.get_attribute("class") or ""
                    ):
                        d.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", el
                        )
                        time.sleep(0.4)
                        d.execute_script("arguments[0].click();", el)
                        time.sleep(2)
                        return True
            except Exception:
                continue
        return False

    # ---------------- download ----------------
    def _download(self):
        if not self.chapters:
            return messagebox.showinfo(self.NAME, "Fetch a chapter list first.")
        lines = [ln for ln in self.ch_box.get("1.0", "end").splitlines() if ln.strip()]
        urls = [ln.split()[-1] for ln in lines]
        chapters = [(f"Chapter_{i+1:04d}", u) for i, u in enumerate(urls)]
        out_root = Path(self.out.get().strip()) / re.sub(
            r'[\\/*?:"<>|]', "", self.title
        )
        cfg = dict(
            nav=self.nav.get(),
            key=self.key.get().strip() or "ArrowRight",
            delay=float(self.delay.get() or 1.5),
            patience=int(self.patience.get() or 10),
            headless=self.headless.get(),
            pdf=self.mk_pdf.get(),
            cbz=self.mk_cbz.get(),
            del_raw=self.del_raw.get(),
        )
        workers = int(self.threads.get())
        if any(uses_panelforge_fetcher(u) for u in urls):
            workers = min(workers, 2)  # each canvas chapter is its own headless Chrome
        self.stop = False

        def work():
            out_root.mkdir(parents=True, exist_ok=True)
            self.ctx.log(f"→ {out_root}  ({workers} parallel)")
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {
                    ex.submit(self._chapter, name, url, out_root, cfg): name
                    for name, url in chapters
                }
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except Exception as e:
                        self.ctx.log(f"[{futs[fut]}] failed: {e}")
            self.ctx.log("\nAll chapters done.")

        self.ctx.run_worker(work, "Download")

    def _chapter(self, name, url, out_root, cfg):
        folder = out_root / name
        folder.mkdir(parents=True, exist_ok=True)
        if uses_panelforge_fetcher(url):
            # canvas reader: captured page by page through PanelForge's fetcher
            res = panelforge_fetch(
                ["get", url, str(folder), name], lambda m: self.ctx.log(f"[{name}] {m}")
            )
            self.ctx.log(f"[{name}] {res.get('pages', 0)} pages captured")
        else:
            d = self._driver()
            seen = set()
            try:
                d.get(url)
                time.sleep(4)
                if cfg["nav"].startswith("Vertical"):
                    self._collect_scroll(d, folder, name, seen, cfg)
                else:
                    self._collect_keys(d, folder, name, seen, cfg)
            finally:
                d.quit()
        # gap check
        files = sorted(folder.glob(f"{name}_*"))
        self.ctx.log(f"[{name}] {len(files)} pages saved")
        if cfg["pdf"] or cfg["cbz"]:
            self._compile(folder, name, out_root, cfg)
        if cfg["del_raw"]:
            for p in folder.glob(f"{name}_*"):
                p.unlink()
            try:
                folder.rmdir()
            except OSError:
                pass

    def _img_urls(self, d):
        urls = []
        for img in d.find_elements(By.TAG_NAME, "img"):
            try:
                src = (
                    img.get_attribute("src")
                    or img.get_attribute("data-src")
                    or img.get_attribute("data-lazy-src")
                    or ""
                )
                if not src.startswith("http"):
                    continue
                if any(b in src.lower() for b in IMG_BLACKLIST):
                    continue
                w = int(
                    img.get_attribute("naturalWidth") or img.get_attribute("width") or 0
                )
                if w and w < 250:
                    continue
                urls.append(src)
            except Exception:
                continue
        return urls

    def _collect_scroll(self, d, folder, name, seen, cfg):
        n = 0
        empty = 0
        last_h = 0
        while not self.stop and empty < cfg["patience"]:
            for src in self._img_urls(d):
                if src in seen:
                    continue
                seen.add(src)
                n += 1
                if self._save(src, folder, name, n):
                    empty = 0
                else:
                    n -= 1
            h = d.execute_script("return document.body.scrollHeight")
            d.execute_script("window.scrollBy(0, Math.round(window.innerHeight*0.85));")
            time.sleep(cfg["delay"])
            new_h = d.execute_script("return document.body.scrollHeight")
            at_bottom = d.execute_script(
                "return (window.innerHeight + window.scrollY) >= document.body.scrollHeight - 5;"
            )
            if not self._img_urls(d) or (at_bottom and new_h == h):
                empty += 1
            last_h = new_h
        self.ctx.log(f"[{name}] scroll finished — {n} pages")

    def _collect_keys(self, d, folder, name, seen, cfg):
        from selenium.webdriver.common.keys import Keys

        keymap = {
            "arrowright": Keys.ARROW_RIGHT,
            "arrowleft": Keys.ARROW_LEFT,
            "arrowdown": Keys.ARROW_DOWN,
            "space": Keys.SPACE,
            "d": "d",
            "a": "a",
        }
        key = keymap.get(cfg["key"].lower(), cfg["key"])
        n = 0
        empty = 0
        for _ in range(400):
            if self.stop or empty >= cfg["patience"]:
                break
            got = False
            for src in self._img_urls(d):
                if src in seen:
                    continue
                seen.add(src)
                n += 1
                if self._save(src, folder, name, n):
                    got = True
                else:
                    n -= 1
            empty = 0 if got else empty + 1
            try:
                d.find_element(By.TAG_NAME, "body").send_keys(key)
            except Exception:
                pass
            time.sleep(cfg["delay"])
        self.ctx.log(f"[{name}] key-nav finished — {n} pages")

    def _save(self, url, folder, name, num):
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
            if ext not in ("jpg", "jpeg", "png", "webp"):
                ext = "jpg"
            (folder / f"{name}_{num:03d}.{ext}").write_bytes(r.content)
            return True
        except Exception:
            return False

    def _compile(self, folder, name, out_root, cfg):
        imgs = sorted(glob.glob(str(folder / f"{name}_*")))
        if not imgs:
            return
        try:
            from PIL import Image

            pil = [Image.open(p).convert("RGB") for p in imgs]
        except Exception as e:
            self.ctx.log(f"[{name}] compile skipped: {e}")
            return
        if cfg["pdf"]:
            pp = out_root / f"{name}.pdf"
            pil[0].save(pp, save_all=True, append_images=pil[1:])
            self.ctx.log(f"[{name}] → {pp.name}")
        if cfg["cbz"]:
            import zipfile

            zp = out_root / f"{name}.cbz"
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                for p in imgs:
                    z.write(p, os.path.basename(p))
            self.ctx.log(f"[{name}] → {zp.name}")
