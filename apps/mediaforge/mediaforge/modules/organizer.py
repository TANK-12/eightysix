"""
Library Organiser — sort a messy folder of anime / TV / movie files into a clean
Plex/Jellyfin-style tree, with a full undo.

Flow:
  1. Scan a source folder (video files).
  2. Parse each filename with anitopy (title, season, episode, year, resolution…).
  3. Look up the canonical title + year from AniList / Jikan / TMDB.
  4. Build a proposed path from your naming pattern.
  5. Show a PREVIEW table (current → proposed), editable, per-row on/off.
  6. Apply — moves/copies/hardlinks, writing a MOVE MANIFEST.
  7. History tab — revert any past run (moves everything back).

Safety: never deletes. Hash-checks so a file already in the right place / an
exact duplicate is skipped, not clobbered. Conflicts skipped or parked in
_conflicts/ per your setting.
"""

import os
import re
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    import anitopy
except Exception:
    anitopy = None

from ..config import VIDEO_EXTS
from ..manifest import Manifest, apply_op, quick_hash, list_manifests, revert
from .. import metadata
from .. import ui


def _clean(s):
    s = re.sub(r'[<>:"/\\|?*]', "", s or "").strip()
    return re.sub(r"\s+", " ", s)


def parse_name(path):
    fn = os.path.basename(path)
    d = {}
    if anitopy:
        try:
            d = anitopy.parse(fn) or {}
        except Exception:
            d = {}
    title = d.get("anime_title") or os.path.splitext(fn)[0]
    ep = d.get("episode_number")
    if isinstance(ep, list):
        ep = ep[0]
    season = d.get("anime_season")
    if isinstance(season, list):
        season = season[0]
    year = d.get("anime_year")
    res = d.get("video_resolution")
    # fallbacks from the raw name
    if ep is None:
        m = re.search(r"(?:e|ep|episode|\b)[ _.]*(\d{1,4})(?:v\d)?\b", fn, re.I)
        if m and not re.search(r"(19|20)\d\d", m.group(0)):
            ep = m.group(1)
    if season is None:
        m = re.search(r"\bs(?:eason)?[ _.]*(\d{1,2})\b", fn, re.I)
        season = m.group(1) if m else None
    try:
        ep = int(ep) if ep is not None else None
    except (TypeError, ValueError):
        ep = None
    try:
        season = int(season) if season is not None else None
    except (TypeError, ValueError):
        season = None
    is_movie = ep is None and (d.get("anime_type", "").lower() in ("movie",) or
                               re.search(r"\bmovie\b", fn, re.I) is not None)
    return {"raw_title": _clean(title), "season": season, "episode": ep,
            "year": int(year) if str(year).isdigit() else None,
            "resolution": res, "is_movie": is_movie}


def build_target(meta_title, year, season, episode, resolution, is_movie, pattern, root):
    title = _clean(meta_title)
    season = season or 1
    fields = {"title": title, "year": year or "", "season": season,
              "episode": episode or 0, "resolution": resolution or ""}
    if is_movie or episode is None:
        rel = f"{title}" + (f" ({year})" if year else "") + f"/{title}" + (f" ({year})" if year else "")
    else:
        try:
            rel = pattern.format(**fields)
        except Exception:
            rel = f"{title}/Season {season:02d}/{title} - S{season:02d}E{episode or 0:02d}"
    return rel


class Organizer:
    NAME = "Library Organiser"
    ICON = "🗂️"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.s = ctx.settings
        self.rows = []          # list of dicts: src, target, on, note
        self.src_dir = None
        self._build(parent)

    def _build(self, f):
        self.tabs = ctk.CTkTabview(f, fg_color=self.ctx.pal["surface"])
        self.tabs.pack(fill="both", expand=True, padx=14, pady=10)
        self.tabs.add("Organise")
        self.tabs.add("History / Revert")
        self._build_org(self.tabs.tab("Organise"))
        self._build_history(self.tabs.tab("History / Revert"))

    # ---------------- Organise tab ----------------
    def _build_org(self, f):
        c = ui.card(f, self.ctx, "Source & rules")
        if anitopy is None:
            ui.hint(c, self.ctx, "anitopy isn't installed — filename parsing will be crude. "
                                 "Run:  pip install anitopy")
        r = ui.row(c)
        ui.button(r, self.ctx, "Choose messy folder…", self._pick_src, primary=True)
        self.src_lbl = ctk.CTkLabel(r, text="(none)", font=self.ctx.f_small,
                                    text_color=self.ctx.pal["text_dim"])
        self.src_lbl.pack(side="left", padx=8)
        self.lib_entry = ui.labeled_entry(c, self.ctx, "Library root",
                                          self.s.get("library_root", str(Path.home() / "Media")), width=460)
        self.pattern_entry = ui.labeled_entry(c, self.ctx, "Naming pattern",
                                              self.s.get("naming_pattern"), width=460)
        self.provider = ui.opt(c, self.ctx, "Metadata",
                               ["anilist", "jikan", "tmdb", "none"], self.s.get("metadata_provider", "anilist"))
        self.action = ui.opt(c, self.ctx, "Action", ["move", "copy", "hardlink"],
                             self.s.get("organise_action", "move"))
        self.conflict = ui.opt(c, self.ctx, "On name clash",
                               ["skip", "number", "conflicts_folder", "duplicates_folder"],
                               self.s.get("on_conflict", "skip"))
        ui.hint(c, self.ctx, "duplicates_folder — when the target already exists (identical "
                             "content or a competing encode), the source is MOVED to "
                             "<library>/_DUPLICATES/<original path> rather than left behind "
                             "or deleted. Clear that folder by hand once you've checked it.")
        self.hashchk = ctk.BooleanVar(value=self.s.get("hash_check", True))
        ctk.CTkCheckBox(ui.row(c), text="hash-check (skip files already sorted / exact dupes)",
                        variable=self.hashchk, font=self.ctx.f_small).pack(side="left")
        r = ui.row(c)
        ui.button(r, self.ctx, "1 · Build preview", self._preview, primary=True)
        ui.button(r, self.ctx, "2 · Apply", self._apply)
        ui.button(r, self.ctx, "Select all / none", self._toggle_all)

        pv = ui.card(f, self.ctx, "Preview  (double-click a row to edit its target)")
        self.tree_box = ctk.CTkTextbox(pv, font=self.ctx.f_mono, height=320,
                                       fg_color=self.ctx.pal["console"])
        self.tree_box.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        self.tree_box.bind("<Double-Button-1>", self._edit_row)
        self.count_lbl = ctk.CTkLabel(pv, text="", font=self.ctx.f_small,
                                      text_color=self.ctx.pal["text_dim"])
        self.count_lbl.pack(anchor="w", padx=16, pady=(0, 10))

    def _pick_src(self):
        d = filedialog.askdirectory()
        if d:
            self.src_dir = d
            self.src_lbl.configure(text=d)

    def _toggle_all(self):
        anyon = any(r["on"] for r in self.rows)
        for r in self.rows:
            r["on"] = not anyon
        self._render()

    def _sync(self):
        self.s["library_root"] = self.lib_entry.get().strip()
        self.s["naming_pattern"] = self.pattern_entry.get().strip()
        self.s["metadata_provider"] = self.provider.get()
        self.s["organise_action"] = self.action.get()
        self.s["on_conflict"] = self.conflict.get()
        self.s["hash_check"] = self.hashchk.get()
        self.ctx.save_settings()

    def _preview(self):
        if not self.src_dir:
            return messagebox.showinfo(self.NAME, "Choose a source folder first.")
        self._sync()
        root = self.lib_entry.get().strip()
        pattern = self.pattern_entry.get().strip()
        provider = self.provider.get()
        tmdb_key = self.s.get("tmdb_key", "")
        src_dir = self.src_dir

        def work():
            vids = [str(p) for p in Path(src_dir).rglob("*")
                    if p.suffix.lower() in VIDEO_EXTS and p.is_file()]
            self.ctx.log(f"Found {len(vids)} video files. Parsing + looking up metadata…")
            rows = []
            meta_cache = {}
            for i, src in enumerate(vids, 1):
                p = parse_name(src)
                mt = p["raw_title"]
                if provider != "none":
                    ck = (mt.lower(), p["is_movie"])
                    if ck not in meta_cache:
                        meta_cache[ck] = metadata.lookup(mt, provider, tmdb_key, p["is_movie"])
                    m = meta_cache[ck]
                else:
                    m = None
                title = (m["title"] if m else mt)
                year = (m["year"] if m and m["year"] else p["year"])
                rel = build_target(title, year, p["season"], p["episode"],
                                   p["resolution"], p["is_movie"], pattern, root)
                target = str(Path(root) / (rel + Path(src).suffix))
                note = ""
                if os.path.abspath(src) == os.path.abspath(target):
                    note = "already in place"
                rows.append({"src": src, "target": target, "on": not note,
                             "note": note or (m["source"] if m else "no metadata")})
                if i % 15 == 0:
                    self.ctx.status(f"parsed {i}/{len(vids)}")
            self.rows = rows
            self.ctx.ui(self._render)
            self.ctx.log("Preview ready. Review, then Apply.")
        self.ctx.run_worker(work, "Preview")

    def _render(self):
        self.tree_box.configure(state="normal")
        self.tree_box.delete("1.0", "end")
        root = self.lib_entry.get().strip()
        for i, r in enumerate(self.rows):
            mark = "[x]" if r["on"] else "[ ]"
            tgt = r["target"]
            try:
                tgt = os.path.relpath(tgt, root)
            except ValueError:
                pass
            self.tree_box.insert("end", f"{mark} {i:>3}  {os.path.basename(r['src'])}\n"
                                        f"        → {tgt}   ({r['note']})\n")
        self.tree_box.configure(state="disabled")
        on = sum(1 for r in self.rows if r["on"])
        self.count_lbl.configure(text=f"{on} of {len(self.rows)} selected · action = {self.action.get()}")

    def _edit_row(self, event):
        try:
            line = int(self.tree_box.index(f"@{event.x},{event.y}").split(".")[0])
        except Exception:
            return
        idx = (line - 1) // 2
        if not (0 <= idx < len(self.rows)):
            return
        r = self.rows[idx]
        dlg = ctk.CTkInputDialog(text=f"Target for {os.path.basename(r['src'])}:", title="Edit target")
        val = dlg.get_input()
        if val:
            r["target"] = val if os.path.isabs(val) else str(Path(self.lib_entry.get().strip()) / val)
            r["on"] = True
            self._render()

    def _apply(self):
        picked = [r for r in self.rows if r["on"]]
        if not picked:
            return messagebox.showinfo(self.NAME, "Nothing selected. Build a preview first.")
        if not messagebox.askyesno(self.NAME,
                                   f"{self.action.get()} {len(picked)} files into\n"
                                   f"{self.lib_entry.get().strip()} ?\n\nA manifest is saved so you "
                                   "can revert."):
            return
        self._sync()
        op = self.action.get()
        conflict = self.conflict.get()
        hashchk = self.hashchk.get()
        root = self.lib_entry.get().strip()

        src_root = self.src_dir

        def _dup_target(src):
            """Where a clashing source file is parked: <root>/_DUPLICATES/<its
            path relative to the messy source folder>, so you can see where each
            came from. Preferred over leaving a second copy in the source tree."""
            try:
                rel = os.path.relpath(src, src_root)
            except ValueError:
                rel = os.path.basename(src)
            return Path(root) / "_DUPLICATES" / rel

        def work():
            man = Manifest("organise")
            done = skip = parked = 0
            for r in picked:
                src, tgt = r["src"], Path(r["target"])
                if not os.path.exists(src):
                    skip += 1
                    continue
                if tgt.exists():
                    identical = hashchk and quick_hash(src) == quick_hash(tgt)
                    if conflict == "duplicates_folder":
                        # identical content or a competing encode of something
                        # already placed -> move the source into _DUPLICATES,
                        # never leave it behind, never delete it.
                        dst = _dup_target(src)
                        k = 2
                        while dst.exists():
                            dst = dst.with_stem(f"{dst.stem} ({k})")
                            k += 1
                        try:
                            sz = os.path.getsize(src)
                            apply_op("move", src, dst)
                            man.record("move", src, dst, sz,
                                       quick_hash(dst) if hashchk else None)
                            parked += 1
                            self.ctx.log(f"→ _DUPLICATES ({'identical' if identical else 'competing encode'}): "
                                         f"{os.path.basename(src)}")
                        except Exception as e:
                            self.ctx.log(f"FAIL park {os.path.basename(src)}: {e}")
                            skip += 1
                        continue
                    if identical:
                        self.ctx.log(f"skip (identical exists): {tgt.name}")
                        skip += 1
                        continue
                    if conflict == "skip":
                        self.ctx.log(f"skip (name clash): {tgt.name}")
                        skip += 1
                        continue
                    elif conflict == "number":
                        k = 2
                        while tgt.with_stem(f"{tgt.stem} ({k})").exists():
                            k += 1
                        tgt = tgt.with_stem(f"{tgt.stem} ({k})")
                    else:
                        tgt = Path(root) / "_conflicts" / tgt.name
                try:
                    sz = os.path.getsize(src)
                    h = quick_hash(src) if hashchk else None
                    apply_op(op, src, tgt)
                    man.record(op, src, tgt, sz, h)
                    done += 1
                    if done % 10 == 0:
                        self.ctx.status(f"{done} done…")
                except Exception as e:
                    self.ctx.log(f"FAIL {os.path.basename(src)}: {e}")
                    skip += 1
            path = man.save()
            extra = f", parked {parked} in _DUPLICATES" if parked else ""
            self.ctx.log(f"\n{op}d {done} files, skipped {skip}{extra}.")
            self.ctx.log(f"Manifest: {path}")
            self.ctx.ui(self._refresh_history)
            self.ctx.ui(lambda: self.tabs.set("History / Revert"))
        self.ctx.run_worker(work, "Apply")

    # ---------------- History tab ----------------
    def _build_history(self, f):
        c = ui.card(f, self.ctx, "Past operations")
        ui.hint(c, self.ctx, "Every organise run is logged. Revert replays it backwards — files "
                             "return to exactly where they were. Reverting is itself logged, so "
                             "you can undo an undo. Manifests live in ~/MediaForgeData/manifests/.")
        r = ui.row(c)
        self.hist_pick = ctk.CTkOptionMenu(r, values=["(none)"], font=self.ctx.f_small, width=460,
                                           fg_color=self.ctx.pal["surface_2"],
                                           button_color=self.ctx.acc["primary"])
        self.hist_pick.pack(side="left")
        ui.button(r, self.ctx, "Refresh", self._refresh_history)
        ui.button(r, self.ctx, "↩ Revert selected", self._do_revert, primary=True,
                  fg_color=self.ctx.pal["warn"])
        ui.button(r, self.ctx, "Open manifests folder",
                  lambda: __import__("mediaforge.config", fromlist=["open_path"]).open_path(
                      str(__import__("mediaforge.config", fromlist=["MANIFEST_DIR"]).MANIFEST_DIR)))
        self.hist_box = ui.console(c, self.ctx, height=340)
        self._refresh_history()

    def _refresh_history(self):
        self.mans = list_manifests()
        labels = [f"{m['id']}  ·  {m['label']}  ·  {m['count']} files" for m in self.mans] or ["(none)"]
        self.hist_pick.configure(values=labels)
        self.hist_pick.set(labels[0])
        self.hist_box.delete("1.0", "end")
        self.hist_box.insert("1.0", "\n".join(labels))

    def _do_revert(self):
        if not getattr(self, "mans", None):
            return
        idx = 0
        try:
            idx = [f"{m['id']}  ·  {m['label']}  ·  {m['count']} files"
                   for m in self.mans].index(self.hist_pick.get())
        except ValueError:
            return
        m = self.mans[idx]
        if not messagebox.askyesno(self.NAME, f"Revert '{m['label']}' ({m['count']} files)?"):
            return

        def work():
            u, s, rp = revert(m["path"], log=self.ctx.log)
            self.ctx.log(f"\nReverted {u}, skipped {s}. New manifest: {rp}")
            self.ctx.ui(self._refresh_history)
        self.ctx.run_worker(work, "Revert")
