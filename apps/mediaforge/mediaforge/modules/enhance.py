"""
Video Enhancer — resolution upscale, motion-interpolation (de-stutter to 60/120),
and I-frame / scene-change compression controls. Same encoder + progress + kill
plumbing as Subtitle Studio.
"""

from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from ..config import VIDEO_EXTS, ffmpeg_caps
from ..ffrunner import probe_streams, FFJob, build_encode_args
from .. import ui

RES = {"Original": None, "720p (1280×720)": (1280, 720), "1080p (1920×1080)": (1920, 1080),
       "1440p (2560×1440)": (2560, 1440), "4K (3840×2160)": (3840, 2160)}


class VideoEnhancer:
    NAME = "Video Enhancer"
    ICON = "✨"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.s = ctx.settings
        self.files = []
        self.job = None
        self._build(parent)

    def _build(self, f):
        c = ui.card(f, self.ctx, "Files")
        r = ui.row(c)
        ui.button(r, self.ctx, "Add videos…", self._add, primary=True)
        ui.button(r, self.ctx, "Clear", lambda: (self.files.clear(), self._refresh()))
        self.out_var = ctk.StringVar(value=str(Path.home() / "Videos" / "MediaForge"))
        ui.button(r, self.ctx, "Output…", self._pick_out)
        self.flist = ctk.CTkTextbox(c, font=self.ctx.f_mono, height=80, fg_color=self.ctx.pal["surface_2"])
        self.flist.pack(fill="x", padx=16, pady=(6, 12))

        u = ui.card(f, self.ctx, "Upscale")
        self.res = ui.opt(u, self.ctx, "Target resolution", list(RES), "Original", width=200)
        self.scaler = ui.opt(u, self.ctx, "Scaler", ["lanczos", "spline", "bicubic", "bilinear"],
                             "lanczos", width=160)

        i = ui.card(f, self.ctx, "Frame interpolation (de-stutter)")
        self.interp = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(ui.row(i), text="enable motion interpolation (minterpolate mci)",
                        variable=self.interp, font=self.ctx.f_small).pack(side="left")
        self.fps = ui.opt(i, self.ctx, "Target fps", ["30", "48", "60", "90", "120", "144"], "60", width=120)
        ui.hint(i, self.ctx, "minterpolate is slow on CPU (often slower than realtime) but genuinely "
                             "smooths stuttery video. Start with a short clip.")

        cmp = ui.card(f, self.ctx, "Compression")
        self.fam = ui.opt(cmp, self.ctx, "Codec", ["x264", "x265"], self.s.get("encoder_family", "x264"))
        self.hw = ui.opt(cmp, self.ctx, "Encoder", ["cpu", "vaapi", "qsv", "nvenc"],
                         self.s.get("hw_encoder", "cpu"))
        r = ui.row(cmp)
        ctk.CTkLabel(r, text="CRF", width=170, anchor="w", font=self.ctx.f_body,
                     text_color=self.ctx.pal["text"]).pack(side="left")
        self.crf = ctk.CTkEntry(r, width=60, fg_color=self.ctx.pal["surface_2"]); self.crf.insert(0, "20")
        self.crf.pack(side="left")
        r = ui.row(cmp)
        ctk.CTkLabel(r, text="Max GOP / keyint (big = smaller file)", width=260, anchor="w",
                     font=self.ctx.f_body, text_color=self.ctx.pal["text"]).pack(side="left")
        self.gop = ctk.CTkEntry(r, width=80, fg_color=self.ctx.pal["surface_2"]); self.gop.insert(0, "250")
        self.gop.pack(side="left")
        r = ui.row(cmp)
        ctk.CTkLabel(r, text="Scene-change threshold (0–100)", width=260, anchor="w",
                     font=self.ctx.f_body, text_color=self.ctx.pal["text"]).pack(side="left")
        self.sc = ctk.CTkEntry(r, width=80, fg_color=self.ctx.pal["surface_2"]); self.sc.insert(0, "40")
        self.sc.pack(side="left")
        self.copy_audio = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(ui.row(cmp), text="copy audio (no re-encode)", variable=self.copy_audio,
                        font=self.ctx.f_small).pack(side="left")

        run = ui.card(f, self.ctx, "Run")
        r = ui.row(run)
        ui.button(r, self.ctx, "▶ Start", self._start, primary=True)
        ui.button(r, self.ctx, "■ KILL", lambda: self.job and self.job.kill(),
                  fg_color=self.ctx.pal["bad"], hover_color="#ff6b6b", text_color="#fff")
        self.prog = ctk.CTkProgressBar(run, progress_color=self.ctx.acc["primary"]); self.prog.set(0)
        self.prog.pack(fill="x", padx=16, pady=6)
        self.log_box = ui.console(run, self.ctx, height=200)

    def _add(self):
        for p in filedialog.askopenfilenames(
                filetypes=[("Video", " ".join(f"*{e}" for e in VIDEO_EXTS))]):
            if p not in self.files:
                self.files.append(p)
        self._refresh()

    def _pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out_var.set(d)

    def _refresh(self):
        import os
        self.flist.delete("1.0", "end")
        self.flist.insert("1.0", "\n".join(os.path.basename(f) for f in self.files) or "(none)")

    def _start(self):
        if not self.files:
            return messagebox.showinfo(self.NAME, "Add files.")
        self.s["encoder_family"] = self.fam.get()
        self.s["hw_encoder"] = self.hw.get()
        try:
            self.s["crf"] = int(float(self.crf.get()))
        except ValueError:
            pass
        self.ctx.save_settings()
        files = list(self.files)
        out_dir = Path(self.out_var.get())
        res = RES[self.res.get()]
        scaler = self.scaler.get()
        interp = self.interp.get()
        fps = self.fps.get()
        gop, sc = self.gop.get(), self.sc.get()
        copy_a = self.copy_audio.get()

        def work():
            out_dir.mkdir(parents=True, exist_ok=True)
            ff = ffmpeg_caps()["ffmpeg"]
            for i, src in enumerate(files, 1):
                import os
                dur = probe_streams(src).get("duration", 0)
                out = str(out_dir / (Path(src).stem + "_enhanced.mp4"))
                vf = []
                if res:
                    vf.append(f"scale={res[0]}:{res[1]}:flags={scaler}")
                if interp:
                    vf.append(f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1")
                pre, vc = build_encode_args(self.s)
                cmd = [ff, "-y"] + pre + ["-i", src, "-map", "0:v:0", "-map", "0:a?"]
                if self.s.get("hw_encoder") == "vaapi":
                    cmd += ["-vf", (",".join(vf) + "," if vf else "") + "format=nv12,hwupload"]
                elif vf:
                    cmd += ["-vf", ",".join(vf)]
                cmd += vc + ["-g", gop, "-sc_threshold", sc]
                cmd += (["-c:a", "copy"] if copy_a else
                        ["-c:a", "aac", "-b:a", "192k"])
                cmd += ["-movflags", "+faststart", out]
                self.ctx.log(f"\n[{i}/{len(files)}] {os.path.basename(src)}")
                self.job = FFJob(cmd, dur, on_line=lambda s: self.ctx.log("  " + s),
                                 on_progress=lambda fr: self.ctx.ui(lambda fr=fr: self.prog.set(fr)))
                rc = self.job.run()
                self.ctx.log(f"  {'✓ ' + out if rc == 0 else 'exit ' + str(rc)}")
            self.ctx.log("\nDone.")
        self.ctx.run_worker(work, "Enhance")
