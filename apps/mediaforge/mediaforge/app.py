"""
MediaForge shell — a left nav rail of modules, a persistent console/progress
strip at the bottom, and a Settings view. Each module builds its own scrollable
page and talks to the shared console through AppContext.
"""

import customtkinter as ctk
from tkinter import messagebox

from . import config
from .theme import palette, accent, FONT, MONO
from .janclient import JanClient
from .ui import Bus, AppContext, card, hint, labeled_entry, opt, button, row

from .modules.subtitles import SubtitleStudio
from .modules.enhance import VideoEnhancer
from .modules.organizer import Organizer
from .modules.dedupe import DuplicateSlayer
from .modules.storage import StorageTools
from .modules.manga import MangaDownloader
from .modules.imagestudio import ImageStudio
from .modules.jptutor import JapaneseTutor
from .modules.anime_library import AnimeLibrary

MODULES = [SubtitleStudio, VideoEnhancer, Organizer, AnimeLibrary, DuplicateSlayer,
           StorageTools, MangaDownloader, ImageStudio, JapaneseTutor]


class MediaForgeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = config.load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        self.pal = palette(self.settings.get("theme", "dark"))
        self.acc = accent(self.settings.get("accent", "cyan"))

        self.title("MediaForge")
        self.geometry("1300x900")
        self.minsize(1080, 720)
        self.configure(fg_color=self.pal["bg"])

        self.f_h1 = ctk.CTkFont(family=FONT, size=21, weight="bold")
        self.f_h2 = ctk.CTkFont(family=FONT, size=14, weight="bold")
        self.f_body = ctk.CTkFont(family=FONT, size=13)
        self.f_small = ctk.CTkFont(family=FONT, size=11)
        self.f_mono = ctk.CTkFont(family=MONO, size=12)

        self.bus = Bus()
        self.jan = JanClient(self.settings.get("jan_base", config.DEFAULTS["jan_base"]),
                             timeout=self.settings.get("request_timeout", 900))
        self.ctx = AppContext(self)

        self._views = {}
        self._nav = {}
        self._build()
        self._show(MODULES[0].__name__)
        self.after(120, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ------------------------------------------------------------------
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # sidebar
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=self.pal["surface"])
        side.grid(row=0, column=0, rowspan=2, sticky="nsw")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="  ⚒  MediaForge", font=self.f_h2,
                     text_color=self.pal["text"]).pack(anchor="w", padx=16, pady=(18, 2))
        ctk.CTkLabel(side, text="  local media workshop", font=self.f_small,
                     text_color=self.pal["text_dim"]).pack(anchor="w", padx=16, pady=(0, 14))
        for M in MODULES:
            b = ctk.CTkButton(side, text=f"  {M.ICON}  {M.NAME}", anchor="w", height=36,
                              font=self.f_body, corner_radius=8, fg_color="transparent",
                              text_color=self.pal["text_dim"], hover_color=self.pal["surface_2"],
                              command=lambda k=M.__name__: self._show(k))
            b.pack(fill="x", padx=8, pady=2)
            self._nav[M.__name__] = b
        b = ctk.CTkButton(side, text="  ⚙  Settings", anchor="w", height=36, font=self.f_body,
                          corner_radius=8, fg_color="transparent", text_color=self.pal["text_dim"],
                          hover_color=self.pal["surface_2"], command=lambda: self._show("Settings"))
        b.pack(fill="x", padx=8, pady=2)
        self._nav["Settings"] = b
        self.conn_lbl = ctk.CTkLabel(side, text="", font=self.f_small, justify="left",
                                     text_color=self.pal["text_dim"], wraplength=190)
        self.conn_lbl.pack(side="bottom", anchor="w", padx=16, pady=12)

        # content area
        self.content = ctk.CTkFrame(self, fg_color=self.pal["bg"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # shared console strip
        strip = ctk.CTkFrame(self, height=170, corner_radius=0, fg_color=self.pal["surface"])
        strip.grid(row=1, column=1, sticky="sew")
        strip.grid_propagate(False)
        top = ctk.CTkFrame(strip, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(6, 0))
        self.status = ctk.CTkLabel(top, text="Ready.", font=self.f_small, text_color=self.pal["text_dim"])
        self.status.pack(side="left")
        ctk.CTkButton(top, text="clear", width=54, font=self.f_small, fg_color=self.pal["surface_2"],
                      hover_color=self.pal["border"],
                      command=lambda: self.console.delete("1.0", "end")).pack(side="right")
        self.gprog = ctk.CTkProgressBar(strip, progress_color=self.acc["primary"], height=6)
        self.gprog.set(0)
        self.gprog.pack(fill="x", padx=12, pady=4)
        self.console = ctk.CTkTextbox(strip, font=self.f_mono, height=110, fg_color=self.pal["console"])
        self.console.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self._refresh_conn()

    def _refresh_conn(self):
        import threading

        def probe():
            up = self.jan.up()
            n = len(self.jan.models()) if up else 0
            self.bus.call(lambda: self.conn_lbl.configure(
                text=f"Jan: {'online · ' + str(n) + ' models' if up else 'offline'}\n"
                     f"ffmpeg: {'ok' if config.ffmpeg_caps()['ffmpeg'] else 'MISSING'}"))
        threading.Thread(target=probe, daemon=True).start()

    def _show(self, key):
        for k, b in self._nav.items():
            b.configure(fg_color=self.acc["primary"] if k == key else "transparent",
                        text_color="#fff" if k == key else self.pal["text_dim"])
        if key not in self._views:
            frame = ctk.CTkScrollableFrame(self.content, fg_color=self.pal["bg"])
            frame.grid(row=0, column=0, sticky="nsew")
            if key == "Settings":
                self._build_settings(frame)
            else:
                M = next(m for m in MODULES if m.__name__ == key)
                try:
                    M(frame, self.ctx)
                except Exception as e:
                    import traceback
                    ctk.CTkLabel(frame, text=f"{M.NAME} failed to load:\n{e}\n\n{traceback.format_exc()}",
                                 justify="left", font=self.f_small,
                                 text_color=self.pal["bad"]).pack(anchor="w", padx=16, pady=16)
            self._views[key] = frame
        for k, v in self._views.items():
            (v.grid if k == key else v.grid_remove)()

    # ------------------------------------------------------------------
    def _build_settings(self, f):
        c = card(f, self.ctx, "General")
        self.v_theme = opt(c, self.ctx, "Theme", ["dark", "light"], self.settings.get("theme", "dark"))
        self.v_accent = opt(c, self.ctx, "Accent", list(config.ACCENTS), self.settings.get("accent", "cyan"))

        j = card(f, self.ctx, "Jan (translation + Japanese tutor)")
        self.e_jan = labeled_entry(j, self.ctx, "Jan API base", self.settings.get("jan_base"), width=360)
        models = self.jan.models()
        self.v_janmodel = opt(j, self.ctx, "Default model", models or ["(offline)"],
                              self.settings.get("jan_model") or (models[0] if models else "(offline)"),
                              width=300)

        t = card(f, self.ctx, "Translation & metadata keys")
        self.e_deepl = labeled_entry(t, self.ctx, "DeepL API key", self.settings.get("deepl_key", ""), width=360)
        self.e_tmdb = labeled_entry(t, self.ctx, "TMDB API key", self.settings.get("tmdb_key", ""), width=360)
        self.e_fal = labeled_entry(t, self.ctx, "fal.ai key", self.settings.get("fal_key", ""), width=360)

        o = card(f, self.ctx, "Organiser defaults")
        self.e_lib = labeled_entry(o, self.ctx, "Library root", self.settings.get("library_root"), width=420)
        self.e_pat = labeled_entry(o, self.ctx, "Naming pattern", self.settings.get("naming_pattern"), width=420)

        button(row(card(f, self.ctx)), self.ctx, "Save settings", self._save_settings, primary=True)
        about = card(f, self.ctx, "About")
        ctk.CTkLabel(about, text="MediaForge · everything runs locally.\n"
                                 "Data + undo manifests: ~/MediaForgeData/\n"
                                 "ffmpeg encoders available: "
                                 + ", ".join(sorted(config.ffmpeg_caps()["encoders"])),
                     justify="left", font=self.f_small, text_color=self.pal["text_dim"]).pack(
            anchor="w", padx=16, pady=12)

    def _save_settings(self):
        s = self.settings
        s["theme"] = self.v_theme.get()
        s["accent"] = self.v_accent.get()
        s["jan_base"] = self.e_jan.get().strip()
        s["jan_model"] = self.v_janmodel.get()
        s["deepl_key"] = self.e_deepl.get().strip()
        s["tmdb_key"] = self.e_tmdb.get().strip()
        s["fal_key"] = self.e_fal.get().strip()
        s["library_root"] = self.e_lib.get().strip()
        s["naming_pattern"] = self.e_pat.get().strip()
        config.save_settings(s)
        self.jan = JanClient(s["jan_base"], timeout=s.get("request_timeout", 900))
        self.ctx.jan = self.jan
        self.bus.log("Settings saved. Theme/accent apply on restart.")
        self._refresh_conn()

    # ------------------------------------------------------------------
    def _pump(self):
        try:
            while True:
                kind, payload = self.bus.q.get_nowait()
                try:
                    if kind == "log":
                        self.console.insert("end", payload + "\n")
                        self.console.see("end")
                    elif kind == "status":
                        self.status.configure(text=payload)
                    elif kind == "progress":
                        self.gprog.set(payload)
                    elif kind == "call":
                        payload()
                    elif kind == "done":
                        self.status.configure(text=f"{payload} finished.")
                        self.gprog.set(0)
                except Exception as e:
                    try:
                        self.console.insert("end", f"[ui] {e}\n")
                    except Exception:
                        pass
        except Exception:
            pass
        self.after(110, self._pump)

    def _close(self):
        config.save_settings(self.settings)
        self.destroy()


def main():
    MediaForgeApp().mainloop()


if __name__ == "__main__":
    main()
