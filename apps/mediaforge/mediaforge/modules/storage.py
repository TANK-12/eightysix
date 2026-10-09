"""
Storage Tools — the SQLite-backed file index from your fast-explorer scripts.

  * Scan a folder / drive -> cached index (survives restarts)
  * Instant search by name / size / extension
  * Largest files first
  * Find duplicate files (size bucket -> quick hash) with one-click delete of extras
  * Clean dead entries
"""

import os

import customtkinter as ctk
from tkinter import filedialog, messagebox

from ..config import open_path, DATA_ROOT
from ..index import FileIndex
from .. import ui


class StorageTools:
    NAME = "Storage Tools"
    ICON = "💾"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.idx = FileIndex()
        self.dupe_groups = []
        self.stop = False
        self._build(parent)

    def _build(self, f):
        c = ui.card(f, self.ctx, "Index")
        r = ui.row(c)
        ui.button(r, self.ctx, "Scan folder / drive…", self._scan, primary=True)
        self.min_mb = ui.labeled_entry(r, self.ctx, "min MB", "20", width=70)
        ui.button(r, self.ctx, "Clean dead entries", self._clean)
        ui.button(r, self.ctx, "Wipe index", self._wipe)
        self.stat = ctk.CTkLabel(c, text="", font=self.ctx.f_small, text_color=self.ctx.pal["text_dim"])
        self.stat.pack(anchor="w", padx=16)

        s = ui.card(f, self.ctx, "Search")
        r = ui.row(s)
        self.q = ctk.CTkEntry(r, placeholder_text="name contains…", width=280,
                              fg_color=self.ctx.pal["surface_2"])
        self.q.pack(side="left")
        self.q.bind("<KeyRelease>", lambda e: self._search())
        self.fmin = ctk.CTkEntry(r, placeholder_text="min MB", width=80, fg_color=self.ctx.pal["surface_2"])
        self.fmin.pack(side="left", padx=6)
        self.fmin.bind("<KeyRelease>", lambda e: self._search())
        self.fext = ctk.CTkEntry(r, placeholder_text=".mkv", width=80, fg_color=self.ctx.pal["surface_2"])
        self.fext.pack(side="left")
        self.fext.bind("<KeyRelease>", lambda e: self._search())
        ui.button(r, self.ctx, "Search", self._search, primary=True)
        self.results = ctk.CTkTextbox(s, font=self.ctx.f_mono, height=240, fg_color=self.ctx.pal["console"])
        self.results.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        self.results.bind("<Double-Button-1>", self._open_line)

        d = ui.card(f, self.ctx, "Duplicate finder")
        r = ui.row(d)
        ui.button(r, self.ctx, "Find duplicates", self._find_dupes, primary=True)
        ui.button(r, self.ctx, "Delete extras (keep 1 per group)", self._del_extras,
                  fg_color=self.ctx.pal["bad"], hover_color="#ff6b6b", text_color="#fff")
        self.dupe_box = ui.console(d, self.ctx, height=220)
        self._update_stat()

    def _update_stat(self):
        self.stat.configure(text=f"{self.idx.count():,} files indexed · db: {DATA_ROOT}")

    def _scan(self):
        d = filedialog.askdirectory()
        if not d:
            return
        try:
            mn = float(self.min_mb.get()) * 1024 * 1024
        except ValueError:
            mn = 0
        self.stop = False

        def work():
            self.idx.scan(d, min_bytes=mn, on_status=self.ctx.status,
                          should_stop=lambda: self.stop)
            self.ctx.ui(self._update_stat)
            self.ctx.ui(self._search)
        self.ctx.run_worker(work, "Scan")

    def _search(self, *_):
        try:
            mn = float(self.fmin.get() or 0)
        except ValueError:
            mn = 0
        rows = self.idx.search(self.q.get().strip(), mn, self.fext.get().strip())
        self.results.delete("1.0", "end")
        for name, ext, size, path in rows:
            self.results.insert("end", f"{_hs(size):>10}  {name}\n            {path}\n")
        self.results.insert("end", f"\n({len(rows)} shown)")

    def _open_line(self, e):
        try:
            line = int(self.results.index(f"@{e.x},{e.y}").split(".")[0])
            txt = self.results.get(f"{line}.0", f"{line}.end").strip()
            if os.path.sep in txt and os.path.exists(txt):
                open_path(txt)
            else:
                nxt = self.results.get(f"{line+1}.0", f"{line+1}.end").strip()
                if os.path.exists(nxt):
                    open_path(os.path.dirname(nxt))
        except Exception:
            pass

    def _clean(self):
        def work():
            n = self.idx.clean_dead()
            self.ctx.log(f"Removed {n} dead entries.")
            self.ctx.ui(self._update_stat)
        self.ctx.run_worker(work, "Clean")

    def _wipe(self):
        if messagebox.askyesno(self.NAME, "Wipe the whole file index? (files on disk are untouched)"):
            self.idx.clear()
            self._update_stat()
            self._search()

    def _find_dupes(self):
        self.stop = False

        def work():
            groups = self.idx.find_duplicates(on_status=self.ctx.status,
                                              should_stop=lambda: self.stop)
            self.dupe_groups = groups
            self.ctx.ui(lambda: self.dupe_box.delete("1.0", "end"))
            waste = 0
            for g in groups:
                sz = os.path.getsize(g[0]) if os.path.exists(g[0]) else 0
                waste += sz * (len(g) - 1)
                self.ctx.ui(lambda g=g, sz=sz: self.dupe_box.insert(
                    "end", f"\n[{_hs(sz)} ×{len(g)}]\n" + "\n".join("  " + p for p in g) + "\n"))
            self.ctx.log(f"{len(groups)} duplicate groups · ~{_hs(waste)} recoverable")
        self.ctx.run_worker(work, "Dupes")

    def _del_extras(self):
        if not self.dupe_groups:
            return
        if not messagebox.askyesno(self.NAME,
                                   f"Delete extra copies in {len(self.dupe_groups)} groups "
                                   "(keeps the first path in each)? This cannot be undone."):
            return

        def work():
            n = 0
            for g in self.dupe_groups:
                for p in g[1:]:
                    try:
                        os.remove(p)
                        n += 1
                    except OSError as e:
                        self.ctx.log(f"skip {p}: {e}")
            self.ctx.log(f"Deleted {n} duplicate files.")
            self.idx.clean_dead()
            self.dupe_groups = []
            self.ctx.ui(self._update_stat)
        self.ctx.run_worker(work, "Delete")


def _hs(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"
