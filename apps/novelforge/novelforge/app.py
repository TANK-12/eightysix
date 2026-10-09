"""
NovelForge GUI (customtkinter).

A left nav rail switches between views; a persistent header carries the model
picker and connection state; generation runs on a worker thread and talks back
to the UI through a single thread-safe queue.
"""

import os
import re
import json
import queue
import shutil
import threading
import traceback
import subprocess

import customtkinter as ctk
from tkinter import filedialog, messagebox

from . import config
from .theme import palette, accent, FONT_FAMILY, MONO_FAMILY
from .janclient import (JanClient, KillSwitch, JanError,
                        ram_status, jan_state, set_state_callback, ram_is_low)
from .catalog import Catalog
from .stylelib import StyleLibrary, PDF_OK
from .project import Project, Series, slugify
from .codex import format_codex, default_codex, codex_stats, codex_is_empty
from .engine import NovelEngine
from . import research
from . import pdfexport
from . import continuation
from .continuation import SPIN_PRESETS
from . import export as bookexport
from . import audiobook


APP_TITLE = "NovelForge"


class Bus:
    """Marshals worker-thread events to the Tk main loop."""
    def __init__(self):
        self.q = queue.Queue()

    def log(self, msg):      self.q.put(("log", str(msg)))
    def stream(self, piece): self.q.put(("stream", piece))
    def progress(self, **kw): self.q.put(("progress", kw))
    def done(self, label):   self.q.put(("done", label))
    def error(self, msg):    self.q.put(("error", str(msg)))


class NovelForgeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = config.load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        try:
            ctk.set_widget_scaling(max(0.7, min(1.6, float(self.settings.get("ui_scale", 1.0)))))
        except Exception:
            pass
        self.pal = palette(self.settings.get("theme", "dark"))
        self.acc = accent(self.settings.get("accent", "forge"))

        self.title(APP_TITLE)
        self.geometry("1240x860")
        self.minsize(1040, 720)
        self.configure(fg_color=self.pal["bg"])

        self.f_h1 = ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold")
        self.f_h2 = ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold")
        self.f_body = ctk.CTkFont(family=FONT_FAMILY, size=13)
        self.f_small = ctk.CTkFont(family=FONT_FAMILY, size=11)
        self.f_mono = ctk.CTkFont(family=MONO_FAMILY, size=12)

        # shared state
        self.catalog = Catalog()
        self.style_lib = StyleLibrary()
        self.client = JanClient(self.settings.get("api_base", config.DEFAULT_API_BASE),
                                timeout=self.settings.get("request_timeout", 900))
        self.models_path = self.settings.get("models_path", config.default_models_path())
        self.project = None
        self._cont_pdfs = []
        self.kill = KillSwitch()
        self.job_kill = KillSwitch()      # export / audiobook only — never stops a generation
        self.bus = Bus()
        self.worker = None
        self.job = None                  # background export / TTS thread
        self._jobs = set()               # labels shown in the header busy indicator
        self._views = {}
        self._nav_buttons = {}
        self._responsive = []            # (widget, "wrap" | "entry") resized with the window
        self._resize_job = None
        self._cover_img = None           # keep a ref or Tk garbage-collects the preview

        self._build_shell()
        # Paint the shell before building the first view: customtkinter redraws
        # every widget on each geometry change, so building Home inline makes the
        # window appear seconds late. This shows the chrome immediately instead.
        self.update_idletasks()
        self.after_idle(lambda: self._show("home"))
        self.after(120, self._pump)
        self.after(200, lambda: self._refresh_models(initial=True))
        self.after(400, self._poll_health)
        set_state_callback(lambda snap: self.bus.q.put(("jan_state", snap)))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==================================================================
    # shell: sidebar + header + content
    # ==================================================================
    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # sidebar
        side = ctk.CTkFrame(self, width=190, corner_radius=0, fg_color=self.pal["surface"])
        side.grid(row=0, column=0, rowspan=2, sticky="nsw")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="  ✦ NovelForge", font=self.f_h2,
                     text_color=self.pal["text"]).pack(anchor="w", padx=16, pady=(18, 4))
        ctk.CTkLabel(side, text="  local long-form studio", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(anchor="w", padx=16, pady=(0, 16))

        for key, label in (("home", "Home"), ("story", "Story"), ("world", "World Codex"),
                           ("refs", "References"), ("continue", "Continue a Series"),
                           ("generate", "Generate"),
                           ("series", "Series"), ("export", "Export"),
                           ("settings", "Settings")):
            b = ctk.CTkButton(side, text=label, anchor="w", height=38,
                              font=self.f_body, corner_radius=8,
                              fg_color="transparent", text_color=self.pal["text_dim"],
                              hover_color=self.pal["surface_2"],
                              command=lambda k=key: self._show(k))
            b.pack(fill="x", padx=10, pady=2)
            self._nav_buttons[key] = b

        self.side_status = ctk.CTkLabel(side, text="", font=self.f_small, justify="left",
                                        text_color=self.pal["text_dim"], wraplength=170)
        self.side_status.pack(side="bottom", anchor="w", padx=16, pady=14)

        # header
        header = ctk.CTkFrame(self, height=58, corner_radius=0, fg_color=self.pal["surface"])
        header.grid(row=0, column=1, sticky="new")
        header.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=16, pady=10)
        self.header_project = ctk.CTkLabel(left, text="No project loaded", font=self.f_h2,
                                           text_color=self.pal["text"])
        self.header_project.pack(side="left")
        self.header_sub = ctk.CTkLabel(left, text="", font=self.f_small,
                                       text_color=self.pal["text_dim"])
        self.header_sub.pack(side="left", padx=10)

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=16, pady=8)
        self.busy_lbl = ctk.CTkLabel(right, text="", font=self.f_small,
                                     text_color=self.acc["primary"])
        self.busy_lbl.pack(side="left", padx=(0, 10))
        self.health_lbl = ctk.CTkLabel(right, text="RAM –", font=self.f_small,
                                       text_color=self.pal["text_dim"])
        self.health_lbl.pack(side="left", padx=(0, 10))
        self.conn_dot = ctk.CTkLabel(right, text="●", font=self.f_body, text_color=self.pal["bad"])
        self.conn_dot.pack(side="left", padx=(0, 2))
        self.conn_txt = ctk.CTkLabel(right, text="offline", font=self.f_small,
                                     text_color=self.pal["text_dim"])
        self.conn_txt.pack(side="left", padx=(0, 8))
        self.model_menu = ctk.CTkOptionMenu(right, values=config.FALLBACK_MODELS,
                                            font=self.f_small, width=260,
                                            fg_color=self.pal["surface_2"],
                                            button_color=self.acc["primary"],
                                            button_hover_color=self.acc["hover"],
                                            command=self._on_model_change)
        self.model_menu.pack(side="left", padx=6)
        ctk.CTkButton(right, text="⟳", width=32, font=self.f_body,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._refresh_models).pack(side="left", padx=2)

        # content
        self.content = ctk.CTkFrame(self, fg_color=self.pal["bg"])
        self.content.grid(row=1, column=1, sticky="nsew", padx=0, pady=0)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.bind("<Configure>", self._on_content_resize)

    # ---------- responsive width ----------
    # Hints and labelled entries were fixed pixel widths, so they clipped on a
    # narrow window and left a dead margin on a wide one. They now track the
    # real content width; call sites that pass an explicit width stay fixed.
    def _content_width(self):
        try:
            w = self.content.winfo_width()
        except Exception:
            w = 0
        return w if w > 200 else 1050

    def _size_responsive(self, widget, kind):
        avail = self._content_width()
        if kind == "wrap":
            widget.configure(wraplength=max(340, avail - 110))
        elif kind == "entry":
            widget.configure(width=max(200, avail - 300))

    def _responsive_widget(self, widget, kind):
        self._responsive.append((widget, kind))
        self._size_responsive(widget, kind)
        return widget

    def _on_content_resize(self, _event=None):
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(120, self._apply_responsive)

    def _apply_responsive(self):
        self._resize_job = None
        alive = []
        for widget, kind in self._responsive:
            try:
                if widget.winfo_exists():
                    self._size_responsive(widget, kind)
                    alive.append((widget, kind))
            except Exception:
                pass
        self._responsive = alive

    def _show(self, key):
        for k, b in self._nav_buttons.items():
            b.configure(fg_color=self.acc["primary"] if k == key else "transparent",
                        text_color=self.acc["on"] if k == key else self.pal["text_dim"])
        if key not in self._views:
            builder = {
                "home": self._build_home, "story": self._build_story,
                "world": self._build_world, "refs": self._build_refs,
                "continue": self._build_continue,
                "generate": self._build_generate, "series": self._build_series,
                "export": self._build_export,
                "settings": self._build_settings,
            }[key]
            frame = ctk.CTkScrollableFrame(self.content, fg_color=self.pal["bg"])
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_columnconfigure(0, weight=1)
            builder(frame)
            self._views[key] = frame
        for k, v in self._views.items():
            (v.grid if k == key else v.grid_remove)()
        if key == "home":
            self._refresh_home()
        if key == "world":
            self._refresh_codex_view()
        if key == "series":
            self._refresh_series_view()
        if key == "export":
            self._refresh_export_view()

    # ---------- small ui helpers ----------
    @property
    def _dense(self):
        return self.settings.get("ui_density", "comfortable") == "compact"

    def _card(self, parent, title=None):
        gap = 5 if self._dense else 10
        c = ctk.CTkFrame(parent, fg_color=self.pal["surface"], corner_radius=12)
        c.pack(fill="x", padx=24, pady=gap)
        c.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(c, text=title, font=self.f_h2, text_color=self.pal["text"]).pack(
                anchor="w", padx=18, pady=((8 if self._dense else 14), 2))
        return c

    def _hint(self, parent, text):
        lbl = ctk.CTkLabel(parent, text=text, font=self.f_small, justify="left",
                           text_color=self.pal["text_dim"])
        lbl.pack(anchor="w", padx=18, pady=(0, 6 if self._dense else 12))
        return self._responsive_widget(lbl, "wrap")

    def _labeled_entry(self, parent, label, value="", width=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=3 if self._dense else 6)
        ctk.CTkLabel(row, text=label, font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        e = ctk.CTkEntry(row, font=self.f_body, width=width or 680,
                         fg_color=self.pal["surface_2"])
        e.pack(side="left", fill="x", expand=True)
        if value:
            e.insert(0, value)
        if width is None:
            self._responsive_widget(e, "entry")
        return e

    def _labeled_text(self, parent, label, value="", height=90):
        ctk.CTkLabel(parent, text=label, font=self.f_body, anchor="w",
                     text_color=self.pal["text"]).pack(anchor="w", padx=18,
                                                       pady=(4 if self._dense else 8, 2))
        if self._dense:
            height = max(48, int(height * 0.75))
        t = ctk.CTkTextbox(parent, font=self.f_body, height=height, fg_color=self.pal["surface_2"],
                           wrap="word")
        t.pack(fill="x", padx=18, pady=(0, 6))
        if value:
            t.insert("1.0", value)
        return t

    def _set_busy(self, label, on=True):
        """Header indicator so a background export / TTS job is never invisible."""
        (self._jobs.add if on else self._jobs.discard)(label)
        try:
            self._render_health()
        except Exception:
            pass

    def _toast(self, msg, kind="info"):
        self.side_status.configure(text=msg,
                                   text_color=self.pal["good"] if kind == "ok"
                                   else self.pal["bad"] if kind == "err" else self.pal["text_dim"])

    # ==================================================================
    # model / connection
    # ==================================================================
    def _refresh_models(self, initial=False):
        def work():
            self.client = JanClient(self.settings.get("api_base", config.DEFAULT_API_BASE),
                                    timeout=self.settings.get("request_timeout", 900))
            models = self.catalog.refresh(self.client, self.models_path)
            up = self.client.ping()
            self.bus.q.put(("models", (models, up)))
        threading.Thread(target=work, daemon=True).start()

    def _apply_models(self, models, up):
        cur = self.model_menu.get()
        self.model_menu.configure(values=models or config.FALLBACK_MODELS)
        want = self.settings.get("model") or (self.project.state.get("last_model") if self.project else "")
        if want in models:
            self.model_menu.set(want)
        elif cur not in models and models:
            self.model_menu.set(models[0])
        self.conn_dot.configure(text_color=self.pal["good"] if up else self.pal["bad"])
        try:
            self.conn_txt.configure(text="online" if up else "offline",
                                    text_color=self.pal["good"] if up else self.pal["text_dim"])
        except Exception:
            pass
        model = self.model_menu.get()
        desc = self.catalog.describe(model) if model else ""
        self.header_sub.configure(
            text=(f"Jan {'online' if up else 'offline'} · {self.catalog.api_count} API / "
                  f"{self.catalog.scan_count} on disk · {desc}"))
        self._on_model_change(model)

    def _on_model_change(self, model):
        prev = self.settings.get("model")
        self.settings["model"] = model
        config.save_settings(self.settings)
        w = getattr(self, "gen_model_note", None)
        try:
            if w is not None and w.winfo_exists():
                w.configure(text=self.catalog.describe(model))
        except Exception:
            pass
        # switching models leaves the old one resident in Jan's llama.cpp router;
        # nudge it to free the previous model so two big models don't stack up.
        if prev and prev != model and not (self.worker and self.worker.is_alive()):
            from .janclient import free_jan_memory
            threading.Thread(
                target=lambda: free_jan_memory(
                    self.settings.get("api_base", config.DEFAULT_API_BASE), keep_model=model),
                daemon=True).start()

    # ==================================================================
    # health: RAM + Jan busy state (header indicator)
    # ==================================================================
    def _poll_health(self):
        try:
            self._render_health()
        except Exception:
            pass
        self.after(2500, self._poll_health)

    def _render_health(self):
        st = ram_status()
        js = jan_state()
        if st.get("available_gb") is None:
            ram_txt, ram_col = "RAM n/a", self.pal["text_dim"]
        else:
            avail = st["available_gb"]
            min_gb = float(self.settings.get("min_free_ram_gb", 2.5))
            ram_col = (self.pal["bad"] if avail < min_gb else
                       self.pal["warn"] if avail < min_gb + 2 else self.pal["text_dim"])
            ram_txt = f"RAM {avail:.1f}G free"
        if js.get("busy"):
            label = js.get("label") or "working"
            ram_txt += f"  ·  Jan: {label}…"
            ram_col = self.acc["primary"] if ram_col == self.pal["text_dim"] else ram_col
        elif js.get("queue"):
            ram_txt += f"  ·  Jan: {js['queue']} queued"
        try:
            if self.health_lbl.winfo_exists():
                self.health_lbl.configure(text=ram_txt, text_color=ram_col)
            if self.busy_lbl.winfo_exists():
                jobs = " · ".join(sorted(self._jobs))
                self.busy_lbl.configure(text=f"⏳ {jobs}…" if jobs else "")
        except Exception:
            pass

    def _unload_jan(self):
        from .janclient import free_jan_memory
        self.unload_lbl.configure(text="asking Jan…")

        def work():
            ok, tried = free_jan_memory(
                self.settings.get("api_base", config.DEFAULT_API_BASE),
                keep_model=self.model_menu.get())
            msg = ("done — idle models unloaded." if ok else
                   "this Jan build has no unload API; it LRU-evicts past its "
                   "model limit on its own.")
            self.bus.q.put(("call", lambda: self.unload_lbl.configure(text=msg)))
        threading.Thread(target=work, daemon=True).start()

    # ==================================================================
    # HOME
    # ==================================================================
    def _build_home(self, f):
        top = self._card(f, "Projects")
        self._hint(top, "Each project is one book, saved under ~/NovelMakerData/projects/. "
                        "Create a new one or open an existing book to keep writing.")
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))
        self.new_proj_entry = ctk.CTkEntry(row, placeholder_text="new project name…",
                                           font=self.f_body, width=280, fg_color=self.pal["surface_2"])
        self.new_proj_entry.pack(side="left")
        ctk.CTkButton(row, text="Create", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._create_project).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Open data folder", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=lambda: config.open_in_file_manager(config.PROJECTS_DIR)).pack(side="left", padx=4)

        self.home_list = ctk.CTkFrame(f, fg_color="transparent")
        self.home_list.pack(fill="x", padx=24, pady=4)

    def _refresh_home(self):
        # quick_stats touches three files per project; with a shelf of books that
        # is enough disk I/O to stutter the UI, so it happens on a thread.
        def work():
            names = Project.list_all()
            self.bus.q.put(("home_stats", [(n, Project.quick_stats(n)) for n in names]))
        threading.Thread(target=work, daemon=True).start()

    def _render_home(self, rows):
        try:
            if not self.home_list.winfo_exists():
                return
        except Exception:
            return
        for w in self.home_list.winfo_children():
            w.destroy()
        if not rows:
            ctk.CTkLabel(self.home_list, text="No books yet — create one above.",
                         font=self.f_body, text_color=self.pal["text_dim"]).pack(anchor="w", pady=8)
            return
        for name, st in rows:
            card = ctk.CTkFrame(self.home_list, fg_color=self.pal["surface"], corner_radius=10)
            card.pack(fill="x", pady=4)
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", padx=16, pady=10, fill="x", expand=True)
            ctk.CTkLabel(info, text=name.replace("_", " ").title(), font=self.f_h2,
                         text_color=self.pal["text"]).pack(anchor="w")
            meta = f"{st['chapters']} chapters · {st['words']:,} words"
            if st["genre"]:
                meta += f" · {st['genre']}"
            ctk.CTkLabel(info, text=meta, font=self.f_small,
                         text_color=self.pal["text_dim"]).pack(anchor="w")
            ctk.CTkButton(card, text="Open", width=80, font=self.f_body,
                          fg_color=self.acc["primary"], hover_color=self.acc["hover"],
                          command=lambda n=name: self._open_project(n)).pack(side="right", padx=14)

    def _create_project(self):
        name = self.new_proj_entry.get().strip()
        if not name:
            return self._toast("Type a project name first.", "err")
        self._open_project(name)
        self._refresh_home()

    def _open_project(self, name):
        self.project = Project(name)
        self.header_project.configure(text=self.project.bible.get("title") or name)
        self._toast(f"Loaded '{name}'.", "ok")
        # rebuild data-bound views so fields refresh
        for k in ("story", "world", "generate", "series", "continue", "export"):
            if k in self._views:
                self._views[k].destroy()
                del self._views[k]
        self._show("story")
        if self.project.state.get("last_model"):
            self._refresh_models()

    def _require_project(self):
        if not self.project:
            messagebox.showinfo(APP_TITLE, "Open or create a project on the Home tab first.")
            return False
        return True

    # ==================================================================
    # STORY
    # ==================================================================
    def _build_story(self, f):
        b = self.project.bible if self.project else {}

        # ---- scope card ----
        sc = self._card(f, "Scope")
        self._hint(sc, "A one-shot is a single self-contained story. A series is N books that "
                       "share a world and an overarching arc — each book resolves its own "
                       "arc and (except the last) ends on a hook. This changes the outline, "
                       "the ending, and how books are saved and chained.")
        srow = ctk.CTkFrame(sc, fg_color="transparent")
        srow.pack(fill="x", padx=18, pady=(0, 6))
        self.scope_seg = ctk.CTkSegmentedButton(
            srow, values=["One-shot", "Series"], font=self.f_small, command=self._on_scope_change)
        self.scope_seg.set("Series" if b.get("story_scope", "series") == "series"
                           and b.get("planned_books", 1) > 1 else "One-shot")
        self.scope_seg.pack(side="left")
        ctk.CTkLabel(srow, text="books:", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(14, 4))
        self.e_books = ctk.CTkEntry(srow, width=56, font=self.f_body, fg_color=self.pal["surface_2"])
        self.e_books.insert(0, str(b.get("planned_books", self.settings.get("planned_books", 3)) or 3))
        self.e_books.pack(side="left")
        ctk.CTkLabel(srow, text="  ·  World depth:", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(14, 4))
        self.opt_depth = ctk.CTkOptionMenu(srow, values=["sketch", "standard", "rich", "epic"],
                                           font=self.f_small, width=110,
                                           fg_color=self.pal["surface_2"], button_color=self.acc["primary"])
        self.opt_depth.set(self.settings.get("world_depth", "rich"))
        self.opt_depth.pack(side="left")
        self.book_idx_lbl = ctk.CTkLabel(sc, text="", font=self.f_small,
                                         text_color=self.pal["text_dim"])
        self.book_idx_lbl.pack(anchor="w", padx=18, pady=(0, 8))

        c = self._card(f, "Story Bible")
        self._hint(c, "Fill in as little or as much as you like. Free-Rein invents anything "
                      "you leave blank — a full cast, locations, factions and world rules — "
                      "and writes them into the World Document + Codex. Deeper world depth = "
                      "much more detail (and more model time).")
        self.e_title = self._labeled_entry(c, "Title", b.get("title", ""))
        self.e_genre = self._labeled_entry(c, "Genre / vibe", b.get("genre", ""))
        self.e_protag = self._labeled_entry(c, "Protagonist", b.get("protagonist", ""))
        self.t_plot = self._labeled_text(c, "Core plot / conflict", b.get("plot", ""), height=80)
        self.t_pinned = self._labeled_text(c, "Pinned facts (never dropped from context)",
                                           b.get("pinned_facts", ""), height=90)
        self.t_inspo = self._labeled_text(c, "Inspiration notes (loose flavour, not binding)",
                                          b.get("inspiration_notes", ""), height=70)
        self.t_directives = self._labeled_text(c, "Author directives (obeyed every scene, e.g. "
                                               "\"no explicit content\", \"present tense\", \"dry wit\")",
                                               b.get("style_directives", ""), height=60)
        btns = ctk.CTkFrame(c, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(btns, text="Save story bible", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._save_story).pack(side="left")
        ctk.CTkButton(btns, text="✦ Free-Rein: build world & cast", font=self.f_body,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._free_rein).pack(side="left", padx=8)
        self.free_rein_expand = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(btns, text="overwrite filled fields too", variable=self.free_rein_expand,
                        font=self.f_small).pack(side="left", padx=8)

        wd = self._card(f, "World Document")
        self._hint(wd, "The full worldbuilding prose Free-Rein produces. Editable. A trimmed "
                       "copy is fed into every chapter so the story stays consistent with it.")
        self.t_worlddoc = ctk.CTkTextbox(wd, font=self.f_body, height=220,
                                         fg_color=self.pal["surface_2"], wrap="word")
        self.t_worlddoc.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        if b.get("world_doc"):
            self.t_worlddoc.insert("1.0", b["world_doc"])

        self.arc_card = self._card(f, "Series Arc")
        self._hint(self.arc_card, "The overarching multi-book plot. Built by 'Plan series arc' "
                                  "(or by Free-Rein for a series). Each book's outline is shaped by this.")
        arow = ctk.CTkFrame(self.arc_card, fg_color="transparent")
        arow.pack(fill="x", padx=18, pady=(0, 4))
        ctk.CTkButton(arow, text="Plan series arc", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._plan_arc).pack(side="left")
        self.t_arc = ctk.CTkTextbox(self.arc_card, font=self.f_body, height=160,
                                    fg_color=self.pal["surface_2"], wrap="word")
        self.t_arc.pack(fill="both", expand=True, padx=18, pady=(4, 10))
        if b.get("arc_synopsis"):
            self.t_arc.insert("1.0", b["arc_synopsis"])

        self._on_scope_change(self.scope_seg.get())

        o = self._card(f, "Outline")
        self._hint(o, "Editable. Every line is one chapter goal and drives generation directly. "
                      "Generate one with the button, or write/paste your own.")
        self.t_outline = ctk.CTkTextbox(o, font=self.f_mono, height=260,
                                        fg_color=self.pal["surface_2"], wrap="word")
        self.t_outline.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        if b.get("outline"):
            self.t_outline.insert("1.0", b["outline"])
        orow = ctk.CTkFrame(o, fg_color="transparent")
        orow.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkButton(orow, text="Save outline", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._save_outline).pack(side="left")
        ctk.CTkButton(orow, text="Generate outline from bible", font=self.f_body,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._gen_outline).pack(side="left", padx=8)

    def _on_scope_change(self, value):
        is_series = value == "Series"
        try:
            self.e_books.configure(state="normal" if is_series else "disabled")
            self.arc_card.pack(fill="x", padx=24, pady=10) if is_series else self.arc_card.pack_forget()
        except Exception:
            pass
        if self.project:
            k = self.project.bible.get("book_index", 1)
            self.book_idx_lbl.configure(
                text=(f"This project is book {k} of the series." if is_series
                      else "Single self-contained book."))

    def _collect_story(self):
        b = self.project.bible
        b["title"] = self.e_title.get().strip() or self.project.name
        b["genre"] = self.e_genre.get().strip()
        b["protagonist"] = self.e_protag.get().strip()
        b["plot"] = self.t_plot.get("1.0", "end").strip()
        b["pinned_facts"] = self.t_pinned.get("1.0", "end").strip()
        b["inspiration_notes"] = self.t_inspo.get("1.0", "end").strip()
        b["style_directives"] = self.t_directives.get("1.0", "end").strip()
        b["world_doc"] = self.t_worlddoc.get("1.0", "end").strip()
        b["arc_synopsis"] = self.t_arc.get("1.0", "end").strip()
        if self.scope_seg.get() == "Series":
            b["story_scope"] = "series"
            try:
                b["planned_books"] = max(2, int(float(self.e_books.get())))
            except Exception:
                b["planned_books"] = 3
        else:
            b["story_scope"] = "oneshot"
            b["planned_books"] = 1
        self.settings["world_depth"] = self.opt_depth.get()
        self.settings["story_scope"] = b["story_scope"]
        self.settings["planned_books"] = b["planned_books"]
        config.save_settings(self.settings)
        self.project.save()

    def _save_story(self):
        if not self._require_project():
            return
        self._collect_story()
        self.header_project.configure(text=self.project.bible["title"])
        self._toast("Story bible saved.", "ok")

    def _save_outline(self):
        if not self._require_project():
            return
        raw = self.t_outline.get("1.0", "end").strip()
        self.project.bible["outline"] = raw
        lines = [re.sub(r"^\s*(?:chapter\s*)?\d+\s*[:.\-)]\s*", "", ln.strip(), flags=re.I)
                 for ln in raw.splitlines() if ln.strip()]
        self.project.bible["chapter_list"] = [ln for ln in lines if ln]
        self.project.save()
        self._toast(f"Outline saved — {len(self.project.bible['chapter_list'])} chapters.", "ok")

    def _free_rein(self):
        if not self._require_project():
            return
        self._collect_story()
        self._run_worker("Free-Rein world build", self._job_free_rein)

    def _job_free_rein(self, engine):
        engine.build_world(self.project.bible.get("genre", ""),
                           self.project.bible.get("protagonist", ""),
                           self.project.bible.get("plot", ""),
                           expand_existing=self.free_rein_expand.get())
        self.bus.q.put(("reload_story", None))

    def _plan_arc(self):
        if not self._require_project():
            return
        self._collect_story()
        planned = self.project.bible.get("planned_books", 3)
        if self.project.bible.get("story_scope") != "series" or planned < 2:
            return self._toast("Set scope to Series (2+ books) first.", "err")
        self._run_worker("Series arc", lambda e: (e.build_arc(planned),
                                                  self.bus.q.put(("reload_story", None))))

    def _gen_outline(self):
        if not self._require_project():
            return
        self._collect_story()
        target = int(self.settings.get("target_chapters", 30))
        if hasattr(self, "sp_chapters"):
            try:
                target = int(self.sp_chapters.get())
            except Exception:
                pass
        self._run_worker("Outline", lambda e: self._job_outline(e, target))

    def _job_outline(self, engine, target):
        text, lines = engine.build_outline(target)
        self.bus.q.put(("set_outline", text))

    # ==================================================================
    # WORLD CODEX
    # ==================================================================
    def _build_world(self, f):
        c = self._card(f, "World Codex")
        self._hint(c, "Characters, relationships, locations, factions and facts the story has "
                      "established. It updates itself after chapters so nothing is forgotten in a "
                      "long book. Entries are only ever added to — never auto-deleted.")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(row, text="Refresh", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._refresh_codex_view).pack(side="left")
        self.codex_edit = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="edit raw JSON", variable=self.codex_edit, font=self.f_small,
                        command=self._toggle_codex_edit).pack(side="left", padx=10)
        ctk.CTkButton(row, text="Save JSON", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._save_codex_json).pack(side="left")
        ctk.CTkButton(row, text="Rebuild from chapters", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._rebuild_codex).pack(side="left", padx=10)
        self.codex_stats_lbl = ctk.CTkLabel(row, text="", font=self.f_small,
                                            text_color=self.pal["text_dim"])
        self.codex_stats_lbl.pack(side="left", padx=10)

        self.codex_box = ctk.CTkTextbox(c, font=self.f_mono, height=360,
                                        fg_color=self.pal["surface_2"], wrap="word")
        self.codex_box.pack(fill="both", expand=True, padx=18, pady=(4, 12))

        sy = self._card(f, "Story so far  ·  Open threads")
        self._hint(sy, "Auto-maintained each chapter. The running synopsis is the model's "
                       "primary plot memory; open threads are what still needs paying off.")
        self.synopsis_box = ctk.CTkTextbox(sy, font=self.f_body, height=150,
                                           fg_color=self.pal["surface_2"], wrap="word")
        self.synopsis_box.pack(fill="x", padx=18, pady=(0, 6))
        self.threads_box = ctk.CTkTextbox(sy, font=self.f_body, height=110,
                                          fg_color=self.pal["surface_2"], wrap="word")
        self.threads_box.pack(fill="x", padx=18, pady=(0, 12))

    def _refresh_codex_view(self):
        if not self.project or self.codex_edit.get():
            return
        try:
            if not self.codex_box.winfo_exists():
                return
        except Exception:
            return
        self.codex_box.delete("1.0", "end")
        self.codex_box.insert("1.0", format_codex(self.project.codex, max_chars=10_000_000,
                                                  current_chapter=self.project.chapter_count() + 1)
                              or "(empty — run Free-Rein or start generating)")
        s = codex_stats(self.project.codex)
        self.codex_stats_lbl.configure(text=f"{s['characters']} chars · {s['locations']} places · "
                                            f"{s['factions']} factions · {s['facts']} facts")
        if hasattr(self, "synopsis_box"):
            for box, val, ph in (
                (self.synopsis_box, self.project.state.get("running_synopsis", ""),
                 "(builds as chapters are written)"),
                (self.threads_box,
                 "\n".join(f"• {t}" for t in self.project.bible.get("open_threads", [])),
                 "(no tracked threads yet)")):
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("1.0", val or ph)
                box.configure(state="disabled")

    def _toggle_codex_edit(self):
        if not self._require_project():
            self.codex_edit.set(False)
            return
        self.codex_box.delete("1.0", "end")
        if self.codex_edit.get():
            self.codex_box.insert("1.0", json.dumps(self.project.codex, ensure_ascii=False, indent=2))
        else:
            self._refresh_codex_view()

    def _save_codex_json(self):
        if not self._require_project() or not self.codex_edit.get():
            return messagebox.showinfo(APP_TITLE, "Tick 'edit raw JSON' first.")
        try:
            data = json.loads(self.codex_box.get("1.0", "end"))
            assert isinstance(data, dict)
        except Exception as e:
            return messagebox.showerror(APP_TITLE, f"Invalid JSON: {e}")
        merged = default_codex()
        for k in merged:
            if k in data:
                merged[k] = data[k]
        self.project.codex = merged
        self.project.save_codex()
        self.codex_edit.set(False)
        self._refresh_codex_view()
        self._toast("Codex saved.", "ok")

    def _rebuild_codex(self):
        if not self._require_project():
            return
        if not messagebox.askyesno(APP_TITLE, "Erase the codex and rebuild it by re-reading "
                                              "every written chapter?"):
            return
        self._run_worker("Codex rebuild", lambda e: e.rebuild_codex())

    # ==================================================================
    # REFERENCES (PDF style + research)
    # ==================================================================
    def _build_refs(self, f):
        c = self._card(f, "PDF Style & Reference")
        if not PDF_OK:
            self._hint(c, "pypdf isn't installed, so PDF learning is off. Run:  pip install pypdf")
        self._hint(c, "Style Guides (how a book is written) are auto-folded into every scene. "
                      "Content Summaries (what it's about) are kept only as your reference and are "
                      "never fed into generation, so your story stays original.")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(row, text="Add PDF(s)…", font=self.f_small, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._add_pdfs).pack(side="left")
        ctk.CTkButton(row, text="Analyze style", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=lambda: self._pdf_action("style")).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Summarize content", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=lambda: self._pdf_action("content")).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Remove", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._remove_pdf).pack(side="left", padx=6)

        self.pdf_list = ctk.CTkOptionMenu(c, values=self.style_lib.names() or ["(none)"],
                                          font=self.f_small, fg_color=self.pal["surface_2"],
                                          button_color=self.acc["primary"],
                                          command=lambda _=None: self._show_pdf_notes())
        self.pdf_list.pack(anchor="w", padx=18, pady=4)
        self.pdf_mode = ctk.StringVar(value="style")
        seg = ctk.CTkSegmentedButton(c, values=["Style guide", "Content summary"],
                                     font=self.f_small,
                                     command=lambda v: (self.pdf_mode.set(
                                         "style" if v.startswith("Style") else "content"),
                                         self._show_pdf_notes()))
        seg.set("Style guide")
        seg.pack(anchor="w", padx=18, pady=4)
        self.pdf_notes = ctk.CTkTextbox(c, font=self.f_body, height=200,
                                        fg_color=self.pal["surface_2"], wrap="word")
        self.pdf_notes.pack(fill="x", padx=18, pady=(4, 16))

        r = self._card(f, "Research (optional idea spark)")
        self._hint(r, "Best-effort DuckDuckGo Instant Answers — no key, only your query leaves "
                      "the machine. Good for mythologies, eras, tropes.")
        rr = ctk.CTkFrame(r, fg_color="transparent")
        rr.pack(fill="x", padx=18, pady=6)
        self.research_entry = ctk.CTkEntry(rr, placeholder_text="topic or concept…", font=self.f_body,
                                           fg_color=self.pal["surface_2"], width=360)
        self.research_entry.pack(side="left")
        ctk.CTkButton(rr, text="Search", font=self.f_small, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._do_research).pack(side="left", padx=6)
        ctk.CTkButton(rr, text="→ add to inspiration notes", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._research_to_notes).pack(side="left", padx=6)
        self.research_box = ctk.CTkTextbox(r, font=self.f_body, height=180,
                                           fg_color=self.pal["surface_2"], wrap="word")
        self.research_box.pack(fill="x", padx=18, pady=(4, 16))

    def _add_pdfs(self):
        if not PDF_OK:
            return messagebox.showerror(APP_TITLE, "Run: pip install pypdf")
        paths = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        if not paths:
            return

        def work():
            for p in paths:
                name = os.path.splitext(os.path.basename(p))[0]
                self.bus.log(f"Reading {name}…")
                try:
                    text = StyleLibrary.extract_pdf_text(p)
                    n = self.style_lib.add_source(name, text)
                    self.bus.log(f"  learned {n} chunks from {name}.")
                except Exception as e:
                    self.bus.log(f"  failed: {e}")
            self.bus.q.put(("pdf_list", None))
        threading.Thread(target=work, daemon=True).start()

    def _remove_pdf(self):
        name = self.pdf_list.get()
        if name and name != "(none)":
            self.style_lib.remove_source(name)
            self._refresh_pdf_list()

    def _refresh_pdf_list(self):
        names = self.style_lib.names() or ["(none)"]
        self.pdf_list.configure(values=names)
        self.pdf_list.set(names[0])
        self._show_pdf_notes()

    def _show_pdf_notes(self):
        name = self.pdf_list.get()
        src = self.style_lib.get(name)
        key = "style_notes" if self.pdf_mode.get() == "style" else "content_summary"
        self.pdf_notes.delete("1.0", "end")
        self.pdf_notes.insert("1.0", src.get(key, "") or "(not generated yet)")

    def _pdf_action(self, kind):
        name = self.pdf_list.get()
        if not name or name == "(none)":
            return
        model = self.model_menu.get()
        client = self.client

        def work():
            self.bus.log(f"{'Analyzing style' if kind == 'style' else 'Summarizing'} of {name}…")
            try:
                if kind == "style":
                    self.style_lib.analyze_style(client, model, name,
                                                 temperature=self.settings.get("structure_temperature", 0.3))
                else:
                    self.style_lib.summarize_content(client, model, name,
                                                     temperature=self.settings.get("structure_temperature", 0.3))
                self.bus.q.put(("pdf_notes", None))
                self.bus.log("  done.")
            except Exception as e:
                self.bus.log(f"  failed: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _do_research(self):
        q = self.research_entry.get().strip()
        if not q:
            return

        def work():
            self.bus.log(f"Researching '{q}'…")
            res = research.lookup(q)
            self.bus.q.put(("research_result", res))
        threading.Thread(target=work, daemon=True).start()

    def _research_to_notes(self):
        if not self._require_project():
            return
        text = self.research_box.get("1.0", "end").strip()
        if not text:
            return
        cur = self.t_inspo.get("1.0", "end").strip() if hasattr(self, "t_inspo") else \
            self.project.bible.get("inspiration_notes", "")
        combined = (cur + "\n\n" + text).strip()
        self.project.bible["inspiration_notes"] = combined
        self.project.save()
        if hasattr(self, "t_inspo"):
            self.t_inspo.delete("1.0", "end")
            self.t_inspo.insert("1.0", combined)
        self._toast("Added to inspiration notes.", "ok")

    # ==================================================================
    # CONTINUE A SERIES  (never-ending story from PDFs)
    # ==================================================================
    def _build_continue(self, f):
        c = self._card(f, "Continue a Series  ·  Never-Ending Story")
        if not PDF_OK:
            self._hint(c, "PDF reading is off — run:  pip install pypdf")
        self._hint(c, "Drop in 1–12 (or more) PDFs of an existing series or an author's "
                      "books. NovelForge reads them, learns the voice, rebuilds the world "
                      "codex and a 'story so far', notes where the last book ended — then "
                      "keeps writing new chapters in that style and universe, "
                      "indefinitely. Add a 'spin' for a deliberate twist.")

        if not self.project:
            ctk.CTkLabel(c, text="Open or create a project on the Home tab first — the "
                                 "ingested series lands in it.", font=self.f_body,
                         text_color=self.pal["text_dim"]).pack(anchor="w", padx=18, pady=14)
            return

        # -- PDFs --
        prow = ctk.CTkFrame(c, fg_color="transparent")
        prow.pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(prow, text="Add PDF(s)…", font=self.f_small, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._cont_add_pdfs).pack(side="left")
        ctk.CTkButton(prow, text="Clear list", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._cont_clear_pdfs).pack(side="left", padx=6)
        self.cont_pdf_lbl = ctk.CTkLabel(c, text="", font=self.f_small, justify="left",
                                         text_color=self.pal["text_dim"])
        self.cont_pdf_lbl.pack(anchor="w", padx=18, pady=(0, 6))
        self._responsive_widget(self.cont_pdf_lbl, "wrap")

        # -- spin --
        srow = ctk.CTkFrame(c, fg_color="transparent")
        srow.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(srow, text="Spin", font=self.f_body, width=90, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.cont_spin = ctk.CTkOptionMenu(srow, values=list(SPIN_PRESETS.keys()),
                                           font=self.f_small, width=260,
                                           fg_color=self.pal["surface_2"],
                                           button_color=self.acc["primary"],
                                           command=self._cont_spin_preset)
        self.cont_spin.set(next(iter(SPIN_PRESETS)))
        self.cont_spin.pack(side="left")
        self.cont_spin_txt = self._labeled_text(
            c, "Spin details (edit freely — leave the preset text or write your own)",
            "", height=60)
        self.cont_notes = self._labeled_text(
            c, "Extra direction for the continuation (optional)", "", height=50)

        irow = ctk.CTkFrame(c, fg_color="transparent")
        irow.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(irow, text="✦ Ingest corpus", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._cont_ingest).pack(side="left")
        b = self.project.bible
        state = ("✓ ingested: " + ", ".join(b.get("source_books", []))
                 if b.get("continuation_mode") else "not ingested yet")
        self.cont_state_lbl = ctk.CTkLabel(irow, text=state, font=self.f_small,
                                           text_color=self.pal["text_dim"])
        self.cont_state_lbl.pack(side="left", padx=12)

        # -- narrative voice --
        nv = self._card(f, "Narrative voice  ·  write exactly as the author did")
        self._hint(nv, "Ingest measures the point of view and tense from the author's own "
                       "prose (dialogue excluded, so a character saying \"I\" doesn't fool "
                       "it) and pins them as an absolute rule in every scene prompt — this "
                       "is what stops the continuation sliding into another head or into "
                       "present tense. Override any of it here if it guessed wrong.")
        prof = self.project.bible.get("narrative_profile") or {}
        vrow = ctk.CTkFrame(nv, fg_color="transparent")
        vrow.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(vrow, text="Point of view", font=self.f_body, width=120, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.opt_pov = ctk.CTkOptionMenu(
            vrow, values=["(not set)", "first person", "second person", "third person"],
            font=self.f_small, width=150, fg_color=self.pal["surface_2"],
            button_color=self.acc["primary"], command=lambda _=None: self._save_narrative_voice())
        self.opt_pov.set(prof.get("pov") or "(not set)")
        self.opt_pov.pack(side="left")
        ctk.CTkLabel(vrow, text="Tense", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(14, 4))
        self.opt_tense = ctk.CTkOptionMenu(
            vrow, values=["(not set)", "past tense", "present tense"], font=self.f_small,
            width=140, fg_color=self.pal["surface_2"], button_color=self.acc["primary"],
            command=lambda _=None: self._save_narrative_voice())
        self.opt_tense.set(prof.get("tense") or "(not set)")
        self.opt_tense.pack(side="left")
        ctk.CTkLabel(vrow, text="POV character", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(14, 4))
        self.e_pov_char = ctk.CTkEntry(vrow, width=170, font=self.f_body,
                                       fg_color=self.pal["surface_2"])
        self.e_pov_char.insert(0, prof.get("pov_character", ""))
        self.e_pov_char.pack(side="left")
        ctk.CTkButton(vrow, text="Save", font=self.f_small, width=60,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._save_narrative_voice).pack(side="left", padx=8)
        self.pov_detect_lbl = ctk.CTkLabel(nv, text="", font=self.f_small, justify="left",
                                           text_color=self.pal["text_dim"])
        self.pov_detect_lbl.pack(anchor="w", padx=18, pady=(0, 12))
        self._responsive_widget(self.pov_detect_lbl, "wrap")
        self._render_pov_detection()

        # -- write chapters --
        wc = self._card(f, "Write the next chapters")
        self._hint(wc, "Each run writes this many further chapters from wherever the book "
                       "stands now, extending the outline automatically. Run it again and "
                       "again — the story never has to end.")
        wr = ctk.CTkFrame(wc, fg_color="transparent")
        wr.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(wr, text="Chapters to write now", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left")
        self.cont_n = ctk.CTkEntry(wr, font=self.f_body, width=70, fg_color=self.pal["surface_2"])
        self.cont_n.insert(0, "8")
        self.cont_n.pack(side="left", padx=8)
        ctk.CTkLabel(wr, text="words/chapter", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(10, 0))
        self.cont_w = ctk.CTkEntry(wr, font=self.f_body, width=80, fg_color=self.pal["surface_2"])
        self.cont_w.insert(0, str(self.project.state.get("target_words_per_chapter", 3000)))
        self.cont_w.pack(side="left", padx=8)
        ctk.CTkButton(wr, text="▶  Write / continue", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._cont_write).pack(side="left", padx=12)
        ctk.CTkButton(wr, text="⏸ Soft stop", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._soft_stop).pack(side="left")
        self.cont_progress_lbl = ctk.CTkLabel(
            wc, text=f"{self.project.chapter_count()} chapters written so far.",
            font=self.f_small, text_color=self.pal["text_dim"])
        self.cont_progress_lbl.pack(anchor="w", padx=18, pady=(0, 10))

        self._cont_refresh_pdf_lbl()

    def _render_pov_detection(self):
        prof = (self.project.bible.get("narrative_profile") or {}) if self.project else {}
        if not prof.get("pov"):
            self.pov_detect_lbl.configure(
                text="Not measured yet — ingest a corpus, or set it by hand above. "
                     "Left unset, the model is only told to keep 'the POV established "
                     "so far', which is what lets it drift.")
            return
        c = prof.get("counts", {}) or {}
        self.pov_detect_lbl.configure(
            text=(f"Measured from the source books: {continuation.profile_line(prof)} "
                  f"(confidence {prof.get('confidence', '?')}). "
                  f"Narration pronouns — 1st {c.get('first', '?')}, 2nd {c.get('second', '?')}, "
                  f"3rd {c.get('third', '?')}; verbs — past {c.get('past', '?')}, "
                  f"present {c.get('present', '?')}."))

    def _save_narrative_voice(self):
        if not self._require_project():
            return
        prof = dict(self.project.bible.get("narrative_profile") or {})
        pov, tense = self.opt_pov.get(), self.opt_tense.get()
        prof["pov"] = "" if pov == "(not set)" else pov
        prof["tense"] = "" if tense == "(not set)" else tense
        prof["pov_character"] = self.e_pov_char.get().strip()
        if prof.get("pov"):
            prof.setdefault("confidence", 1.0)
            self.project.bible["narrative_profile"] = prof
        else:
            self.project.bible.pop("narrative_profile", None)
        self.project.save()
        self._render_pov_detection()
        self._toast("Narrative voice saved — it's pinned into every scene prompt.", "ok")

    def _cont_refresh_pdf_lbl(self):
        if not hasattr(self, "cont_pdf_lbl"):
            return
        if self._cont_pdfs:
            names = "\n".join(f"  {i + 1}. {os.path.basename(p)}"
                              for i, p in enumerate(self._cont_pdfs))
            self.cont_pdf_lbl.configure(text=f"{len(self._cont_pdfs)} PDF(s):\n{names}")
        else:
            self.cont_pdf_lbl.configure(text="No PDFs added yet.")

    def _cont_add_pdfs(self):
        if not PDF_OK:
            return messagebox.showerror(APP_TITLE, "Run: pip install pypdf")
        paths = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        for p in paths:
            if p not in self._cont_pdfs:
                self._cont_pdfs.append(p)
        self._cont_refresh_pdf_lbl()

    def _cont_clear_pdfs(self):
        self._cont_pdfs = []
        self._cont_refresh_pdf_lbl()

    def _cont_spin_preset(self, label):
        text = SPIN_PRESETS.get(label, "")
        self.cont_spin_txt.delete("1.0", "end")
        if text:
            self.cont_spin_txt.insert("1.0", text)

    def _cont_ingest(self):
        if not self._require_project():
            return
        if not self._cont_pdfs:
            return self._toast("Add at least one PDF first.", "err")
        if self.worker and self.worker.is_alive():
            return self._toast("Busy — wait for the current task.", "err")
        spin = self.cont_spin_txt.get("1.0", "end").strip()
        notes = self.cont_notes.get("1.0", "end").strip()
        paths = list(self._cont_pdfs)

        def job(engine):
            ing = continuation.CorpusIngest(
                self.project, engine.client, engine.model, self.style_lib,
                engine.s, self.bus.log, kill=self.kill)
            ing.run(paths, spin_directive=spin, extra_notes=notes)
            self.bus.q.put(("reload_story", None))
            self.bus.q.put(("pdf_list", None))

        self._run_worker("Corpus ingest", job)

    def _cont_write(self):
        if not self._require_project():
            return
        if not self.project.bible.get("continuation_mode"):
            return self._toast("Ingest a corpus first.", "err")
        if self.worker and self.worker.is_alive():
            return self._toast("Already generating.", "err")
        low, st = ram_is_low(float(self.settings.get("min_free_ram_gb", 2.5)))
        if low and not messagebox.askyesno(
                APP_TITLE, f"Only {st['available_gb']:.1f} GB RAM free. Continue anyway?"):
            return
        try:
            n_more = max(1, int(float(self.cont_n.get())))
            words = max(400, int(float(self.cont_w.get())))
        except Exception:
            return self._toast("Chapter / word counts must be numbers.", "err")
        self.project.state["target_words_per_chapter"] = words
        self.project.save()
        self.settings.update(self._gen_settings_snapshot() if hasattr(self, "sp_maxtok")
                             else {})
        self.kill.reset()
        self.stream_box_ensure()
        self._run_worker("Continuation",
                         lambda e: e.continue_run(n_more, words),
                         settings=dict(self.settings))

    def stream_box_ensure(self):
        """The live-output box lives on the Generate view; make sure it exists."""
        if not hasattr(self, "stream_box"):
            self._show("generate")

    # ==================================================================
    # GENERATE
    # ==================================================================
    def _build_generate(self, f):
        if not self.project:
            box = self._card(f, "Generate")
            ctk.CTkLabel(box, text="Open or create a project on the Home tab first.",
                         font=self.f_body, text_color=self.pal["text_dim"]).pack(
                anchor="w", padx=18, pady=16)
            return
        adv = self.settings.get("advanced_mode", False)
        c = self._card(f, "Generate")
        ctk.CTkLabel(c, text=self.project.scope_label(), font=self.f_body,
                     text_color=self.acc["primary"]).pack(anchor="w", padx=18, pady=(2, 0))
        self.gen_model_note = ctk.CTkLabel(c, text=self.catalog.describe(self.model_menu.get()),
                                           font=self.f_small, text_color=self.pal["text_dim"])
        self.gen_model_note.pack(anchor="w", padx=18)

        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=10)

        def spin(parent, label, val, frm, to, step=1, col=0):
            box = ctk.CTkFrame(parent, fg_color="transparent")
            box.grid(row=0, column=col, padx=(0, 18), sticky="w")
            ctk.CTkLabel(box, text=label, font=self.f_small,
                         text_color=self.pal["text_dim"]).pack(anchor="w")
            e = ctk.CTkEntry(box, font=self.f_body, width=110, fg_color=self.pal["surface_2"])
            e.insert(0, str(val))
            e.pack()
            return e

        st = self.project.state
        self.sp_chapters = spin(grid, "Target chapters", st.get("target_chapters", 30), 1, 500, col=0)
        self.sp_words = spin(grid, "Words / chapter", st.get("target_words_per_chapter", 3500),
                             300, 20000, col=1)
        self.sp_maxtok = spin(grid, "Max tokens / call", self.settings.get("max_tokens_per_call", 4096),
                              256, 32000, col=2)

        if adv:
            grid2 = ctk.CTkFrame(c, fg_color="transparent")
            grid2.pack(fill="x", padx=18, pady=(0, 6))
            self.sp_budget = spin(grid2, "Context budget", self.settings.get("context_budget", 24000),
                                  2000, 200000, col=0)
            self.sp_recent = spin(grid2, "Recent full chapters", st.get("recent_full_chapters", 2),
                                  1, 20, col=1)
            self.sp_ptemp = spin(grid2, "Prose temp", self.settings.get("prose_temperature", 0.9),
                                 0, 2, col=2)
            self.sp_stemp = spin(grid2, "Structure temp", self.settings.get("structure_temperature", 0.3),
                                 0, 2, col=3)
            togs = ctk.CTkFrame(c, fg_color="transparent")
            togs.pack(fill="x", padx=18, pady=4)
            self.v_codex = ctk.BooleanVar(value=self.settings.get("auto_codex", True))
            self.v_summary = ctk.BooleanVar(value=self.settings.get("auto_summary", True))
            ctk.CTkCheckBox(togs, text="auto-update codex", variable=self.v_codex,
                            font=self.f_small).pack(side="left", padx=8)
            ctk.CTkCheckBox(togs, text="auto-summarize chapters", variable=self.v_summary,
                            font=self.f_small).pack(side="left", padx=8)
        else:
            self.v_codex = ctk.BooleanVar(value=self.settings.get("auto_codex", True))
            self.v_summary = ctk.BooleanVar(value=self.settings.get("auto_summary", True))

        # control buttons
        ctr = ctk.CTkFrame(c, fg_color="transparent")
        ctr.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(ctr, text="Generate outline", font=self.f_body, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._gen_outline).pack(side="left", padx=4)
        self.btn_start = ctk.CTkButton(ctr, text="▶  Start / Resume", font=self.f_body,
                                       fg_color=self.acc["primary"], hover_color=self.acc["hover"],
                                       command=self._start_generation)
        self.btn_start.pack(side="left", padx=4)
        ctk.CTkButton(ctr, text="⏸  Soft stop", font=self.f_body, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._soft_stop).pack(side="left", padx=4)
        ctk.CTkButton(ctr, text="■  KILL NOW", font=self.f_body, fg_color=self.pal["bad"],
                      hover_color="#ff6b6b", text_color="#ffffff",
                      command=self._kill_now).pack(side="left", padx=12)
        self.v_keep_partial = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(ctr, text="keep partial on kill", variable=self.v_keep_partial,
                        font=self.f_small).pack(side="left")

        # progress
        pf = ctk.CTkFrame(c, fg_color="transparent")
        pf.pack(fill="x", padx=18, pady=(4, 0))
        self.prog_chapter = ctk.CTkProgressBar(pf, progress_color=self.acc["primary"])
        self.prog_chapter.set(0)
        self.prog_chapter.pack(fill="x", pady=3)
        self.prog_scene = ctk.CTkProgressBar(pf, progress_color=self.pal["text_dim"], height=6)
        self.prog_scene.set(0)
        self.prog_scene.pack(fill="x", pady=3)
        self.gen_status = ctk.CTkLabel(c, text="Idle.", font=self.f_small,
                                       text_color=self.pal["text_dim"])
        self.gen_status.pack(anchor="w", padx=18, pady=(2, 8))

        # live stream
        sc = self._card(f, "Live output")
        rowc = ctk.CTkFrame(sc, fg_color="transparent")
        rowc.pack(fill="x", padx=18)
        ctk.CTkButton(rowc, text="clear", font=self.f_small, width=60, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"],
                      command=lambda: self.stream_box.delete("1.0", "end")).pack(side="right")
        self.stream_box = ctk.CTkTextbox(sc, font=self.f_mono, height=340,
                                         fg_color="#0a0d12" if self.settings.get("theme") == "dark"
                                         else "#ffffff", wrap="word")
        self.stream_box.pack(fill="both", expand=True, padx=18, pady=(6, 16))

    def _gen_settings_snapshot(self):
        s = dict(self.settings)
        try:
            s["max_tokens_per_call"] = int(float(self.sp_maxtok.get()))
        except Exception:
            pass
        for attr, key, cast in (("sp_budget", "context_budget", int),
                                ("sp_ptemp", "prose_temperature", float),
                                ("sp_stemp", "structure_temperature", float)):
            if hasattr(self, attr):
                try:
                    s[key] = cast(float(getattr(self, attr).get()))
                except Exception:
                    pass
        s["auto_codex"] = self.v_codex.get()
        s["auto_summary"] = self.v_summary.get()
        return s

    def _start_generation(self):
        if not self._require_project():
            return
        if self.worker and self.worker.is_alive():
            return self._toast("Already generating.", "err")
        low, st = ram_is_low(float(self.settings.get("min_free_ram_gb", 2.5)))
        if low:
            if not messagebox.askyesno(
                    APP_TITLE,
                    f"Only {st['available_gb']:.1f} GB of RAM is free. Generation loads a "
                    "multi-GB model and may run the machine out of memory.\n\n"
                    "Close other apps or loaded models first. Start anyway?"):
                return self._toast("Generation held — free some RAM.", "err")
        if not hasattr(self, "e_title"):
            self._show("story")
            return self._toast("Set up the Story tab first, then come back.", "err")
        self._collect_story()
        self._save_outline()
        try:
            target = int(float(self.sp_chapters.get()))
            words = int(float(self.sp_words.get()))
        except Exception:
            return self._toast("Chapter / word targets must be numbers.", "err")
        self.project.state["target_chapters"] = target
        self.project.state["target_words_per_chapter"] = words
        if hasattr(self, "sp_recent"):
            try:
                self.project.state["recent_full_chapters"] = int(float(self.sp_recent.get()))
            except Exception:
                pass
        self.project.save()
        self.settings.update(self._gen_settings_snapshot())
        config.save_settings(self.settings)

        self.kill.reset()
        self.prog_chapter.set(self.project.chapter_count() / max(target, 1))
        self.stream_box.insert("end", f"\n\n{'='*60}\n▶ starting from chapter "
                                      f"{self.project.state.get('current_chapter', 0)+1}\n{'='*60}\n")
        self._run_worker("Generation", lambda e: e.run(target, words), settings=self._gen_settings_snapshot())

    def _soft_stop(self):
        self.kill.request_soft()
        self._toast("Soft stop — will halt after this chapter.")

    def _kill_now(self):
        self.kill.request_hard(keep_partial=self.v_keep_partial.get())
        self._toast("KILL — aborting the model stream now.", "err")

    # ==================================================================
    # SERIES
    # ==================================================================
    def _build_series(self, f):
        c = self._card(f, "Series")
        self._hint(c, "Group books into a series so later books inherit the earlier books' "
                      "codex and a synopsis as canon. You can also spin up the next book with "
                      "one click.")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=6)
        self.series_entry = ctk.CTkEntry(row, placeholder_text="series name…", font=self.f_body,
                                         width=240, fg_color=self.pal["surface_2"])
        self.series_entry.pack(side="left")
        ctk.CTkButton(row, text="Attach current project to this series", font=self.f_small,
                      fg_color=self.acc["primary"], hover_color=self.acc["hover"],
                      command=self._attach_series).pack(side="left", padx=8)

        self.series_pick = ctk.CTkOptionMenu(c, values=Series.list_all() or ["(none)"],
                                             font=self.f_small, fg_color=self.pal["surface_2"],
                                             button_color=self.acc["primary"],
                                             command=lambda _=None: self._refresh_series_view())
        self.series_pick.pack(anchor="w", padx=18, pady=6)
        self.series_info = ctk.CTkLabel(c, text="", font=self.f_small, justify="left",
                                        text_color=self.pal["text_dim"])
        self.series_info.pack(anchor="w", padx=18, pady=6)
        self._responsive_widget(self.series_info, "wrap")

        ir = ctk.CTkFrame(c, fg_color="transparent")
        ir.pack(fill="x", padx=18, pady=8)
        ctk.CTkButton(ir, text="Import earlier books as canon → current project", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._import_series_canon).pack(side="left")
        ctk.CTkButton(ir, text="Start next book", font=self.f_small,
                      fg_color=self.acc["primary"], hover_color=self.acc["hover"],
                      command=self._start_next_book).pack(side="left", padx=8)

    def _refresh_series_view(self):
        if not hasattr(self, "series_pick"):
            return
        names = Series.list_all() or ["(none)"]
        self.series_pick.configure(values=names)
        if self.series_pick.get() not in names:
            self.series_pick.set(names[0])
        name = self.series_pick.get()
        if name and name != "(none)":
            s = Series(name)
            books = s.data.get("books", [])
            self.series_info.configure(text=f"{len(books)} book(s): " +
                                       ", ".join(books) if books else "no books yet")

    def _attach_series(self):
        if not self._require_project():
            return
        name = self.series_entry.get().strip() or self.series_pick.get()
        if not name or name == "(none)":
            return self._toast("Name the series first.", "err")
        s = Series(name)
        s.add_book(self.project.name)
        self.project.bible["series"] = s.name
        self.project.bible["book_index"] = s.book_index_of(self.project.name)
        self.project.save()
        self._toast(f"'{self.project.name}' is book {self.project.bible['book_index']} of {s.name}.", "ok")
        self._refresh_series_view()

    def _import_series_canon(self):
        if not self._require_project():
            return
        s_name = self.project.bible.get("series") or self.series_pick.get()
        if not s_name or s_name == "(none)":
            return self._toast("Attach the project to a series first.", "err")
        s = Series(s_name)
        priors = [b for b in s.data.get("books", []) if b != self.project.name]
        priors = priors[:self.project.bible.get("book_index", len(priors) + 1) - 1] or priors
        if not priors:
            return self._toast("No earlier books to import.", "err")
        prior_projects = [Project(b) for b in priors]
        self._run_worker("Series canon import",
                         lambda e: e.import_series_canon(prior_projects))

    def _start_next_book(self):
        s_name = (self.project.bible.get("series") if self.project else "") or self.series_pick.get()
        if not s_name or s_name == "(none)":
            return self._toast("Pick or attach a series first.", "err")
        s = Series(s_name)
        idx = len(s.data.get("books", [])) + 1
        new_name = f"{s.name}_book_{idx}"
        proj = Project(new_name)
        proj.bible["series"] = s.name
        proj.bible["book_index"] = idx
        if self.project:
            proj.bible["genre"] = self.project.bible.get("genre", "")
        proj.save()
        s.add_book(new_name)
        prior_projects = [Project(b) for b in s.data["books"][:-1]]
        self.project = proj
        self.header_project.configure(text=proj.bible.get("title") or new_name)
        if prior_projects:
            self._run_worker("Series canon import",
                             lambda e: e.import_series_canon(prior_projects))
        self._toast(f"Created {new_name}. Set its plot on the Story tab, then Generate.", "ok")
        for k in ("story", "world", "generate"):
            if k in self._views:
                self._views[k].destroy()
                del self._views[k]
        self._show("story")

    # ==================================================================
    # EXPORT  ·  books, cover art, audiobooks
    # ==================================================================
    def _build_export(self, f):
        # ---------------- books ----------------
        c = self._card(f, "Export a book")
        self._hint(c, "EPUB (separate chapter documents, a real TOC and metadata), PDF "
                      "(the styled export, using the cover below) and plain TXT. "
                      "'Whole series' runs the very same export over every book attached "
                      "to a series, into one folder.")
        if not bookexport.EPUB_OK:
            self._hint(c, bookexport.PIP_HINTS["epub"])
        if not pdfexport.REPORTLAB_OK:
            self._hint(c, bookexport.PIP_HINTS["pdf"])

        trow = ctk.CTkFrame(c, fg_color="transparent")
        trow.pack(fill="x", padx=18, pady=(0, 6))
        self.exp_target = ctk.CTkSegmentedButton(
            trow, values=["This book", "Whole series"], font=self.f_small,
            command=lambda _v=None: self._refresh_export_view())
        self.exp_target.set("This book")
        self.exp_target.pack(side="left")
        self.exp_series = ctk.CTkOptionMenu(trow, values=Series.list_all() or ["(none)"],
                                            font=self.f_small, width=200,
                                            fg_color=self.pal["surface_2"],
                                            button_color=self.acc["primary"],
                                            command=lambda _v=None: self._refresh_export_view())
        self.exp_series.pack(side="left", padx=10)

        frow = ctk.CTkFrame(c, fg_color="transparent")
        frow.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(frow, text="Formats", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        want = self.settings.get("export_formats") or ["epub"]
        self.v_fmt = {}
        for fmt in bookexport.FORMATS:
            self.v_fmt[fmt] = ctk.BooleanVar(value=fmt in want)
            ctk.CTkCheckBox(frow, text=fmt.upper(), variable=self.v_fmt[fmt],
                            font=self.f_small, width=80).pack(side="left", padx=6)

        self.e_export_dir = self._labeled_entry(
            c, "Output folder", self.settings.get("export_dir", ""))
        brow = ctk.CTkFrame(c, fg_color="transparent")
        brow.pack(fill="x", padx=18, pady=(0, 4))
        ctk.CTkLabel(brow, text="", width=180).pack(side="left")
        ctk.CTkButton(brow, text="Browse…", font=self.f_small, width=90,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._exp_pick_dir).pack(side="left")
        ctk.CTkLabel(brow, text="blank = <project>/export/", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=8)

        erow = ctk.CTkFrame(c, fg_color="transparent")
        erow.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(erow, text="⬇  Export", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._do_export).pack(side="left")
        ctk.CTkButton(erow, text="Open output folder", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._exp_open_dir).pack(side="left", padx=8)
        self.exp_status = ctk.CTkLabel(erow, text="", font=self.f_small,
                                       text_color=self.pal["text_dim"])
        self.exp_status.pack(side="left", padx=10)

        if not self.project:
            box = self._card(f, "Cover art & audiobook")
            ctk.CTkLabel(box, text="Open or create a project on the Home tab to make a "
                                   "cover or an audiobook.", font=self.f_body,
                         text_color=self.pal["text_dim"]).pack(anchor="w", padx=18, pady=16)
            return

        # ---------------- cover art ----------------
        cv = self._card(f, "Cover art")
        self._hint(cv, "Import your own image, or generate one instantly from the title, "
                       "genre and your accent colour — no model, no network. The chosen "
                       "cover is embedded in the EPUB and printed on the PDF title page.")
        cbody = ctk.CTkFrame(cv, fg_color="transparent")
        cbody.pack(fill="x", padx=18, pady=(0, 10))
        self.cover_preview = ctk.CTkLabel(cbody, text="no cover", width=150, height=225,
                                          fg_color=self.pal["surface_2"], corner_radius=8,
                                          font=self.f_small, text_color=self.pal["text_dim"])
        self.cover_preview.pack(side="left", padx=(0, 16))
        cctl = ctk.CTkFrame(cbody, fg_color="transparent")
        cctl.pack(side="left", fill="x", expand=True)
        self.cover_path_lbl = ctk.CTkLabel(cctl, text="", font=self.f_small, justify="left",
                                           text_color=self.pal["text_dim"])
        self.cover_path_lbl.pack(anchor="w", pady=(0, 8))
        self._responsive_widget(self.cover_path_lbl, "wrap")

        r1 = ctk.CTkFrame(cctl, fg_color="transparent")
        r1.pack(anchor="w", pady=3)
        ctk.CTkButton(r1, text="Import image…", font=self.f_small, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._cover_import).pack(side="left")
        ctk.CTkButton(r1, text="✦ Quick generate", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._cover_quick).pack(side="left", padx=6)
        self.opt_cover_style = ctk.CTkOptionMenu(r1, values=["gradient", "duotone", "minimal"],
                                                 font=self.f_small, width=110,
                                                 fg_color=self.pal["surface_2"],
                                                 button_color=self.acc["primary"])
        self.opt_cover_style.set(self.settings.get("cover_style", "gradient"))
        self.opt_cover_style.pack(side="left", padx=6)

        r2 = ctk.CTkFrame(cctl, fg_color="transparent")
        r2.pack(anchor="w", pady=3)
        ctk.CTkButton(r2, text="Edit cover…", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._cover_edit_dialog).pack(side="left")
        ctk.CTkButton(r2, text="Remove", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._cover_clear).pack(side="left", padx=6)
        ctk.CTkButton(r2, text="✧ AI generate", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=self._cover_ai).pack(side="left", padx=6)
        ctk.CTkLabel(r2, text=("diffusers ready" if bookexport.DIFFUSERS_OK else "diffusers not installed"),
                     font=self.f_small,
                     text_color=self.pal["good"] if bookexport.DIFFUSERS_OK else self.pal["text_dim"]
                     ).pack(side="left", padx=6)

        # ---------------- audiobook ----------------
        ab = self._card(f, "Audiobook  ·  local Piper TTS")
        if not audiobook.PIPER_OK:
            self._hint(ab, audiobook.PIPER_HINT)
        self._hint(ab, "Fully offline neural narration. Voice models download once "
                       "(~60-110 MB each) into ~/NovelMakerData/tts_voices/ and are reused "
                       "forever after. Give each character their own voice and quoted "
                       "dialogue is routed to them; anything the attributor can't place "
                       "stays with the narrator. Chapters are stitched with ffmpeg into a "
                       "single tagged, chaptered file under <project>/audiobook/.")

        nrow = ctk.CTkFrame(ab, fg_color="transparent")
        nrow.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(nrow, text="Narrator", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        vmap = audiobook.load_voice_map(self.project, self.settings)
        self.opt_narrator = ctk.CTkOptionMenu(nrow, values=audiobook.VOICE_LABELS,
                                              font=self.f_small, width=340,
                                              fg_color=self.pal["surface_2"],
                                              button_color=self.acc["primary"])
        self.opt_narrator.set(audiobook.id_to_label(vmap.get("narrator")))
        self.opt_narrator.pack(side="left")
        ctk.CTkButton(nrow, text="▷ hear it", font=self.f_small, width=80,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=lambda: self._tts_preview(self.opt_narrator.get())).pack(side="left", padx=6)

        mrow = ctk.CTkFrame(ab, fg_color="transparent")
        mrow.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(mrow, text="Narration", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.opt_tts_mode = ctk.CTkOptionMenu(
            mrow, values=[audiobook.MODE_LABELS[m] for m in audiobook.MODES],
            font=self.f_small, width=400, fg_color=self.pal["surface_2"],
            button_color=self.acc["primary"], command=lambda _v=None: self._tts_mode_changed())
        self.opt_tts_mode.set(audiobook.MODE_LABELS[audiobook.narration_mode(self.settings, vmap)])
        self.opt_tts_mode.pack(side="left")

        orow = ctk.CTkFrame(ab, fg_color="transparent")
        orow.pack(fill="x", padx=18, pady=6)
        self.v_tts_split = ctk.BooleanVar(value=self.settings.get("tts_per_character_voices", True))
        self.v_tts_announce = ctk.BooleanVar(value=self.settings.get("tts_announce_chapter", True))
        ctk.CTkCheckBox(orow, text="announce chapter numbers", variable=self.v_tts_announce,
                        font=self.f_small).pack(side="left", padx=12)
        ctk.CTkLabel(orow, text="format", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(12, 4))
        self.opt_tts_fmt = ctk.CTkOptionMenu(orow, values=list(audiobook.AUDIO_FORMATS),
                                             font=self.f_small, width=80,
                                             fg_color=self.pal["surface_2"],
                                             button_color=self.acc["primary"])
        self.opt_tts_fmt.set(self.settings.get("tts_format", "m4a"))
        self.opt_tts_fmt.pack(side="left")
        ctk.CTkLabel(orow, text="speed", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(12, 4))
        self.e_tts_speed = ctk.CTkEntry(orow, width=56, font=self.f_body,
                                        fg_color=self.pal["surface_2"])
        self.e_tts_speed.insert(0, str(self.settings.get("tts_speed", 1.0)))
        self.e_tts_speed.pack(side="left")
        ctk.CTkLabel(orow, text="expression", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(12, 4))
        self.sl_tts_var = ctk.CTkSlider(orow, from_=0.5, to=1.1, number_of_steps=12, width=120)
        self.sl_tts_var.set(float(self.settings.get("tts_variation", 0.85)))
        self.sl_tts_var.pack(side="left")
        self._hint(ab, "'Expression' varies phoneme timing — the main cure for a flat, "
                       "robotic read. Turn it up for narration, down if a voice starts "
                       "slurring. The ★ high-quality voices sound markedly more human than "
                       "the (fast) ones; they render at roughly 5× realtime on this CPU "
                       "instead of 20×, which is still far faster than listening.")

        crow = ctk.CTkFrame(ab, fg_color="transparent")
        crow.pack(fill="x", padx=18, pady=(10, 2))
        ctk.CTkLabel(crow, text="Character voices (from the World Codex)", font=self.f_body,
                     text_color=self.pal["text"]).pack(side="left")
        ctk.CTkButton(crow, text="✦ Auto-cast with the model", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._auto_cast).pack(side="left", padx=10)
        ctk.CTkButton(crow, text="Clear", font=self.f_small, width=60,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=lambda: self._build_voice_rows(
                          {"narrator": audiobook.label_to_id(self.opt_narrator.get()),
                           "characters": {}})).pack(side="left")
        ctk.CTkButton(crow, text="⚙ Manage voice models…", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._manage_voices).pack(side="right")
        self.voice_rows_frame = ctk.CTkScrollableFrame(ab, fg_color=self.pal["surface_2"],
                                                       height=190)
        self.voice_rows_frame.pack(fill="x", padx=18, pady=(0, 8))
        self.voice_menus, self.pitch_menus = {}, {}
        self._build_voice_rows(vmap)
        self._tts_mode_changed()

        arow = ctk.CTkFrame(ab, fg_color="transparent")
        arow.pack(fill="x", padx=18, pady=10)
        ctk.CTkButton(arow, text="🎧  Render audiobook", font=self.f_body,
                      fg_color=self.acc["primary"], hover_color=self.acc["hover"],
                      command=self._do_audiobook).pack(side="left")
        ctk.CTkButton(arow, text="⏸ Soft stop", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"],
                      command=lambda: (self.job_kill.request_soft(),
                                       self._toast("Audio job stops after this chapter."))
                      ).pack(side="left", padx=6)
        ctk.CTkButton(arow, text="■ Cancel", font=self.f_small, fg_color=self.pal["bad"],
                      hover_color="#ff6b6b", text_color="#ffffff",
                      command=lambda: (self.job_kill.request_hard(),
                                       self._toast("Audio job cancelling…", "err"))
                      ).pack(side="left", padx=6)
        ctk.CTkButton(arow, text="Open audiobook folder", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=lambda: config.open_in_file_manager(
                          os.path.join(self.project.dir, "audiobook"))).pack(side="left", padx=6)

        self.tts_prog = ctk.CTkProgressBar(ab, progress_color=self.acc["primary"])
        self.tts_prog.set(0)
        self.tts_prog.pack(fill="x", padx=18, pady=(2, 4))
        self.tts_status = ctk.CTkLabel(ab, text="Idle.", font=self.f_small,
                                       text_color=self.pal["text_dim"])
        self.tts_status.pack(anchor="w", padx=18, pady=(0, 14))

    def _build_voice_rows(self, vmap):
        for w in self.voice_rows_frame.winfo_children():
            w.destroy()
        self.voice_menus, self.pitch_menus = {}, {}
        names = audiobook.character_names(self.project)
        if not names:
            ctk.CTkLabel(self.voice_rows_frame,
                         text="No characters in the codex yet — the whole book will be read "
                              "by the narrator.", font=self.f_small,
                         text_color=self.pal["text_dim"]).pack(anchor="w", padx=8, pady=8)
            return
        chosen = vmap.get("characters", {})
        infl = vmap.get("inflections", {})
        for name in names:
            row = ctk.CTkFrame(self.voice_rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=name, font=self.f_small, width=170, anchor="w",
                         text_color=self.pal["text"]).pack(side="left", padx=(6, 4))
            # full-cast mode picks a model; narrator-does-voices picks a pitch.
            # Both live in the row and _tts_mode_changed shows the relevant one.
            m = ctk.CTkOptionMenu(row, values=["(narrator)"] + audiobook.VOICE_LABELS,
                                  font=self.f_small, width=330,
                                  fg_color=self.pal["surface"],
                                  button_color=self.acc["primary"])
            m.set(audiobook.id_to_label(chosen[name]) if chosen.get(name) else "(narrator)")
            pm = ctk.CTkOptionMenu(row, values=audiobook.INFLECTION_LABELS,
                                   font=self.f_small, width=330,
                                   fg_color=self.pal["surface"],
                                   button_color=self.acc["primary"])
            pm.set(audiobook.label_for_inflection(infl.get(name)))
            ctk.CTkButton(row, text="▷", font=self.f_small, width=32,
                          fg_color=self.pal["surface"], hover_color=self.pal["border"],
                          command=lambda n=name: self._preview_character(n)).pack(side="right", padx=4)
            m.pack(side="left")
            self.voice_menus[name] = m
            self.pitch_menus[name] = pm

    def _preview_character(self, name):
        """Audition exactly what this character will sound like in the current mode."""
        mode = self._tts_mode()
        if mode == "cast":
            v = self.voice_menus[name].get()
            return self._tts_preview(v)
        pitch, pace = 1.0, 1.0
        if mode == "narrator_voices":
            pitch, pace = (audiobook.inflection_from_label(self.pitch_menus[name].get())
                           or audiobook.inflection_for(name, self._peek_voice_map()))
        self._tts_preview(self.opt_narrator.get(), pitch=pitch, pace=pace)

    def _peek_voice_map(self):
        return {"characters": {n: self.voice_menus[n].get() for n in self.voice_menus},
                "inflections": {}}

    def _tts_mode(self):
        chosen = self.opt_tts_mode.get()
        for m in audiobook.MODES:
            if audiobook.MODE_LABELS[m] == chosen:
                return m
        return "cast"

    def _tts_mode_changed(self):
        """Only full-cast mode uses the per-character voice models, so grey the
        list out otherwise rather than letting it lie about what will be heard."""
        mode = self._tts_mode()
        for name, m in self.voice_menus.items():
            pm = self.pitch_menus.get(name)
            try:
                if mode == "cast":
                    if pm is not None:
                        pm.pack_forget()
                    m.pack(side="left")
                    m.configure(state="normal")
                elif mode == "narrator_voices":
                    m.pack_forget()
                    if pm is not None:
                        pm.pack(side="left")
                        pm.configure(state="normal")
                else:
                    m.pack(side="left")
                    m.configure(state="disabled")
                    if pm is not None:
                        pm.pack_forget()
            except Exception:
                pass
        note = {"single": "One voice reads the whole book — the character list is ignored.",
                "cast": "Each character below gets their own voice model.",
                "narrator_voices": "The narrator reads everyone, pitch- and pace-shifted "
                                   "per character — one model, several apparent voices."}
        if hasattr(self, "tts_status"):
            self.tts_status.configure(text=note.get(mode, ""))

    def _collect_voice_map(self):
        vmap = {"narrator": audiobook.label_to_id(self.opt_narrator.get()),
                "mode": self._tts_mode(), "characters": {}, "inflections": {}}
        for name, menu in self.voice_menus.items():
            v = menu.get()
            if v and v != "(narrator)":
                vmap["characters"][name] = audiobook.label_to_id(v)
            pv = audiobook.inflection_from_label(self.pitch_menus[name].get())
            if pv:
                vmap["inflections"][name] = list(pv)
        audiobook.save_voice_map(self.project, vmap)
        return vmap

    def _auto_cast(self):
        """Let the local model read the codex and pick a voice per character."""
        if not self._require_project():
            return
        if not self.voice_menus:
            return self._toast("No codex characters to cast.", "err")
        if self._tts_mode() != "cast":
            self.opt_tts_mode.set(audiobook.MODE_LABELS["cast"])
            self._tts_mode_changed()
        project, client, model = self.project, self.client, self.model_menu.get()
        s = dict(self.settings)

        def job(_engine=None):
            cast = audiobook.cast_voices(project, client, model, settings=s, log=self.bus.log,
                                         temperature=s.get("structure_temperature", 0.3))
            self.bus.q.put(("voice_cast", cast))
        # goes through the generation worker so it queues behind Jan like every
        # other model call rather than racing one
        self._run_worker("Voice casting", job)

    def _apply_cast(self, cast):
        vmap = {"narrator": cast.get("narrator") or audiobook.label_to_id(self.opt_narrator.get()),
                "mode": "cast", "characters": cast.get("characters", {})}
        self.opt_narrator.set(audiobook.id_to_label(vmap["narrator"]))
        self._build_voice_rows(vmap)
        self._tts_mode_changed()
        audiobook.save_voice_map(self.project, vmap)
        self._toast(f"Cast {len(vmap['characters'])} characters.", "ok")

    def _manage_voices(self):
        """Downloaded voice models are by far the biggest thing NovelForge stores,
        so they get a plain list with sizes and a delete button."""
        win = ctk.CTkToplevel(self)
        win.title("Voice models")
        win.geometry("620x520")
        win.configure(fg_color=self.pal["bg"])
        win.transient(self)
        ctk.CTkLabel(win, text="Downloaded voice models", font=self.f_h2,
                     text_color=self.pal["text"]).pack(anchor="w", padx=18, pady=(16, 2))
        total_lbl = ctk.CTkLabel(win, text="", font=self.f_small,
                                 text_color=self.pal["text_dim"], justify="left")
        total_lbl.pack(anchor="w", padx=18)
        listing = ctk.CTkScrollableFrame(win, fg_color=self.pal["surface"], height=330)
        listing.pack(fill="both", expand=True, padx=18, pady=10)

        def refresh():
            for w in listing.winfo_children():
                w.destroy()
            rows = audiobook.installed_report(self.settings)
            total = audiobook.voices_total_bytes(self.settings)
            total_lbl.configure(
                text=f"{len(rows)} installed · {total / 1e9:.2f} GB in "
                     f"{audiobook.voices_dir(self.settings)}\nDeleting one is safe — it "
                     f"re-downloads automatically the next time you use it.")
            if not rows:
                ctk.CTkLabel(listing, text="Nothing downloaded yet.", font=self.f_body,
                             text_color=self.pal["text_dim"]).pack(anchor="w", padx=10, pady=10)
                return
            for vid, desc, size, known in rows:
                row = ctk.CTkFrame(listing, fg_color="transparent")
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(row, text=f"{size / 1e6:.0f} MB", font=self.f_small, width=70,
                             anchor="e", text_color=self.pal["text_dim"]).pack(side="left", padx=6)
                info = ctk.CTkFrame(row, fg_color="transparent")
                info.pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(info, text=vid, font=self.f_small, anchor="w",
                             text_color=self.pal["text"]).pack(anchor="w")
                ctk.CTkLabel(info, text=desc + ("" if known else "   (not in the voice list)"),
                             font=self.f_small, anchor="w",
                             text_color=self.pal["text_dim"]).pack(anchor="w")
                ctk.CTkButton(row, text="▷", font=self.f_small, width=32,
                              fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                              state="disabled" if vid.endswith(":*") else "normal",
                              command=lambda v=vid: self._tts_preview(v)).pack(side="right", padx=4)
                ctk.CTkButton(row, text="Delete", font=self.f_small, width=70,
                              fg_color=self.pal["surface_2"], hover_color=self.pal["bad"],
                              command=lambda v=vid, d=desc: do_delete(v, d)).pack(side="right")

        def do_delete(vid, desc):
            if vid == "kokoro:*":
                msg = ("Delete the whole Kokoro engine (354 MB)? That removes all 54 "
                       "realistic voices at once. They re-download together on next use.")
            else:
                msg = f"Delete {vid}?\n{desc}\n\nIt re-downloads automatically when next used."
            if not messagebox.askyesno(APP_TITLE, msg, parent=win):
                return
            try:
                n = audiobook.delete_voice(vid, self.settings)
                self._toast(f"Deleted {vid} ({n} file(s)).", "ok")
            except Exception as e:
                messagebox.showerror(APP_TITLE, str(e), parent=win)
            refresh()

        brow = ctk.CTkFrame(win, fg_color="transparent")
        brow.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkButton(brow, text="Clear voice samples", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=lambda: (audiobook.clear_previews(self.settings), refresh())
                      ).pack(side="left")
        ctk.CTkButton(brow, text="Open folder", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=lambda: config.open_in_file_manager(
                          audiobook.voices_dir(self.settings))).pack(side="left", padx=8)
        ctk.CTkButton(brow, text="Close", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=win.destroy).pack(side="right")
        refresh()

    def _refresh_export_view(self):
        if not hasattr(self, "exp_target"):
            return
        try:
            names = Series.list_all() or ["(none)"]
            self.exp_series.configure(values=names)
            if self.exp_series.get() not in names:
                self.exp_series.set(names[0])
            series_mode = self.exp_target.get() == "Whole series"
            self.exp_series.configure(state="normal" if series_mode else "disabled")
            if series_mode:
                s = Series(self.exp_series.get()) if self.exp_series.get() != "(none)" else None
                n = len(s.data.get("books", [])) if s else 0
                self.exp_status.configure(text=f"{n} book(s) in this series")
            elif self.project:
                self.exp_status.configure(
                    text=f"{self.project.chapter_count()} chapters · "
                         f"{self.project.total_words():,} words")
            else:
                self.exp_status.configure(text="no project open")
        except Exception:
            pass
        self._refresh_cover_preview()

    def _refresh_cover_preview(self):
        if not (self.project and hasattr(self, "cover_preview")):
            return
        try:
            if not self.cover_preview.winfo_exists():
                return
        except Exception:
            return
        path = bookexport.cover_for(self.project)
        if not path:
            self._cover_img = None
            self.cover_preview.configure(image=None, text="no cover")
            self.cover_path_lbl.configure(text="No cover chosen. The EPUB and PDF still "
                                               "export fine without one.")
            return
        self.cover_path_lbl.configure(text=path)
        if not bookexport.PIL_OK:
            return
        try:
            from PIL import Image
            im = Image.open(path)
            im.thumbnail((150, 225))
            self._cover_img = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
            self.cover_preview.configure(image=self._cover_img, text="")
        except Exception as e:
            self.cover_preview.configure(image=None, text="preview failed")
            self.cover_path_lbl.configure(text=f"{path}\n({e})")

    # ---------- export actions ----------
    def _exp_formats(self):
        return [f for f in bookexport.FORMATS if self.v_fmt[f].get()]

    def _exp_pick_dir(self):
        d = filedialog.askdirectory(title="Export folder")
        if d:
            self.e_export_dir.delete(0, "end")
            self.e_export_dir.insert(0, d)

    def _exp_settings(self):
        """Persist the tab's choices into settings and hand them to the worker."""
        self.settings["export_formats"] = self._exp_formats() or ["epub"]
        self.settings["export_dir"] = self.e_export_dir.get().strip()
        if hasattr(self, "opt_cover_style"):
            self.settings["cover_style"] = self.opt_cover_style.get()
        if hasattr(self, "opt_tts_fmt"):
            self.settings["tts_format"] = self.opt_tts_fmt.get()
            self.settings["tts_mode"] = self._tts_mode()
            self.settings["tts_per_character_voices"] = self._tts_mode() != "single"
            self.settings["tts_announce_chapter"] = self.v_tts_announce.get()
            try:
                self.settings["tts_speed"] = max(0.5, min(2.0, float(self.e_tts_speed.get())))
            except Exception:
                pass
            self.settings["tts_variation"] = round(float(self.sl_tts_var.get()), 2)
        if hasattr(self, "opt_narrator"):
            self.settings["tts_voice"] = audiobook.label_to_id(self.opt_narrator.get())
        config.save_settings(self.settings)
        return dict(self.settings)

    def _exp_output_dir(self):
        d = self.e_export_dir.get().strip() if hasattr(self, "e_export_dir") else ""
        if d:
            return d
        if self.exp_target.get() == "Whole series":
            name = self.exp_series.get()
            return os.path.join(config.DATA_ROOT, "exports",
                                name if name != "(none)" else "series")
        return os.path.join(self.project.dir, "export") if self.project else config.DATA_ROOT

    def _exp_open_dir(self):
        d = self._exp_output_dir()
        os.makedirs(d, exist_ok=True)
        config.open_in_file_manager(d)

    def _do_export(self):
        formats = self._exp_formats()
        if not formats:
            return self._toast("Tick at least one format.", "err")
        s = self._exp_settings()
        out_dir = self._exp_output_dir()
        series_mode = self.exp_target.get() == "Whole series"
        if series_mode:
            name = self.exp_series.get()
            if not name or name == "(none)":
                return self._toast("Pick a series first.", "err")

            def job():
                self.bus.log(f"Exporting series '{name}' as {', '.join(f.upper() for f in formats)}…")
                bookexport.export_series(name, formats, settings=s, log=self.bus.log,
                                         kill=self.job_kill, out_dir=out_dir)
                self.bus.q.put(("export_done", out_dir))
            return self._run_bg("Series export", job)

        if not self._require_project():
            return
        if self.project.chapter_count() == 0:
            return self._toast("No chapters written yet.", "err")
        project = self.project

        def job():
            self.bus.log(f"Exporting '{bookexport.book_title(project)}' as "
                         f"{', '.join(f.upper() for f in formats)}…")
            bookexport.export_book(project, formats, settings=s, log=self.bus.log,
                                   out_dir=out_dir)
            self.bus.q.put(("export_done", out_dir))
        self._run_bg("Export", job)

    # ---------- cover actions ----------
    def _cover_import(self):
        if not self._require_project():
            return
        p = filedialog.askopenfilename(
            title="Choose a cover image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if not p:
            return
        try:
            bookexport.import_cover(self.project, p)
            self._refresh_cover_preview()
            self._toast("Cover imported.", "ok")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def _cover_quick(self):
        if not self._require_project():
            return
        if not bookexport.PIL_OK:
            return messagebox.showerror(APP_TITLE, bookexport.PIP_HINTS["cover"])
        s = self._exp_settings()
        project = self.project
        style = self.opt_cover_style.get()
        out = os.path.join(project.dir, "cover.png")

        def job():
            self.bus.log("Generating a cover…")
            bookexport.quick_cover(project, out, accent_hex=self.acc["primary"],
                                   dark=self.settings.get("theme", "dark") == "dark",
                                   style=style,
                                   width=int(s.get("cover_width", 1600)),
                                   height=int(s.get("cover_height", 2400)),
                                   author=s.get("author_name", ""))
            self.bus.q.put(("cover_done", out))
        self._run_bg("Cover", job, warn_if_generating=False)

    def _cover_clear(self):
        if not self._require_project():
            return
        bookexport.set_cover(self.project, "")
        self._refresh_cover_preview()
        self._toast("Cover removed from this book (the file is left on disk).")

    def _cover_ai(self):
        if not self._require_project():
            return
        if not bookexport.DIFFUSERS_OK:
            return messagebox.showinfo(APP_TITLE, bookexport.AI_COVER_HINT)
        if not messagebox.askyesno(APP_TITLE, "Local diffusion on a CPU-only machine takes "
                                              "several minutes and a lot of RAM. Continue?"):
            return
        project = self.project
        out = os.path.join(project.dir, "cover_ai.png")
        self._run_bg("AI cover", lambda: (bookexport.ai_cover(project, out, log=self.bus.log),
                                          self.bus.q.put(("cover_done", out))))

    def _cover_edit_dialog(self):
        if not self._require_project():
            return
        src = bookexport.cover_for(self.project)
        if not src:
            return self._toast("Choose or generate a cover first.", "err")
        if not bookexport.PIL_OK:
            return messagebox.showerror(APP_TITLE, bookexport.PIP_HINTS["cover"])

        win = ctk.CTkToplevel(self)
        win.title("Edit cover")
        win.geometry("460x420")
        win.configure(fg_color=self.pal["bg"])
        win.transient(self)
        ctk.CTkLabel(win, text="Edit cover", font=self.f_h2,
                     text_color=self.pal["text"]).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(win, text="Applied to a copy — the original file is left alone.",
                     font=self.f_small, text_color=self.pal["text_dim"]).pack(anchor="w", padx=18)

        v_crop = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(win, text="crop to 2:3 cover ratio", variable=v_crop,
                        font=self.f_small).pack(anchor="w", padx=18, pady=(14, 4))

        sliders = {}
        for key, label in (("brightness", "Brightness"), ("contrast", "Contrast")):
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(row, text=label, font=self.f_small, width=90, anchor="w",
                         text_color=self.pal["text"]).pack(side="left")
            val = ctk.CTkLabel(row, text="1.00", font=self.f_small,
                               text_color=self.pal["text_dim"])
            sl = ctk.CTkSlider(row, from_=0.4, to=1.8, number_of_steps=28, width=230,
                               command=lambda v, l=val: l.configure(text=f"{v:.2f}"))
            sl.set(1.0)
            sl.pack(side="left", padx=8)
            val.pack(side="left")
            sliders[key] = sl

        e_title = self._labeled_entry(win, "Title overlay", "", width=210)
        e_author = self._labeled_entry(win, "Author overlay",
                                       self.settings.get("author_name", ""), width=210)
        ctk.CTkLabel(win, text="Leave both blank for no text overlay.", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(anchor="w", padx=18)

        def apply_edit():
            out = os.path.join(self.project.dir, "cover_edited.png")
            try:
                bookexport.edit_cover(
                    src, out, crop_ratio=bookexport.COVER_RATIO if v_crop.get() else None,
                    brightness=float(sliders["brightness"].get()),
                    contrast=float(sliders["contrast"].get()),
                    title_text=e_title.get().strip(), author_text=e_author.get().strip(),
                    accent_hex=self.acc["primary"])
                bookexport.set_cover(self.project, out)
                self._refresh_cover_preview()
                self._toast("Cover edited.", "ok")
                win.destroy()
            except Exception as e:
                messagebox.showerror(APP_TITLE, str(e))

        brow = ctk.CTkFrame(win, fg_color="transparent")
        brow.pack(fill="x", padx=18, pady=16)
        ctk.CTkButton(brow, text="Apply", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=apply_edit).pack(side="left")
        ctk.CTkButton(brow, text="Cancel", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"], command=win.destroy).pack(side="left", padx=8)

    # ---------- audiobook actions ----------
    def _tts_preview(self, label, pitch=1.0, pace=1.0):
        if not (audiobook.PIPER_OK or audiobook.KOKORO_OK):
            return messagebox.showerror(APP_TITLE, audiobook.PIPER_HINT)
        vid = audiobook.label_to_id(label)
        if not label or label == "(narrator)":
            vid = audiobook.label_to_id(self.opt_narrator.get())
        s = self._exp_settings()

        def job():
            self.bus.log(f"Preparing a sample of {vid}…")
            tag = vid.replace("#", "_").replace(":", "-")
            if abs(pitch - 1.0) > 1e-3 or abs(pace - 1.0) > 1e-3:
                tag += f"_{pitch:.2f}x{pace:.2f}"
            path = os.path.join(audiobook.voices_dir(s), "_preview_" + tag + ".wav")
            audiobook.preview_voice(vid, path, settings=s, log=self.bus.log,
                                    pitch=pitch, pace=pace)
            for player in ("ffplay", "paplay", "aplay"):
                exe = shutil.which(player)
                if not exe:
                    continue
                args = [exe, "-nodisp", "-autoexit", "-loglevel", "quiet", path] \
                    if player == "ffplay" else [exe, path]
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            self.bus.log(f"  no audio player found — sample saved at {path}")
        self._run_bg("Voice sample", job, warn_if_generating=False)

    def _do_audiobook(self):
        if not self._require_project():
            return
        if not audiobook.PIPER_OK:
            return messagebox.showerror(APP_TITLE, audiobook.PIPER_HINT)
        if self.project.chapter_count() == 0:
            return self._toast("No chapters written yet.", "err")
        low, st = ram_is_low(float(self.settings.get("min_free_ram_gb", 2.5)))
        if low and not messagebox.askyesno(
                APP_TITLE, f"Only {st['available_gb']:.1f} GB RAM free. Rendering loads one "
                           "voice model per speaker (~60-110 MB each) and pins a CPU core. "
                           "Continue anyway?"):
            return self._toast("Audiobook held — free some RAM.", "err")
        s = self._exp_settings()
        vmap = self._collect_voice_map()
        project = self.project
        wanted = [vmap["narrator"]]
        if vmap.get("mode") == "cast":
            wanted += list(vmap["characters"].values())
        missing = {v for v in wanted if not audiobook.voice_installed(v, s)}
        if missing:
            self.bus.log(f"{len(missing)} voice model(s) will download first "
                         f"(one-off, ~{sum(354 if v.startswith('kokoro') else 90 for v in missing)} MB).")

        def job():
            self.bus.log(f"Rendering audiobook for '{bookexport.book_title(project)}'…")
            out = audiobook.build_audiobook(
                project, s, vmap, log=self.bus.log, progress=self.bus.progress,
                kill=self.job_kill, keep_wavs=s.get("tts_keep_chapter_wavs", False))
            self.bus.q.put(("audiobook_done", out))
        self._run_bg("Audiobook", job)

    # ==================================================================
    # SETTINGS
    # ==================================================================
    def _build_settings(self, f):
        c = self._card(f, "Settings")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=8)
        self.v_advanced = ctk.BooleanVar(value=self.settings.get("advanced_mode", False))
        ctk.CTkSwitch(row, text="Advanced mode (show all generation controls)",
                      variable=self.v_advanced, font=self.f_body,
                      command=self._save_settings_form).pack(anchor="w", pady=4)
        self.v_strip = ctk.BooleanVar(value=self.settings.get("strip_reasoning", True))
        ctk.CTkSwitch(row, text="Strip <think> reasoning blocks from model output",
                      variable=self.v_strip, font=self.f_body,
                      command=self._save_settings_form).pack(anchor="w", pady=4)
        self.v_degen = ctk.BooleanVar(value=self.settings.get("degeneration_guard", True))
        ctk.CTkSwitch(row, text="Degeneration guard (retry / trim scenes that loop — recommended)",
                      variable=self.v_degen, font=self.f_body,
                      command=self._save_settings_form).pack(anchor="w", pady=4)
        self.v_synopsis = ctk.BooleanVar(value=self.settings.get("auto_running_synopsis", True))
        ctk.CTkSwitch(row, text="Maintain a rolling 'story so far' synopsis (anti-amnesia)",
                      variable=self.v_synopsis, font=self.f_body,
                      command=self._save_settings_form).pack(anchor="w", pady=4)
        self.v_threads = ctk.BooleanVar(value=self.settings.get("auto_open_threads", True))
        ctk.CTkSwitch(row, text="Track open plot threads",
                      variable=self.v_threads, font=self.f_body,
                      command=self._save_settings_form).pack(anchor="w", pady=4)

        drow = ctk.CTkFrame(c, fg_color="transparent")
        drow.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(drow, text="Default world depth", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.opt_depth_default = ctk.CTkOptionMenu(drow, values=["sketch", "standard", "rich", "epic"],
                                                   font=self.f_small, width=110,
                                                   fg_color=self.pal["surface_2"],
                                                   button_color=self.acc["primary"],
                                                   command=lambda _=None: self._save_settings_form())
        self.opt_depth_default.set(self.settings.get("world_depth", "rich"))
        self.opt_depth_default.pack(side="left", padx=6)
        ctk.CTkLabel(drow, text="  Reconcile codex every N chapters (0 = off)", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(12, 4))
        self.e_reconcile = ctk.CTkEntry(drow, width=56, font=self.f_body, fg_color=self.pal["surface_2"])
        self.e_reconcile.insert(0, str(self.settings.get("reconcile_every", 12)))
        self.e_reconcile.pack(side="left")

        srow = ctk.CTkFrame(c, fg_color="transparent")
        srow.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(srow, text="Anti-repeat strength (DRY)", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.sl_dry = ctk.CTkSlider(srow, from_=0.0, to=1.4, number_of_steps=14, width=200,
                                    command=lambda _=None: self._save_settings_form())
        self.sl_dry.set(float(self.settings.get("dry_multiplier", 0.8)))
        self.sl_dry.pack(side="left", padx=8)
        self.dry_lbl = ctk.CTkLabel(srow, text="", font=self.f_small, text_color=self.pal["text_dim"])
        self.dry_lbl.pack(side="left")

        self.e_api = self._labeled_entry(c, "Jan API base URL",
                                         self.settings.get("api_base", config.DEFAULT_API_BASE))
        self.e_models_path = self._labeled_entry(c, "Models folder", self.models_path)

        # --- memory safety ---
        mrow = ctk.CTkFrame(c, fg_color="transparent")
        mrow.pack(fill="x", padx=18, pady=6)
        self.v_ramguard = ctk.BooleanVar(value=self.settings.get("ram_guard", True))
        ctk.CTkSwitch(mrow, text="RAM guard — pause generation if free memory runs low",
                      variable=self.v_ramguard, font=self.f_body,
                      command=self._save_settings_form).pack(side="left")
        ctk.CTkLabel(mrow, text="  min free GB:", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(12, 4))
        self.e_minram = ctk.CTkEntry(mrow, width=56, font=self.f_body, fg_color=self.pal["surface_2"])
        self.e_minram.insert(0, str(self.settings.get("min_free_ram_gb", 2.5)))
        self.e_minram.pack(side="left")
        urow = ctk.CTkFrame(c, fg_color="transparent")
        urow.pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(urow, text="⏏  Unload idle Jan models", font=self.f_small,
                      fg_color=self.pal["surface_2"], hover_color=self.pal["border"],
                      command=self._unload_jan).pack(side="left")
        self.unload_lbl = ctk.CTkLabel(urow, text="", font=self.f_small,
                                       text_color=self.pal["text_dim"])
        self.unload_lbl.pack(side="left", padx=10)
        tr = ctk.CTkFrame(c, fg_color="transparent")
        tr.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(tr, text="Theme", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.opt_theme = ctk.CTkOptionMenu(tr, values=["dark", "light"], font=self.f_small,
                                           fg_color=self.pal["surface_2"], button_color=self.acc["primary"],
                                           command=lambda _=None: self._save_settings_form())
        self.opt_theme.set(self.settings.get("theme", "dark"))
        self.opt_theme.pack(side="left", padx=6)
        self.opt_accent = ctk.CTkOptionMenu(tr, values=["forge", "ember", "moss", "plum"],
                                            font=self.f_small, fg_color=self.pal["surface_2"],
                                            button_color=self.acc["primary"],
                                            command=lambda _=None: self._save_settings_form())
        self.opt_accent.set(self.settings.get("accent", "forge"))
        self.opt_accent.pack(side="left", padx=6)
        ctk.CTkLabel(tr, text="  UI scale", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(12, 4))
        self.opt_uiscale = ctk.CTkOptionMenu(tr, values=["0.9", "1.0", "1.1", "1.25", "1.4"],
                                             font=self.f_small, width=80,
                                             fg_color=self.pal["surface_2"],
                                             button_color=self.acc["primary"],
                                             command=lambda _=None: self._save_settings_form())
        self.opt_uiscale.set(str(self.settings.get("ui_scale", 1.0)))
        self.opt_uiscale.pack(side="left", padx=4)
        self.opt_density = ctk.CTkOptionMenu(tr, values=["comfortable", "compact"],
                                             font=self.f_small, width=130,
                                             fg_color=self.pal["surface_2"],
                                             button_color=self.acc["primary"],
                                             command=lambda _=None: self._save_settings_form())
        self.opt_density.set(self.settings.get("ui_density", "comfortable"))
        self.opt_density.pack(side="left", padx=4)

        br = ctk.CTkFrame(c, fg_color="transparent")
        br.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(br, text="Save settings", font=self.f_body, fg_color=self.acc["primary"],
                      hover_color=self.acc["hover"], command=self._save_settings_form).pack(side="left")
        ctk.CTkButton(br, text="Open data folder", font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"],
                      command=lambda: config.open_in_file_manager(config.DATA_ROOT)).pack(side="left", padx=8)

        # --- export / covers / audiobook defaults ---
        x = self._card(f, "Export, covers & audiobooks")
        self._hint(x, "Defaults for the Export tab. The author name is written into EPUB, "
                      "PDF and audiobook metadata and onto generated covers.")
        self.e_author = self._labeled_entry(x, "Author name", self.settings.get("author_name", ""))
        self.e_export_dir_default = self._labeled_entry(
            x, "Default export folder", self.settings.get("export_dir", ""))

        exr = ctk.CTkFrame(x, fg_color="transparent")
        exr.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(exr, text="Default formats", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        want = self.settings.get("export_formats") or ["epub"]
        self.v_fmt_default = {}
        for fmt in bookexport.FORMATS:
            self.v_fmt_default[fmt] = ctk.BooleanVar(value=fmt in want)
            ctk.CTkCheckBox(exr, text=fmt.upper(), variable=self.v_fmt_default[fmt],
                            font=self.f_small, width=80,
                            command=self._save_settings_form).pack(side="left", padx=6)

        exr2 = ctk.CTkFrame(x, fg_color="transparent")
        exr2.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(exr2, text="PDF page size", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.opt_pagesize = ctk.CTkOptionMenu(exr2, values=list(bookexport.PAGE_SIZES),
                                              font=self.f_small, width=90,
                                              fg_color=self.pal["surface_2"],
                                              button_color=self.acc["primary"],
                                              command=lambda _=None: self._save_settings_form())
        self.opt_pagesize.set(self.settings.get("pdf_page_size", "A4"))
        self.opt_pagesize.pack(side="left", padx=6)
        self.v_open_after = ctk.BooleanVar(value=self.settings.get("export_open_after", True))
        ctk.CTkCheckBox(exr2, text="open the output folder when a job finishes",
                        variable=self.v_open_after, font=self.f_small,
                        command=self._save_settings_form).pack(side="left", padx=12)

        exr3 = ctk.CTkFrame(x, fg_color="transparent")
        exr3.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(exr3, text="Cover style", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.opt_cover_style_default = ctk.CTkOptionMenu(
            exr3, values=["gradient", "duotone", "minimal"], font=self.f_small, width=120,
            fg_color=self.pal["surface_2"], button_color=self.acc["primary"],
            command=lambda _=None: self._save_settings_form())
        self.opt_cover_style_default.set(self.settings.get("cover_style", "gradient"))
        self.opt_cover_style_default.pack(side="left", padx=6)
        self.v_ai_backend = ctk.BooleanVar(value=self.settings.get("ai_image_backend", False))
        ctk.CTkCheckBox(exr3, text="enable local AI image generation (needs diffusers)",
                        variable=self.v_ai_backend, font=self.f_small,
                        command=self._save_settings_form).pack(side="left", padx=12)
        ctk.CTkLabel(exr3, text=("diffusers detected" if bookexport.DIFFUSERS_OK
                                 else "diffusers not installed — the quick cover needs nothing"),
                     font=self.f_small,
                     text_color=self.pal["good"] if bookexport.DIFFUSERS_OK
                     else self.pal["text_dim"]).pack(side="left", padx=4)

        tts = ctk.CTkFrame(x, fg_color="transparent")
        tts.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(tts, text="Narrator voice", font=self.f_body, width=180, anchor="w",
                     text_color=self.pal["text"]).pack(side="left")
        self.opt_voice_default = ctk.CTkOptionMenu(
            tts, values=audiobook.VOICE_LABELS, font=self.f_small, width=340,
            fg_color=self.pal["surface_2"], button_color=self.acc["primary"],
            command=lambda _=None: self._save_settings_form())
        self.opt_voice_default.set(audiobook.id_to_label(
            self.settings.get("tts_voice", audiobook.DEFAULT_VOICE)))
        self.opt_voice_default.pack(side="left", padx=6)
        self.e_voices_dir = self._labeled_entry(
            x, "Voice download folder", self.settings.get("tts_voices_dir", ""))
        self._hint(x, f"Blank = {os.path.join(config.DATA_ROOT, 'tts_voices')}. "
                      f"Installed voices: {', '.join(audiobook.installed_voices(self.settings)) or 'none yet'}. "
                      + ("Piper is installed — narration is fully offline after the first "
                         "voice download." if audiobook.PIPER_OK else audiobook.PIPER_HINT))

        tts2 = ctk.CTkFrame(x, fg_color="transparent")
        tts2.pack(fill="x", padx=18, pady=(0, 12))
        self.v_tts_split_default = ctk.BooleanVar(
            value=self.settings.get("tts_per_character_voices", True))
        ctk.CTkCheckBox(tts2, text="auto-split dialogue by character for audiobooks",
                        variable=self.v_tts_split_default, font=self.f_small,
                        command=self._save_settings_form).pack(side="left")
        self.v_tts_keep = ctk.BooleanVar(value=self.settings.get("tts_keep_chapter_wavs", False))
        ctk.CTkCheckBox(tts2, text="keep per-chapter WAVs", variable=self.v_tts_keep,
                        font=self.f_small,
                        command=self._save_settings_form).pack(side="left", padx=12)
        ctk.CTkLabel(tts2, text="chapter gap (ms)", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(side="left", padx=(12, 4))
        self.e_tts_gap = ctk.CTkEntry(tts2, width=64, font=self.f_body,
                                      fg_color=self.pal["surface_2"])
        self.e_tts_gap.insert(0, str(self.settings.get("tts_chapter_pause_ms", 900)))
        self.e_tts_gap.pack(side="left")

        about = self._card(f, "About")
        ctk.CTkLabel(about, text="NovelForge · local long-form novel studio for Jan.ai\n"
                                 "Data lives in ~/NovelMakerData/. Nothing leaves your machine "
                                 "except optional DuckDuckGo idea lookups.",
                     font=self.f_small, justify="left",
                     text_color=self.pal["text_dim"]).pack(anchor="w", padx=18, pady=12)

    def _save_settings_form(self):
        self.settings["advanced_mode"] = self.v_advanced.get()
        self.settings["strip_reasoning"] = self.v_strip.get()
        self.settings["degeneration_guard"] = self.v_degen.get()
        self.settings["auto_running_synopsis"] = self.v_synopsis.get()
        self.settings["auto_open_threads"] = self.v_threads.get()
        self.settings["world_depth"] = self.opt_depth_default.get()
        try:
            self.settings["reconcile_every"] = max(0, int(float(self.e_reconcile.get())))
        except Exception:
            pass
        self.settings["dry_multiplier"] = round(float(self.sl_dry.get()), 2)
        self.dry_lbl.configure(text=f"{self.settings['dry_multiplier']:.2f}"
                               + ("  (off)" if self.settings["dry_multiplier"] == 0 else ""))
        if hasattr(self, "v_ramguard"):
            self.settings["ram_guard"] = self.v_ramguard.get()
        if hasattr(self, "e_minram"):
            try:
                self.settings["min_free_ram_gb"] = max(0.5, float(self.e_minram.get()))
            except Exception:
                pass
        self.settings["api_base"] = self.e_api.get().strip() or config.DEFAULT_API_BASE
        self.settings["models_path"] = self.e_models_path.get().strip()
        self.models_path = self.settings["models_path"] or config.default_models_path()
        self.settings["theme"] = self.opt_theme.get()
        self.settings["accent"] = self.opt_accent.get()

        # --- export / cover / audiobook defaults ---
        if hasattr(self, "e_author"):
            self.settings["author_name"] = self.e_author.get().strip()
            self.settings["export_dir"] = self.e_export_dir_default.get().strip()
            self.settings["export_formats"] = [f for f, v in self.v_fmt_default.items()
                                               if v.get()] or ["epub"]
            self.settings["pdf_page_size"] = self.opt_pagesize.get()
            self.settings["export_open_after"] = self.v_open_after.get()
            self.settings["cover_style"] = self.opt_cover_style_default.get()
            self.settings["ai_image_backend"] = self.v_ai_backend.get()
            self.settings["tts_voice"] = audiobook.label_to_id(self.opt_voice_default.get())
            self.settings["tts_voices_dir"] = self.e_voices_dir.get().strip()
            self.settings["tts_per_character_voices"] = self.v_tts_split_default.get()
            self.settings["tts_keep_chapter_wavs"] = self.v_tts_keep.get()
            try:
                self.settings["tts_chapter_pause_ms"] = max(0, int(float(self.e_tts_gap.get())))
            except Exception:
                pass

        # --- ui density / scale ---
        rebuild_all = False
        if hasattr(self, "opt_uiscale"):
            try:
                scale = max(0.7, min(1.6, float(self.opt_uiscale.get())))
            except Exception:
                scale = 1.0
            if scale != self.settings.get("ui_scale", 1.0):
                self.settings["ui_scale"] = scale
                try:
                    ctk.set_widget_scaling(scale)
                except Exception:
                    pass
            density = self.opt_density.get()
            if density != self.settings.get("ui_density", "comfortable"):
                self.settings["ui_density"] = density
                rebuild_all = True

        config.save_settings(self.settings)
        # rebuild views so the advanced toggle / density change takes effect
        for key in (list(self._views) if rebuild_all else ["generate"]):
            if key in self._views and key != "settings":
                self._views[key].destroy()
                del self._views[key]
        self._toast("Settings saved. Theme changes apply on restart.", "ok")
        self._apply_responsive()
        self._refresh_models()

    # ==================================================================
    # worker plumbing
    # ==================================================================
    def _make_engine(self, settings=None, model=None):
        model = model or self.model_menu.get()
        profile = self.catalog.profile(model)
        s = settings or self.settings
        return NovelEngine(
            self.project, self.client, model, self.style_lib, profile, s,
            log=self.bus.log, progress=self.bus.progress, stream=self.bus.stream, kill=self.kill,
        )

    def _run_worker(self, label, job, settings=None):
        if self.worker and self.worker.is_alive():
            return self._toast("Busy — wait for the current task.", "err")
        self.kill.reset()
        model = self.model_menu.get()

        def wrapped():
            try:
                engine = self._make_engine(settings, model=model)
                job(engine)
                self.bus.done(label)
            except Exception as e:
                self.bus.error(f"{label} failed: {e}")
                self.bus.log(traceback.format_exc())
                self.bus.done(label)

        self.worker = threading.Thread(target=wrapped, daemon=True)
        self.worker.start()
        self._set_busy(label, True)
        self._toast(f"{label}…")

    def _run_bg(self, label, fn, warn_if_generating=True):
        """Export / cover / TTS work. Its own thread and its own kill switch, so it
        never touches a running generation — but it does warn before competing with
        one for this machine's CPU and RAM."""
        if self.job and self.job.is_alive():
            return self._toast(f"Busy — '{label}' must wait for the running job.", "err")
        if warn_if_generating and self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                    APP_TITLE,
                    f"A model generation is running.\n\n{label} will compete with it for "
                    "CPU and RAM, which can slow both down badly on this machine.\n\n"
                    "Start anyway?"):
                return self._toast(f"{label} held — generation is running.", "err")
        self.job_kill.reset()

        def wrapped():
            try:
                fn()
            except Exception as e:
                self.bus.error(f"{label} failed: {e}")
                self.bus.log(traceback.format_exc())
            finally:
                self.bus.q.put(("job_done", label))

        self.job = threading.Thread(target=wrapped, daemon=True)
        self.job.start()
        self._set_busy(label, True)
        self._toast(f"{label}…")

    def _pump(self):
        try:
            while True:
                kind, payload = self.bus.q.get_nowait()
                try:
                    self._dispatch(kind, payload)
                except Exception as e:
                    self._append_stream(f"\n[ui] {e}\n")
        except queue.Empty:
            pass
        self.after(90, self._pump)

    def _dispatch(self, kind, payload):
        if kind == "log":
            self._append_stream(f"\n{payload}\n" if not payload.startswith("\n") else payload)
        elif kind == "stream":
            self._append_stream(payload)
        elif kind == "progress":
            self._handle_progress(payload)
        elif kind == "models":
            self._apply_models(*payload)
        elif kind == "jan_state":
            self._render_health()
        elif kind == "call":
            payload()
        elif kind == "reload_story":
            self._reload_story_fields()
        elif kind == "set_outline":
            if hasattr(self, "t_outline"):
                self.t_outline.delete("1.0", "end")
                self.t_outline.insert("1.0", payload)
            self._save_outline()
        elif kind == "pdf_list":
            self._refresh_pdf_list()
        elif kind == "pdf_notes":
            self._show_pdf_notes()
        elif kind == "research_result":
            self.research_box.delete("1.0", "end")
            self.research_box.insert("1.0", payload)
        elif kind == "home_stats":
            self._render_home(payload)
        elif kind == "cover_done":
            self._refresh_cover_preview()
        elif kind == "voice_cast":
            self._apply_cast(payload)
        elif kind == "export_done":
            if self.settings.get("export_open_after", True):
                config.open_in_file_manager(payload)
        elif kind == "audiobook_done":
            if hasattr(self, "tts_status"):
                self.tts_status.configure(
                    text=f"Done → {payload}" if payload else "Cancelled — chapter WAVs kept.")
            if payload and self.settings.get("export_open_after", True):
                config.open_in_file_manager(os.path.dirname(payload))
        elif kind == "job_done":
            self._set_busy(payload, False)
            self._toast(f"{payload} finished.", "ok")
            if hasattr(self, "tts_prog"):
                self.tts_prog.set(0)
            self._refresh_export_view()
        elif kind == "error":
            self._toast(payload, "err")
            self._append_stream(f"\n[!] {payload}\n")
        elif kind == "done":
            self._set_busy(payload, False)
            self._toast(f"{payload} finished.", "ok")
            if hasattr(self, "prog_scene"):
                self.prog_scene.set(0)
            self._refresh_codex_view()
            if "home" in self._views:
                self._refresh_home()

    def _append_stream(self, text):
        box = getattr(self, "stream_box", None)
        try:
            if box is not None and box.winfo_exists():
                box.insert("end", text)
                box.see("end")
        except Exception:
            pass

    def _handle_progress(self, kw):
        try:
            self._handle_progress_inner(kw)
        except Exception:
            pass

    def _handle_progress_inner(self, kw):
        stage = kw.get("stage")
        if stage == "chapter":
            n, tot = kw.get("chapter", 0), kw.get("chapter_total", 1)
            self.prog_chapter.set((n - 1) / max(tot, 1))
            self.gen_status.configure(text=f"Chapter {n} / {tot}")
        elif stage == "scene":
            i, tot = kw.get("scene", 0), kw.get("scene_total", 1)
            self.prog_scene.set(i / max(tot, 1))
            self.gen_status.configure(text=f"Chapter {kw.get('chapter')} · scene {i}/{tot}")
        elif stage == "chapter_done":
            n, tot = kw.get("chapter", 0), kw.get("chapter_total", 1)
            self.prog_chapter.set(n / max(tot, 1))
            self.gen_status.configure(text=f"Chapter {n}/{tot} done · {kw.get('words', 0):,} words total")
            self.header_sub.configure(text=f"{kw.get('words', 0):,} words")
        elif stage in ("tts_chapter", "tts_done") and hasattr(self, "tts_prog"):
            n, tot = kw.get("chapter", 0), kw.get("chapter_total", 1)
            self.tts_prog.set(n / max(tot, 1))
            self.tts_status.configure(
                text=(f"Stitching {n} chapters…" if stage == "tts_done"
                      else f"Narrating chapter {n} / {tot}"))

    def _reload_story_fields(self):
        if "story" in self._views:
            self._views["story"].destroy()
            del self._views["story"]
        self._show("story")

    # ==================================================================
    def _on_close(self):
        try:
            self.kill.request_hard(keep_partial=True)
            config.save_settings(self.settings)
        finally:
            self.destroy()


def main():
    app = NovelForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
