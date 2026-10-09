"""
Subtitle Studio.

Batch video -> MP4 with subtitles handled one of five ways:
  hardbake_embedded    burn an embedded subtitle track into the picture
  hardbake_file        burn an external .srt/.ass you pick
  translate_hardbake   extract an embedded track (or picked file) -> translate
                       (via your local Jan model / Google / DeepL) -> burn it
  transcribe_hardbake  no subs? Whisper-transcribe the audio -> (optional
                       translate) -> burn it. Lets you subtitle raws without
                       typing a line.
  convert_only         no subtitles, just re-encode / resize / compress

Track Inspector: ffprobe every loaded file, list its audio + subtitle tracks,
remember the picked indices across the whole batch.
Encoder: CPU (x264/x265) or hardware (VAAPI / QSV / NVENC) — CPU by default.
Live ffmpeg progress + log + a real Kill button.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from ..config import VIDEO_EXTS, ffmpeg_caps, available_hw_encoders
from ..ffrunner import probe_streams, track_label, FFJob, build_encode_args, escape_for_filter
from ..translate import translate_subtitle_file
from .. import ui

MODES = [
    ("hardbake_embedded", "Hardbake an embedded subtitle track"),
    ("hardbake_file", "Hardbake an external .srt / .ass file"),
    ("translate_hardbake", "Translate a track/file, then hardbake"),
    ("transcribe_hardbake", "Transcribe audio (Whisper), then hardbake"),
    ("convert_only", "No subtitles — just convert / compress / resize"),
]
MODE_LABELS = [m[1] for m in MODES]


class SubtitleStudio:
    NAME = "Subtitle Studio"
    ICON = "📝"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.s = ctx.settings
        self.files = []
        self.probe_cache = {}
        self.ext_sub = None
        self.job = None
        self._build(parent)

    # ------------------------------------------------------------------
    def _build(self, f):
        c = ui.card(f, self.ctx, "1 · Files")
        r = ui.row(c)
        ui.button(r, self.ctx, "Add videos…", self._add, primary=True)
        ui.button(r, self.ctx, "Clear", self._clear)
        self.out_var = ctk.StringVar(value=str(Path.home() / "Videos" / "MediaForge"))
        ui.button(r, self.ctx, "Output folder…", self._pick_out)
        self.out_lbl = ctk.CTkLabel(c, text=f"→ {self.out_var.get()}", font=self.ctx.f_small,
                                    text_color=self.ctx.pal["text_dim"])
        self.out_lbl.pack(anchor="w", padx=16)
        self.file_list = ctk.CTkTextbox(c, font=self.ctx.f_mono, height=90,
                                        fg_color=self.ctx.pal["surface_2"])
        self.file_list.pack(fill="x", padx=16, pady=(6, 12))

        insp = ui.card(f, self.ctx, "2 · Track Inspector")
        ui.hint(insp, self.ctx, "Pick a file to scan its tracks. The chosen audio / subtitle "
                                "index is reused for every file in the batch.")
        r = ui.row(insp)
        self.scan_pick = ctk.CTkOptionMenu(r, values=["(add files first)"], font=self.ctx.f_small,
                                           width=380, fg_color=self.ctx.pal["surface_2"],
                                           button_color=self.ctx.acc["primary"],
                                           command=lambda _=None: self._scan())
        self.scan_pick.pack(side="left")
        ui.button(r, self.ctx, "Rescan", self._scan)
        self.audio_opt = ui.opt(insp, self.ctx, "Audio track", ["0"], "0", width=380)
        self.sub_opt = ui.opt(insp, self.ctx, "Subtitle track", ["0"], "0", width=380)

        m = ui.card(f, self.ctx, "3 · Mode & subtitle source")
        self.mode_opt = ui.opt(m, self.ctx, "What to do", MODE_LABELS,
                               dict(MODES).get(self.s.get("sub_mode"), MODE_LABELS[0]),
                               width=380, command=lambda _=None: self._mode_changed())
        r = ui.row(m)
        ui.button(r, self.ctx, "Pick external .srt/.ass…", self._pick_sub)
        self.sub_file_lbl = ctk.CTkLabel(r, text="(none)", font=self.ctx.f_small,
                                         text_color=self.ctx.pal["text_dim"])
        self.sub_file_lbl.pack(side="left", padx=8)
        self.tr_backend = ui.opt(m, self.ctx, "Translate with",
                                 ["jan", "google", "deepl"], self.s.get("translate_backend", "jan"))
        self.tr_target = ui.labeled_entry(m, self.ctx, "Target language",
                                          self.s.get("target_language", "English"), width=200)
        self.wh_model = ui.opt(m, self.ctx, "Whisper model",
                               ["tiny", "base", "small", "medium"], self.s.get("whisper_model", "base"))

        enc = ui.card(f, self.ctx, "4 · Encoding")
        self.hw_opt = ui.opt(enc, self.ctx, "Encoder", available_hw_encoders(),
                             self.s.get("hw_encoder", "cpu"))
        ui.hint(enc, self.ctx, "CPU is the safe default. VAAPI/QSV use your Intel GPU — much "
                               "faster, occasionally fussy. Test on one file first.")
        self.fam_opt = ui.opt(enc, self.ctx, "Codec", ["x264", "x265"], self.s.get("encoder_family", "x264"))
        r = ui.row(enc)
        ctk.CTkLabel(r, text="CRF", font=self.ctx.f_body, width=170, anchor="w",
                     text_color=self.ctx.pal["text"]).pack(side="left")
        self.crf = ctk.CTkEntry(r, width=60, font=self.ctx.f_body, fg_color=self.ctx.pal["surface_2"])
        self.crf.insert(0, str(self.s.get("crf", 22)))
        self.crf.pack(side="left")
        self.preset_opt = ui.opt(enc, self.ctx, "Preset",
                                 ["ultrafast", "superfast", "veryfast", "faster", "fast",
                                  "medium", "slow", "slower"], self.s.get("preset", "medium"))
        self.tune_opt = ui.opt(enc, self.ctx, "Tune (x264/5)",
                               ["none", "animation", "film", "grain", "stillimage", "fastdecode"],
                               self.s.get("tune", "none"))
        r = ui.row(enc)
        ctk.CTkLabel(r, text="Resize WxH (letterboxed)", font=self.ctx.f_body, width=170,
                     anchor="w", text_color=self.ctx.pal["text"]).pack(side="left")
        self.w = ctk.CTkEntry(r, width=70, font=self.ctx.f_body, fg_color=self.ctx.pal["surface_2"])
        self.w.insert(0, str(self.s.get("sub_scale_w", 1280)))
        self.w.pack(side="left")
        ctk.CTkLabel(r, text=" × ", text_color=self.ctx.pal["text"]).pack(side="left")
        self.h = ctk.CTkEntry(r, width=70, font=self.ctx.f_body, fg_color=self.ctx.pal["surface_2"])
        self.h.insert(0, str(self.s.get("sub_scale_h", 720)))
        self.h.pack(side="left")
        self.no_resize = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(r, text="keep original size", variable=self.no_resize,
                        font=self.ctx.f_small).pack(side="left", padx=10)

        run = ui.card(f, self.ctx, "5 · Run")
        r = ui.row(run)
        ui.button(r, self.ctx, "▶ Start batch", self._start, primary=True)
        ui.button(r, self.ctx, "■ KILL", self._kill, fg_color=self.ctx.pal["bad"],
                  hover_color="#ff6b6b", text_color="#fff")
        self.prog = ctk.CTkProgressBar(run, progress_color=self.ctx.acc["primary"])
        self.prog.set(0)
        self.prog.pack(fill="x", padx=16, pady=6)
        self.stat = ctk.CTkLabel(run, text="Idle.", font=self.ctx.f_small,
                                 text_color=self.ctx.pal["text_dim"])
        self.stat.pack(anchor="w", padx=16)
        self.log_box = ui.console(run, self.ctx, height=220)
        self._mode_changed()

    # ------------------------------------------------------------------
    def _add(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Video", " ".join(f"*{e}" for e in VIDEO_EXTS)), ("All", "*.*")])
        for p in paths:
            if p not in self.files:
                self.files.append(p)
        self._refresh_files()

    def _clear(self):
        self.files = []
        self.probe_cache.clear()
        self._refresh_files()

    def _refresh_files(self):
        self.file_list.delete("1.0", "end")
        self.file_list.insert("1.0", "\n".join(os.path.basename(f) for f in self.files)
                              or "(no files)")
        names = [os.path.basename(f) for f in self.files] or ["(add files first)"]
        self.scan_pick.configure(values=names)
        self.scan_pick.set(names[0])
        if self.files:
            self._scan()

    def _pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out_var.set(d)
            self.out_lbl.configure(text=f"→ {d}")

    def _pick_sub(self):
        p = filedialog.askopenfilename(filetypes=[("Subtitles", "*.srt *.ass *.ssa *.vtt")])
        if p:
            self.ext_sub = p
            self.sub_file_lbl.configure(text=os.path.basename(p))

    def _mode_changed(self):
        label = self.mode_opt.get()
        mode = next(k for k, v in MODES if v == label)
        self.s["sub_mode"] = mode
        self.ctx.save_settings()

    def _current_mode(self):
        return next(k for k, v in MODES if v == self.mode_opt.get())

    def _scan(self):
        if not self.files:
            return
        idx = 0
        try:
            idx = [os.path.basename(f) for f in self.files].index(self.scan_pick.get())
        except ValueError:
            pass
        path = self.files[idx]
        self.ctx.log(f"Scanning tracks: {os.path.basename(path)}")

        def work():
            info = probe_streams(path)
            self.probe_cache[path] = info
            a = [f"{t['index']} — {track_label(t)}" for t in info["audio"]] or ["0 — (none)"]
            s = [f"{t['index']} — {track_label(t)}" for t in info["subtitle"]] or ["0 — (none)"]
            self.ctx.ui(lambda: (self.audio_opt.configure(values=a), self.audio_opt.set(a[0]),
                                 self.sub_opt.configure(values=s), self.sub_opt.set(s[0])))
            self.ctx.log(f"  {len(info['audio'])} audio / {len(info['subtitle'])} subtitle tracks, "
                         f"{info['duration']:.0f}s")
        self.ctx.run_worker(work, "Scan")

    def _kill(self):
        if self.job:
            self.job.kill()
        self.ctx.log("KILL requested.")

    # ------------------------------------------------------------------
    def _sync_settings(self):
        s = self.s
        s["hw_encoder"] = self.hw_opt.get()
        s["encoder_family"] = self.fam_opt.get()
        s["preset"] = self.preset_opt.get()
        s["tune"] = self.tune_opt.get()
        s["translate_backend"] = self.tr_backend.get()
        s["target_language"] = self.tr_target.get().strip() or "English"
        s["whisper_model"] = self.wh_model.get()
        try:
            s["crf"] = int(float(self.crf.get()))
        except ValueError:
            pass
        try:
            s["sub_scale_w"] = int(self.w.get()); s["sub_scale_h"] = int(self.h.get())
        except ValueError:
            pass
        self.ctx.save_settings()

    def _start(self):
        if not self.files:
            return messagebox.showinfo(self.NAME, "Add video files first.")
        if not ffmpeg_caps()["ffmpeg"]:
            return messagebox.showerror(self.NAME, "ffmpeg not found on PATH.")
        self._sync_settings()
        mode = self._current_mode()
        aidx = self.audio_opt.get().split(" — ")[0].strip()
        sidx = self.sub_opt.get().split(" — ")[0].strip()
        out_dir = Path(self.out_var.get())
        files = list(self.files)
        ext_sub = self.ext_sub
        keep_size = self.no_resize.get()

        def work():
            out_dir.mkdir(parents=True, exist_ok=True)
            for i, src in enumerate(files, 1):
                self.ctx.ui(lambda i=i: self.stat.configure(text=f"File {i}/{len(files)}"))
                self.ctx.log(f"\n=== [{i}/{len(files)}] {os.path.basename(src)} ===")
                try:
                    self._process_one(src, out_dir, mode, aidx, sidx, ext_sub, keep_size)
                except Exception as e:
                    self.ctx.log(f"  FAILED: {e}")
            self.ctx.log("\nBatch complete.")
            self.ctx.ui(lambda: self.stat.configure(text="Done."))
        self.ctx.run_worker(work, "Encode")

    # ------------------------------------------------------------------
    def _process_one(self, src, out_dir, mode, aidx, sidx, ext_sub, keep_size):
        src = str(src)
        info = self.probe_cache.get(src) or probe_streams(src)
        dur = info.get("duration", 0)
        out = str(out_dir / (Path(src).stem + ".mp4"))
        tmp = tempfile.mkdtemp(prefix="mf_")
        sub_path = None      # a file:// subtitle to burn
        burn_si = None       # embedded subtitle stream index to burn

        if mode == "hardbake_embedded":
            burn_si = sidx
        elif mode == "hardbake_file":
            if not ext_sub:
                raise RuntimeError("pick an external subtitle file first")
            sub_path = ext_sub
        elif mode == "translate_hardbake":
            raw = ext_sub
            if not raw:
                raw = os.path.join(tmp, "extracted.srt")
                self.ctx.log("  extracting embedded subtitle…")
                r = subprocess.run([ffmpeg_caps()["ffmpeg"], "-y", "-i", src,
                                    "-map", f"0:s:{sidx}", raw], capture_output=True, text=True)
                if r.returncode != 0 or not os.path.exists(raw):
                    raise RuntimeError("could not extract an embedded subtitle track")
            sub_path = os.path.join(tmp, "translated" + os.path.splitext(raw)[1])
            self.ctx.log(f"  translating → {self.s.get('target_language')} via {self.s.get('translate_backend')}")
            translate_subtitle_file(raw, sub_path, self.s, self.ctx.jan,
                                    log=self.ctx.log, kill=lambda: self.job and self.job._killed)
        elif mode == "transcribe_hardbake":
            srt = os.path.join(tmp, "whisper.srt")
            self._whisper(src, srt, tmp)
            sub_path = srt
            if self.s.get("target_language", "English").lower() not in ("", "english", "auto"):
                tr = os.path.join(tmp, "whisper_translated.srt")
                translate_subtitle_file(srt, tr, self.s, self.ctx.jan, log=self.ctx.log,
                                        kill=lambda: self.job and self.job._killed)
                sub_path = tr
        # convert_only -> nothing

        # -------- build ffmpeg command --------
        ff = ffmpeg_caps()["ffmpeg"]
        pre, vc = build_encode_args(self.s)
        w = int(self.w.get() or 1280) if not keep_size else 0
        h = int(self.h.get() or 720) if not keep_size else 0
        scale = ""
        if w and h:
            scale = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                     f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")

        vf = []
        if burn_si is not None:
            vf.append(f"subtitles='{escape_for_filter(src)}':si={burn_si}")
        elif sub_path:
            vf.append(f"subtitles='{escape_for_filter(sub_path)}'")
        if scale:
            vf.append(scale)

        cmd = [ff, "-y"] + pre + ["-i", src,
               "-map", "0:v:0", "-map", f"0:a:{aidx}?"]
        if vf:
            hw = self.s.get("hw_encoder", "cpu")
            if hw in ("vaapi",):
                cmd += ["-vf", ",".join(vf) + ",format=nv12,hwupload"]
            else:
                cmd += ["-vf", ",".join(vf)]
        elif self.s.get("hw_encoder") == "vaapi":
            cmd += ["-vf", "format=nv12,hwupload"]
        cmd += vc
        cmd += ["-c:a", self.s.get("audio_codec", "aac"), "-b:a", self.s.get("audio_bitrate", "192k"),
                "-movflags", "+faststart", out]

        self.ctx.ui(lambda: self.prog.set(0))
        self.job = FFJob(cmd, duration=dur,
                         on_line=lambda s: self.ctx.log("  " + s) if not s.startswith("$") else None,
                         on_progress=lambda fr: self.ctx.ui(lambda fr=fr: self.prog.set(fr)))
        rc = self.job.run()
        if rc == 0:
            self.ctx.log(f"  ✓ {out}")
        elif self.job._killed:
            self.ctx.log("  killed.")
        else:
            self.ctx.log(f"  ffmpeg exited {rc}")

    def _whisper(self, src, out_srt, tmp):
        self.ctx.log("  transcribing with Whisper (first run downloads the model)…")
        wav = os.path.join(tmp, "a.wav")
        subprocess.run([ffmpeg_caps()["ffmpeg"], "-y", "-i", src, "-vn", "-ac", "1",
                        "-ar", "16000", wav], capture_output=True)
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(self.s.get("whisper_model", "base"), device="cpu", compute_type="int8")
            segs, _ = model.transcribe(wav)
            self._write_srt_from_segments(segs, out_srt)
        except ImportError:
            try:
                import whisper
                model = whisper.load_model(self.s.get("whisper_model", "base"))
                res = model.transcribe(wav)
                cues = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                        for s in res["segments"]]
                self._write_srt_from_cues(cues, out_srt)
            except ImportError:
                raise RuntimeError("Whisper not installed. Run:  pip install faster-whisper")

    @staticmethod
    def _ts(t):
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    def _write_srt_from_segments(self, segs, path):
        with open(path, "w", encoding="utf-8") as f:
            for i, s in enumerate(segs, 1):
                f.write(f"{i}\n{self._ts(s.start)} --> {self._ts(s.end)}\n{s.text.strip()}\n\n")

    def _write_srt_from_cues(self, cues, path):
        with open(path, "w", encoding="utf-8") as f:
            for i, c in enumerate(cues, 1):
                f.write(f"{i}\n{self._ts(c['start'])} --> {self._ts(c['end'])}\n{c['text']}\n\n")
