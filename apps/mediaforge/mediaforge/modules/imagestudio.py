"""
AI Image Studio — text-to-image and image-to-image via fal.ai (your API key),
plus a fully local upscaler (Lanczos / bicubic + optional unsharp) that needs
nothing but Pillow.

fal.ai is used through its plain HTTP API so there's no heavy SDK. Set FAL_KEY in
the environment or paste it here (stored in settings.json).
"""

import os
import time
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

import requests

from ..config import DL_DIR
from .. import ui

try:
    from PIL import Image, ImageFilter
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

FAL_MODELS = {
    "FLUX.1 [schnell] (fast)": "fal-ai/flux/schnell",
    "FLUX.1 [dev]": "fal-ai/flux/dev",
    "SDXL": "fal-ai/fast-sdxl",
}


class ImageStudio:
    NAME = "AI Image Studio"
    ICON = "🎨"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.s = ctx.settings
        self._build(parent)

    def _build(self, f):
        self.tabs = ctk.CTkTabview(f, fg_color=self.ctx.pal["surface"])
        self.tabs.pack(fill="both", expand=True, padx=14, pady=10)
        self.tabs.add("Generate")
        self.tabs.add("Local upscale")
        self._gen(self.tabs.tab("Generate"))
        self._upscale(self.tabs.tab("Local upscale"))

    # ---------------- generate ----------------
    def _gen(self, f):
        c = ui.card(f, self.ctx, "fal.ai")
        self.key = ui.labeled_entry(c, self.ctx, "FAL_KEY",
                                    self.s.get("fal_key") or os.getenv("FAL_KEY", ""), width=440)
        self.model = ui.opt(c, self.ctx, "Model", list(FAL_MODELS), list(FAL_MODELS)[0], width=260)
        self.prompt = ctk.CTkTextbox(c, height=90, font=self.ctx.f_body, fg_color=self.ctx.pal["surface_2"])
        self.prompt.pack(fill="x", padx=16, pady=6)
        self.prompt.insert("1.0", "a cozy seaside town at dawn, anime background art")
        self.size = ui.opt(c, self.ctx, "Size", ["square", "portrait_4_3", "landscape_16_9", "portrait_16_9"],
                           "landscape_16_9", width=200)
        r = ui.row(c)
        ctk.CTkLabel(r, text="Steps", width=170, anchor="w", font=self.ctx.f_body,
                     text_color=self.ctx.pal["text"]).pack(side="left")
        self.steps = ctk.CTkEntry(r, width=60, fg_color=self.ctx.pal["surface_2"]); self.steps.insert(0, "4")
        self.steps.pack(side="left")
        self.img2img = ui.labeled_entry(c, self.ctx, "img2img source (optional)", "", width=440)
        r = ui.row(c)
        ui.button(r, self.ctx, "Browse img…", lambda: self._pick(self.img2img))
        self.strength = ui.labeled_entry(r, self.ctx, "strength", "0.75", width=70)
        self.out = ui.labeled_entry(c, self.ctx, "Save folder", str(DL_DIR / "Images"), width=440)
        ui.button(ui.row(c), self.ctx, "✦ Generate", self._generate, primary=True)
        self.log_box = ui.console(ui.card(f, self.ctx, "Log"), self.ctx, height=200)

    def _pick(self, entry):
        p = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg *.webp")])
        if p:
            entry.delete(0, "end")
            entry.insert(0, p)

    def _generate(self):
        key = self.key.get().strip()
        if not key:
            return messagebox.showerror(self.NAME, "Paste your fal.ai API key.")
        self.s["fal_key"] = key
        self.ctx.save_settings()
        model_id = FAL_MODELS[self.model.get()]
        payload = {"prompt": self.prompt.get("1.0", "end").strip(),
                   "image_size": self.size.get(),
                   "num_inference_steps": int(self.steps.get() or 4),
                   "num_images": 1}
        src = self.img2img.get().strip()
        out_dir = Path(self.out.get().strip())

        def work():
            out_dir.mkdir(parents=True, exist_ok=True)
            url = f"https://fal.run/{model_id}"
            data = dict(payload)
            if src and os.path.exists(src):
                import base64
                b = base64.b64encode(open(src, "rb").read()).decode()
                data["image_url"] = f"data:image/png;base64,{b}"
                data["strength"] = float(self.strength.get() or 0.75)
                url = f"https://fal.run/{model_id}/image-to-image"
            self.ctx.log("Requesting fal.ai…")
            r = requests.post(url, headers={"Authorization": f"Key {key}"}, json=data, timeout=180)
            if r.status_code >= 400:
                self.ctx.log(f"fal.ai {r.status_code}: {r.text[:300]}")
                return
            j = r.json()
            imgs = j.get("images") or []
            for i, im in enumerate(imgs):
                iu = im.get("url")
                if not iu:
                    continue
                content = requests.get(iu, timeout=120).content
                fp = out_dir / f"fal_{int(time.time())}_{i}.png"
                fp.write_bytes(content)
                self.ctx.log(f"✓ {fp}")
        self.ctx.run_worker(work, "Generate")

    # ---------------- local upscale ----------------
    def _upscale(self, f):
        c = ui.card(f, self.ctx, "Local upscale (no API, Pillow only)")
        if not HAVE_PIL:
            ui.hint(c, self.ctx, "pip install pillow")
        self.up_in = ui.labeled_entry(c, self.ctx, "Input image / folder", "", width=440)
        ui.button(ui.row(c), self.ctx, "Browse file…", lambda: self._pick(self.up_in))
        ui.button(ui.row(c), self.ctx, "Browse folder…",
                  lambda: (self.up_in.delete(0, "end"),
                           self.up_in.insert(0, filedialog.askdirectory() or "")))
        self.up_scale = ui.opt(c, self.ctx, "Scale", ["1.5", "2", "3", "4"], "2", width=100)
        self.up_method = ui.opt(c, self.ctx, "Method", ["lanczos", "bicubic", "hamming"], "lanczos", width=140)
        self.up_sharp = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(ui.row(c), text="unsharp mask after upscale", variable=self.up_sharp,
                        font=self.ctx.f_small).pack(side="left")
        self.up_out = ui.labeled_entry(c, self.ctx, "Save folder", str(DL_DIR / "Upscaled"), width=440)
        ui.button(ui.row(c), self.ctx, "Upscale", self._do_upscale, primary=True)
        self.up_log = ui.console(ui.card(f, self.ctx, "Log"), self.ctx, height=180)

    def _do_upscale(self):
        if not HAVE_PIL:
            return
        src = self.up_in.get().strip()
        if not src or not os.path.exists(src):
            return messagebox.showerror(self.NAME, "Pick an input.")
        scale = float(self.up_scale.get())
        method = {"lanczos": Image.LANCZOS, "bicubic": Image.BICUBIC,
                  "hamming": Image.HAMMING}[self.up_method.get()]
        sharp = self.up_sharp.get()
        out_dir = Path(self.up_out.get().strip())
        files = ([src] if os.path.isfile(src) else
                 [str(p) for p in Path(src).iterdir()
                  if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")])

        def work():
            out_dir.mkdir(parents=True, exist_ok=True)
            for p in files:
                try:
                    im = Image.open(p)
                    im = im.resize((int(im.width * scale), int(im.height * scale)), method)
                    if sharp:
                        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=3))
                    fp = out_dir / (Path(p).stem + f"_x{scale:g}.png")
                    im.save(fp)
                    self.up_log_line(f"✓ {fp.name}")
                except Exception as e:
                    self.up_log_line(f"skip {os.path.basename(p)}: {e}")
        self.ctx.run_worker(work, "Upscale")

    def up_log_line(self, m):
        self.ctx.ui(lambda: (self.up_log.insert("end", m + "\n"), self.up_log.see("end")))
