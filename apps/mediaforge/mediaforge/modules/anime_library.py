"""
Anime Library — the companion to the sorter. Points at the centralised library
the sorter produced and gives you a health view of it:

  * every series, its year, episode count, seasons, size on disk
  * MISSING EPISODE gaps inside a season (e.g. has 1-6, 8-12 → "missing 7")
  * series still holding BOTH an .mkv and an .mp4 of the same episode
  * folders with no verified year (title never matched a database)
  * a name check — re-parses each file and flags anything that no longer
    matches its folder / the SxxExx convention

Read-only by default. "Fix names" builds a rename preview that goes through the
same manifest/undo machinery as the organiser.
"""

import os
import re
from collections import defaultdict
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from ..config import open_path
from ..manifest import Manifest
from .. import ui

EXTS = {".mkv", ".mp4"}
EP_RE = re.compile(r"\bS(\d{1,2})E(\d{1,3})\b", re.I)
YEAR_RE = re.compile(r"\((\d{4})\)\s*$")


def scan_library(root):
    """root -> list of series dicts, sorted by title."""
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        files = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in EXTS]
        if not files:
            continue
        ym = YEAR_RE.search(d.name)
        seasons = defaultdict(dict)   # season -> {ep: [paths]}
        loose = []
        total = 0
        for f in files:
            try:
                total += f.stat().st_size
            except OSError:
                pass
            m = EP_RE.search(f.stem)
            if m:
                s, e = int(m.group(1)), int(m.group(2))
                seasons[s].setdefault(e, []).append(f)
            else:
                loose.append(f)
        gaps = {}
        dupe_eps = {}
        for s, eps in seasons.items():
            if eps:
                lo, hi = min(eps), max(eps)
                missing = [n for n in range(lo, hi + 1) if n not in eps]
                if missing:
                    gaps[s] = missing
                d_eps = {e: [p.suffix.lower() for p in ps] for e, ps in eps.items() if len(ps) > 1}
                if d_eps:
                    dupe_eps[s] = d_eps
        out.append({
            "title": YEAR_RE.sub("", d.name).strip(),
            "year": ym.group(1) if ym else None,
            "path": d,
            "file_count": len(files),
            "size": total,
            "seasons": {s: sorted(eps) for s, eps in seasons.items()},
            "loose": loose,
            "gaps": gaps,
            "dupe_eps": dupe_eps,
        })
    return out


def library_report(root):
    lib = scan_library(root)
    L = []
    tot_files = sum(s["file_count"] for s in lib)
    tot_gb = sum(s["size"] for s in lib) / 1e9
    L.append(f"LIBRARY: {root}")
    L.append(f"{len(lib)} series · {tot_files} files · {tot_gb:.1f} GB")
    L.append("=" * 68)
    for s in lib:
        head = f"{s['title']}" + (f" ({s['year']})" if s['year'] else "  [no year]")
        seasons = ", ".join(f"S{k:02d}:{len(v)}ep" for k, v in sorted(s["seasons"].items()))
        L.append(f"\n{head}  —  {seasons or str(len(s['loose'])) + ' files'} · {s['size']/1e9:.1f} GB")
        for sea, miss in sorted(s["gaps"].items()):
            L.append(f"    ! S{sea:02d} missing episode(s): {', '.join(map(str, miss))}")
        for sea, de in sorted(s["dupe_eps"].items()):
            for ep, exts in sorted(de.items()):
                L.append(f"    · S{sea:02d}E{ep:02d} has {' + '.join(exts)} (both kept)")
        if s["loose"]:
            L.append(f"    · {len(s['loose'])} file(s) with no SxxExx: "
                     + ", ".join(p.name for p in s["loose"][:4]) + ("…" if len(s["loose"]) > 4 else ""))
    return "\n".join(L), lib


class AnimeLibrary:
    NAME = "Anime Library"
    ICON = "📺"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.s = ctx.settings
        self.lib = []
        self._build(parent)

    def _build(self, f):
        c = ui.card(f, self.ctx, "Centralised anime library")
        ui.hint(c, self.ctx, "Health view of the folder the sorter consolidates everything into. "
                             "Read-only — nothing here moves or deletes a file unless you run Fix names.")
        self.root_entry = ui.labeled_entry(
            c, self.ctx, "Library root",
            self.s.get("library_root", str(Path.home() / "Media" / "Anime")), width=480)
        r = ui.row(c)
        ui.button(r, self.ctx, "Scan", self._scan, primary=True)
        ui.button(r, self.ctx, "Open folder",
                  lambda: open_path(self.root_entry.get().strip()))
        ui.button(r, self.ctx, "Name check", self._namecheck)
        ui.button(r, self.ctx, "Export report", self._export)

        pv = ui.card(f, self.ctx, "Report")
        self.box = ctk.CTkTextbox(pv, font=self.ctx.f_mono, height=460,
                                  fg_color=self.ctx.pal["console"], wrap="none")
        self.box.pack(fill="both", expand=True, padx=16, pady=(4, 12))

    def _set(self, text):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", text)
        self.box.configure(state="disabled")

    def _scan(self):
        root = self.root_entry.get().strip()
        self.s["library_root"] = root
        self.ctx.save_settings()

        def work():
            self.ctx.status("scanning library…")
            text, lib = library_report(root)
            self.lib = lib
            self.ctx.ui(lambda: self._set(text))
            self.ctx.log(f"Library scan: {len(lib)} series.")
        self.ctx.run_worker(work, "Library scan")

    def _namecheck(self):
        try:
            import anitopy
        except Exception:
            return messagebox.showinfo(self.NAME, "anitopy not installed.")
        root = self.root_entry.get().strip()

        def work():
            self.ctx.status("checking names…")
            lines = ["NAME CHECK — files whose parsed title differs from their folder\n"]
            n = 0
            for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
                folder_key = re.sub(r"[^a-z0-9]+", "", YEAR_RE.sub("", d.name).lower())
                for f in d.rglob("*"):
                    if f.suffix.lower() not in EXTS:
                        continue
                    if not EP_RE.search(f.stem) and "-" not in f.stem:
                        lines.append(f"  no SxxExx : {f.relative_to(root)}")
                        n += 1
                        continue
                    p = anitopy.parse(f.name) or {}
                    t = re.sub(r"[^a-z0-9]+", "", (p.get("anime_title") or "").lower())
                    if t and folder_key and t not in folder_key and folder_key not in t:
                        lines.append(f"  {p.get('anime_title','?'):<40} in  {d.name}")
                        n += 1
            lines.insert(1, f"{n} flagged\n")
            self.ctx.ui(lambda: self._set("\n".join(lines)))
            self.ctx.log(f"Name check: {n} flagged.")
        self.ctx.run_worker(work, "Name check")

    def _export(self):
        root = self.root_entry.get().strip()
        text, _ = library_report(root)
        out = Path(root) / "_library_report.txt"
        try:
            out.write_text(text, "utf-8")
            self.ctx.log(f"Wrote {out}")
            open_path(str(out))
        except Exception as e:
            self.ctx.log(f"export failed: {e}")
