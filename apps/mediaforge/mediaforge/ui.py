"""
Shared customtkinter helpers + the AppContext object every module receives.
"""

import queue
import threading
import traceback

import customtkinter as ctk

from .theme import palette, accent, FONT, MONO


class Bus:
    def __init__(self):
        self.q = queue.Queue()

    def log(self, m):        self.q.put(("log", str(m)))
    def progress(self, f):   self.q.put(("progress", float(f)))
    def status(self, m):     self.q.put(("status", str(m)))
    def call(self, fn):      self.q.put(("call", fn))
    def done(self, label):   self.q.put(("done", str(label)))


class AppContext:
    """Passed to every module. Gives fonts, palette, logging and a worker runner."""

    def __init__(self, app):
        self.app = app
        self.settings = app.settings
        self.pal = app.pal
        self.acc = app.acc
        self.bus = app.bus
        self.jan = app.jan
        self.f_h1 = app.f_h1
        self.f_h2 = app.f_h2
        self.f_body = app.f_body
        self.f_small = app.f_small
        self.f_mono = app.f_mono
        self._worker = None

    # --- logging / progress into the shared console ---
    def log(self, m):       self.bus.log(m)
    def status(self, m):    self.bus.status(m)
    def progress(self, f):  self.bus.progress(f)
    def ui(self, fn):       self.bus.call(fn)

    def busy(self):
        return self._worker is not None and self._worker.is_alive()

    def run_worker(self, fn, label="Task"):
        if self.busy():
            self.log("Busy — wait for the current task to finish.")
            return False

        def wrap():
            try:
                fn()
            except Exception as e:
                self.log(f"[{label}] error: {e}")
                self.log(traceback.format_exc())
            finally:
                self.bus.done(label)
        self._worker = threading.Thread(target=wrap, daemon=True)
        self._worker.start()
        return True

    def save_settings(self):
        from .config import save_settings
        save_settings(self.settings)


# --------------------------------------------------------------------------
# widget helpers
# --------------------------------------------------------------------------
def card(parent, ctx, title=None):
    c = ctk.CTkFrame(parent, fg_color=ctx.pal["surface"], corner_radius=12)
    c.pack(fill="x", padx=18, pady=8)
    if title:
        ctk.CTkLabel(c, text=title, font=ctx.f_h2, text_color=ctx.pal["text"]).pack(
            anchor="w", padx=16, pady=(12, 2))
    return c


def hint(parent, ctx, text):
    ctk.CTkLabel(parent, text=text, font=ctx.f_small, justify="left", wraplength=820,
                 text_color=ctx.pal["text_dim"]).pack(anchor="w", padx=16, pady=(0, 10))


def row(parent):
    r = ctk.CTkFrame(parent, fg_color="transparent")
    r.pack(fill="x", padx=16, pady=5)
    return r


def labeled_entry(parent, ctx, label, value="", width=360):
    r = row(parent)
    ctk.CTkLabel(r, text=label, font=ctx.f_body, width=170, anchor="w",
                 text_color=ctx.pal["text"]).pack(side="left")
    e = ctk.CTkEntry(r, font=ctx.f_body, width=width, fg_color=ctx.pal["surface_2"])
    e.pack(side="left", fill="x", expand=True)
    if value:
        e.insert(0, str(value))
    return e


def opt(parent, ctx, label, values, value, width=150, command=None):
    r = row(parent)
    ctk.CTkLabel(r, text=label, font=ctx.f_body, width=170, anchor="w",
                 text_color=ctx.pal["text"]).pack(side="left")
    o = ctk.CTkOptionMenu(r, values=[str(v) for v in values], font=ctx.f_small, width=width,
                          fg_color=ctx.pal["surface_2"], button_color=ctx.acc["primary"],
                          button_hover_color=ctx.acc["hover"], command=command)
    o.set(str(value))
    o.pack(side="left")
    return o


def button(parent, ctx, text, command, primary=False, side="left", **kw):
    # callers sometimes want a specific colour (a red "KILL"/"Delete"/"Revert"
    # button) instead of the primary/neutral default -- let an explicit
    # fg_color/hover_color/etc. in kw win instead of colliding with the ones
    # CTkButton would otherwise get passed twice.
    kw.setdefault("fg_color", ctx.acc["primary"] if primary else ctx.pal["surface_2"])
    kw.setdefault("hover_color", ctx.acc["hover"] if primary else ctx.pal["border"])
    b = ctk.CTkButton(parent, text=text, font=ctx.f_body, command=command, **kw)
    b.pack(side=side, padx=4, pady=4)
    return b


def console(parent, ctx, height=260):
    box = ctk.CTkTextbox(parent, font=ctx.f_mono, height=height, wrap="word",
                         fg_color=ctx.pal["console"])
    box.pack(fill="both", expand=True, padx=16, pady=(4, 14))
    return box
