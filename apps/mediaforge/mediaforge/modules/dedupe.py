"""
Duplicate Slayer — feed it a PDF or a folder of images. It perceptually hashes
every page (dHash), groups near-identical ones, lets you auto-keep-first or
manually review with thumbnails, then rebuilds an optimised PDF or CBZ.

Great for cleaning scraped manga chapters that have repeated / filler pages.
"""

import os
import zipfile
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from ..config import IMAGE_EXTS
from .. import ui

try:
    import imagehash
    from PIL import Image
    HAVE = True
except Exception:
    HAVE = False
try:
    import pymupdf as fitz
except Exception:
    try:
        import fitz
    except Exception:
        fitz = None


class DuplicateSlayer:
    NAME = "Duplicate Slayer"
    ICON = "🧹"

    def __init__(self, parent, ctx):
        self.ctx = ctx
        self.target = None
        self.groups = []
        self.keep = []
        self._build(parent)

    def _build(self, f):
        c = ui.card(f, self.ctx, "Target")
        if not HAVE:
            ui.hint(c, self.ctx, "Needs Pillow + imagehash.  pip install pillow imagehash")
        r = ui.row(c)
        ui.button(r, self.ctx, "Load PDF…", lambda: self._load("pdf"), primary=True)
        ui.button(r, self.ctx, "Load image folder…", lambda: self._load("dir"))
        self.tgt_lbl = ctk.CTkLabel(c, text="(none)", font=self.ctx.f_small,
                                    text_color=self.ctx.pal["text_dim"])
        self.tgt_lbl.pack(anchor="w", padx=16)

        o = ui.card(f, self.ctx, "Options")
        self.thresh = ui.opt(o, self.ctx, "Similarity", ["exact", "near", "loose"], "near", width=140)
        self.mode = ui.opt(o, self.ctx, "Resolve", ["auto keep first", "manual review"],
                           "manual review", width=200)
        self.compress = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(ui.row(o), text="compress output (cap 3000px height, JPEG q80)",
                        variable=self.compress, font=self.ctx.f_small).pack(side="left")
        self.out_fmt = ui.opt(o, self.ctx, "Output", ["pdf", "cbz"], "pdf", width=120)
        ui.button(ui.row(o), self.ctx, "SCAN & OPTIMISE", self._run, primary=True)

        self.log_box = ui.console(ui.card(f, self.ctx, "Log"), self.ctx, height=300)

    def _load(self, kind):
        if kind == "pdf":
            p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        else:
            p = filedialog.askdirectory()
        if p:
            self.target = p
            self.tgt_lbl.configure(text=p)

    def _dist(self):
        return {"exact": 0, "near": 6, "loose": 12}[self.thresh.get()]

    def _run(self):
        if not self.target:
            return messagebox.showinfo(self.NAME, "Load a PDF or folder.")
        if not HAVE:
            return messagebox.showerror(self.NAME, "pip install pillow imagehash")
        target = self.target
        maxd = self._dist()
        auto = self.mode.get().startswith("auto")
        compress = self.compress.get()
        fmt = self.out_fmt.get()

        def work():
            import tempfile
            tmp = tempfile.mkdtemp(prefix="mf_dedupe_")
            if target.lower().endswith(".pdf"):
                if not fitz:
                    self.ctx.log("PyMuPDF missing:  pip install pymupdf")
                    return
                self.ctx.log("Extracting page images from PDF…")
                imgs = self._pdf_images(target, tmp)
            else:
                imgs = sorted(str(p) for p in Path(target).iterdir()
                              if p.suffix.lower() in IMAGE_EXTS)
            if not imgs:
                self.ctx.log("No images found.")
                return
            self.ctx.log(f"Hashing {len(imgs)} images…")
            hashes = []
            for i, im in enumerate(imgs):
                try:
                    hashes.append((im, imagehash.dhash(Image.open(im))))
                except Exception:
                    hashes.append((im, None))
                if i % 20 == 0:
                    self.ctx.status(f"hashed {i}/{len(imgs)}")
            # cluster
            used = set()
            groups = []
            for i, (pa, ha) in enumerate(hashes):
                if i in used or ha is None:
                    continue
                grp = [pa]
                used.add(i)
                for j in range(i + 1, len(hashes)):
                    pb, hb = hashes[j]
                    if j in used or hb is None:
                        continue
                    if (ha - hb) <= maxd:
                        grp.append(pb)
                        used.add(j)
                if len(grp) > 1:
                    groups.append(grp)
            dupes = sum(len(g) - 1 for g in groups)
            self.ctx.log(f"{dupes} duplicate pages in {len(groups)} groups.")
            keep = [im for im, h in hashes if not any(im in g for g in groups)]
            if auto or not groups:
                for g in groups:
                    keep.append(g[0])
            else:
                self.groups = groups
                self.keep = keep
                self.ctx.ui(self._review)
                return
            self._compile(sorted(keep), target, compress, fmt, tmp)
        self.ctx.run_worker(work, "Dedupe")

    def _pdf_images(self, pdf, tmp):
        doc = fitz.open(pdf)
        out = []
        for pn in range(len(doc)):
            for k, img in enumerate(doc.load_page(pn).get_images(full=True)):
                try:
                    b = doc.extract_image(img[0])
                    fp = os.path.join(tmp, f"p{pn:04d}_{k}.{b['ext']}")
                    open(fp, "wb").write(b["image"])
                    out.append(fp)
                except Exception:
                    pass
        doc.close()
        return out

    def _review(self):
        win = ctk.CTkToplevel(self.ctx.app)
        win.title("Manual review")
        win.geometry("980x680")
        win.grab_set()
        state = {"i": 0}
        body = ctk.CTkFrame(win, fg_color=self.ctx.pal["surface"])
        body.pack(fill="both", expand=True, padx=10, pady=10)

        def show():
            for w in body.winfo_children():
                w.destroy()
            if state["i"] >= len(self.groups):
                win.destroy()
                self.ctx.run_worker(lambda: self._compile(
                    sorted(self.keep), self.target, self.compress.get(),
                    self.out_fmt.get(), __import__("tempfile").mkdtemp()), "Dedupe")
                return
            grp = self.groups[state["i"]]
            ctk.CTkLabel(body, text=f"Group {state['i']+1}/{len(self.groups)} — {len(grp)} similar pages",
                         font=self.ctx.f_h2).pack(pady=6)
            strip = ctk.CTkScrollableFrame(body, orientation="horizontal", height=420,
                                           fg_color=self.ctx.pal["surface_2"])
            strip.pack(fill="x", padx=6)
            sel = ctk.StringVar(value=grp[0])
            for im in grp:
                cell = ctk.CTkFrame(strip, fg_color="transparent")
                cell.pack(side="left", padx=6, pady=6)
                try:
                    from PIL import Image as PImage
                    pi = PImage.open(im); pi.thumbnail((280, 360))
                    ph = ctk.CTkImage(light_image=pi, dark_image=pi, size=pi.size)
                    ctk.CTkLabel(cell, image=ph, text="").pack()
                except Exception:
                    ctk.CTkLabel(cell, text="(load error)").pack()
                ctk.CTkRadioButton(cell, text=os.path.basename(im), variable=sel, value=im,
                                   font=self.ctx.f_small).pack()
            br = ctk.CTkFrame(body, fg_color="transparent")
            br.pack(pady=10)

            def keep_one():
                self.keep.append(sel.get())
                state["i"] += 1
                show()

            def keep_all():
                self.keep.extend(grp)
                state["i"] += 1
                show()
            ui.button(br, self.ctx, "Keep selected (drop rest)", keep_one, primary=True)
            ui.button(br, self.ctx, "Keep ALL (chapter break)", keep_all)
        show()

    def _compile(self, images, target, compress, fmt, tmp):
        if not images:
            self.ctx.log("Nothing to write.")
            return
        base = os.path.splitext(os.path.basename(target))[0] + "_optimised"
        out_dir = os.path.dirname(target) if os.path.isfile(target) else target
        pil = []
        for k, im in enumerate(images):
            try:
                img = Image.open(im).convert("RGB")
                if compress and img.height > 3000:
                    r = 3000 / img.height
                    img = img.resize((int(img.width * r), 3000), Image.LANCZOS)
                if compress:
                    jp = os.path.join(tmp, f"c{k}.jpg")
                    img.save(jp, "JPEG", quality=80, optimize=True)
                    img = Image.open(jp)
                pil.append(img)
            except Exception as e:
                self.ctx.log(f"skip {im}: {e}")
        if fmt == "cbz":
            zp = os.path.join(out_dir, base + ".cbz")
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                for k, img in enumerate(pil):
                    fp = os.path.join(tmp, f"z{k:04d}.jpg")
                    img.save(fp, "JPEG", quality=88)
                    z.write(fp, f"{k:04d}.jpg")
            self.ctx.log(f"✓ {zp}")
        else:
            pp = os.path.join(out_dir, base + ".pdf")
            pil[0].save(pp, save_all=True, append_images=pil[1:])
            self.ctx.log(f"✓ {pp}")
