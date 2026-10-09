"""
Book export -- EPUB / PDF / TXT -- plus cover art (import, procedural, light edits).

Pillow does the always-available cover work. ebooklib and reportlab are optional
and degrade to a pip hint instead of crashing, same as pdfexport.py. The
diffusers path is a deliberate stub: torch+diffusers is a multi-GB install and
minutes per image on a CPU-only machine, so it only lights up if the user
installs it themselves.
"""

import os
import re
import json
import shutil
import datetime

from . import config
from .project import Project, Series, slugify
from . import pdfexport

try:
    from ebooklib import epub
    EPUB_OK = True
except Exception:
    EPUB_OK = False

try:
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
    PIL_OK = True
except Exception:
    PIL_OK = False

try:
    import diffusers  # noqa: F401
    import torch      # noqa: F401
    DIFFUSERS_OK = True
except Exception:
    DIFFUSERS_OK = False


FORMATS = ("epub", "pdf", "txt")
COVER_RATIO = 2 / 3.0            # width / height, the usual ebook cover shape

PIP_HINTS = {
    "epub": "EPUB export needs EbookLib.  Run:  pip install EbookLib",
    "pdf": "PDF export needs reportlab.  Run:  pip install reportlab",
    "cover": "Cover art needs Pillow.  Run:  pip install Pillow",
}

# Installed on this kind of box under a few different names; first hit wins and
# Pillow's bitmap default is the last resort so cover generation never fails.
_FONT_CANDIDATES = {
    "serif_bold": ["DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf", "NotoSerif-Bold.ttf"],
    "serif": ["DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "NotoSerif-Regular.ttf"],
    "sans_bold": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf"],
    "sans": ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf"],
}
_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts",
              os.path.expanduser("~/.local/share/fonts"), os.path.expanduser("~/.fonts")]
_font_cache = {}


def _font_path(kind):
    if kind in _font_cache:
        return _font_cache[kind]
    for name in _FONT_CANDIDATES.get(kind, []):
        for root in _FONT_DIRS:
            for dirpath, _dirs, files in os.walk(root):
                if name in files:
                    _font_cache[kind] = os.path.join(dirpath, name)
                    return _font_cache[kind]
    _font_cache[kind] = None
    return None


def _font(kind, size):
    p = _font_path(kind)
    if p and PIL_OK:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default() if PIL_OK else None


# ==========================================================================
# per-project export sidecar  (<project>/export.json)
# ==========================================================================
def meta_path(project):
    return os.path.join(project.dir, "export.json")


def load_meta(project):
    try:
        with open(meta_path(project), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_meta(project, meta):
    try:
        with open(meta_path(project), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def cover_for(project):
    """The cover chosen for this book, if it still exists on disk."""
    p = load_meta(project).get("cover", "")
    return p if p and os.path.exists(p) else ""


def set_cover(project, path):
    m = load_meta(project)
    m["cover"] = path or ""
    save_meta(project, m)
    return path


def book_title(project):
    return project.bible.get("title") or project.name.replace("_", " ").title()


def output_dir(project, settings):
    """Where exports land: the configured folder, else the project folder."""
    d = (settings or {}).get("export_dir", "") or os.path.join(project.dir, "export")
    os.makedirs(d, exist_ok=True)
    return d


# ==========================================================================
# TXT
# ==========================================================================
def export_txt(project, out_path):
    b = project.bible
    parts = [book_title(project)]
    if b.get("genre"):
        parts.append(b["genre"])
    if b.get("series"):
        parts.append(f"{b['series'].replace('_', ' ').title()} — Book {b.get('book_index', 1)}")
    parts += ["", ""]
    for n in range(1, project.chapter_count() + 1):
        t = project.chapter_title(n)
        parts.append(f"CHAPTER {n}" + (f" — {t}" if t else ""))
        parts.append("")
        parts.append(project.load_chapter(n).strip())
        parts += ["", ""]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path


# ==========================================================================
# EPUB
# ==========================================================================
def _paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text or "") if p.strip()]


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def export_epub(project, out_path, cover_image=None, author="", language="en"):
    if not EPUB_OK:
        raise RuntimeError(PIP_HINTS["epub"])

    b = project.bible
    title = book_title(project)
    author = author or "NovelForge"

    book = epub.EpubBook()
    book.set_identifier(f"novelforge-{project.name}-{datetime.date.today().isoformat()}")
    book.set_title(title)
    book.set_language(language or "en")
    book.add_author(author)
    if b.get("genre"):
        book.add_metadata("DC", "subject", b["genre"])
    if b.get("plot"):
        book.add_metadata("DC", "description", " ".join(b["plot"].split()[:120]))
    if b.get("series"):
        # Calibre's de-facto series convention; readers that know it show
        # "Series, Book 2" instead of an unordered pile.
        series_name = b["series"].replace("_", " ").title()
        book.add_metadata(None, "meta", "", {"name": "calibre:series", "content": series_name})
        book.add_metadata(None, "meta", "",
                          {"name": "calibre:series_index", "content": str(b.get("book_index", 1))})

    if cover_image and os.path.exists(cover_image):
        try:
            with open(cover_image, "rb") as f:
                book.set_cover("cover" + os.path.splitext(cover_image)[1].lower(), f.read())
        except Exception:
            pass

    css = epub.EpubItem(uid="style", file_name="style/main.css", media_type="text/css",
                        content=(
                            "body{font-family:Georgia,serif;line-height:1.55;margin:5%;}"
                            "h1{font-size:1.5em;margin:2em 0 1.2em;text-align:center;"
                            "font-weight:normal;letter-spacing:.06em;}"
                            "h1 small{display:block;font-size:.62em;color:#666;"
                            "letter-spacing:.14em;text-transform:uppercase;margin-bottom:.6em;}"
                            "p{text-indent:1.4em;margin:0 0 .15em;text-align:justify;}"
                            "p.first{text-indent:0;}"
                            ".title-page{text-align:center;margin-top:22%;}"
                            ".title-page h2{font-size:2em;font-weight:normal;}"
                            ".title-page .sub{color:#666;font-style:italic;}"))
    book.add_item(css)

    sub = []
    if b.get("series"):
        sub.append(f"{b['series'].replace('_', ' ').title()} — Book {b.get('book_index', 1)}")
    if b.get("genre"):
        sub.append(b["genre"])
    tp = epub.EpubHtml(title="Title", file_name="title.xhtml", lang=language or "en")
    tp.content = ("<div class='title-page'><h2>" + _esc(title) + "</h2>"
                  + "".join(f"<p class='sub'>{_esc(s)}</p>" for s in sub)
                  + f"<p class='sub'>{_esc(author)}</p></div>")
    tp.add_item(css)
    book.add_item(tp)

    chapters = []
    for n in range(1, project.chapter_count() + 1):
        ct = project.chapter_title(n)
        c = epub.EpubHtml(title=f"Chapter {n}" + (f" — {ct}" if ct else ""),
                          file_name=f"chap_{n:03d}.xhtml", lang=language or "en")
        body = _paras(project.load_chapter(n))
        html = [f"<h1><small>Chapter {n}</small>{_esc(ct) if ct else ''}</h1>"]
        for i, p in enumerate(body):
            cls = " class='first'" if i == 0 else ""
            html.append(f"<p{cls}>{_esc(p)}</p>")
        c.content = "".join(html)
        c.add_item(css)
        book.add_item(c)
        chapters.append(c)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", tp] + chapters
    epub.write_epub(out_path, book)
    return out_path


# ==========================================================================
# PDF  (thin wrapper so the tab has one uniform call shape)
# ==========================================================================
PAGE_SIZES = ("A4", "Letter")


def export_pdf(project, out_path, cover_image=None, page_size="A4"):
    if not pdfexport.REPORTLAB_OK:
        raise RuntimeError(PIP_HINTS["pdf"])
    from reportlab.lib.pagesizes import A4, LETTER
    size = LETTER if str(page_size).lower().startswith("l") else A4
    return pdfexport.export_pdf(project, out_path, cover_image=cover_image or None, page_size=size)


# ==========================================================================
# orchestration
# ==========================================================================
def export_book(project, formats, settings=None, log=None, out_dir=None):
    """Export one book in every requested format. Returns [(fmt, path_or_error)]."""
    settings = settings or {}
    log = log or (lambda _m: None)
    d = out_dir or output_dir(project, settings)
    stem = slugify(book_title(project))
    cover = cover_for(project)
    results = []
    for fmt in formats:
        path = os.path.join(d, f"{stem}.{fmt}")
        try:
            if fmt == "txt":
                export_txt(project, path)
            elif fmt == "epub":
                export_epub(project, path, cover_image=cover,
                            author=settings.get("author_name", ""),
                            language=settings.get("epub_language", "en"))
            elif fmt == "pdf":
                export_pdf(project, path, cover_image=cover,
                           page_size=settings.get("pdf_page_size", "A4"))
            else:
                raise ValueError(f"unknown format '{fmt}'")
            log(f"  ✓ {fmt.upper()} → {path}")
            results.append((fmt, path))
        except Exception as e:
            log(f"  ✗ {fmt.upper()}: {e}")
            results.append((fmt, f"ERROR: {e}"))
    return results


def export_series(series_name, formats, settings=None, log=None, kill=None, out_dir=None):
    """Same per-book path, looped over the series. Returns {book: results}."""
    log = log or (lambda _m: None)
    s = Series(series_name)
    books = s.data.get("books", [])
    if not books:
        raise RuntimeError(f"Series '{series_name}' has no books attached.")
    root = out_dir or os.path.join(config.DATA_ROOT, "exports", s.name)
    os.makedirs(root, exist_ok=True)
    out = {}
    for i, slug in enumerate(books, 1):
        if kill is not None and kill.any:
            log("stopped.")
            break
        p = Project(slug)
        if p.chapter_count() == 0:
            log(f"[{i}/{len(books)}] {slug}: no chapters written yet — skipped.")
            continue
        log(f"[{i}/{len(books)}] {book_title(p)} — {p.chapter_count()} chapters")
        out[slug] = export_book(p, formats, settings=settings, log=log, out_dir=root)
    return out


# ==========================================================================
# COVER ART
# ==========================================================================
def _hex_rgb(h, fallback=(31, 111, 235)):
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _shade(rgb, f):
    """f<1 darkens, f>1 lightens."""
    return tuple(max(0, min(255, int(round(c * f)))) for c in rgb)


def import_cover(project, src_path):
    """Copy a chosen image into the project folder so the book is self-contained."""
    if not os.path.exists(src_path):
        raise RuntimeError(f"No such file: {src_path}")
    ext = os.path.splitext(src_path)[1].lower() or ".png"
    dst = os.path.join(project.dir, "cover" + ext)
    if os.path.abspath(src_path) != os.path.abspath(dst):
        shutil.copyfile(src_path, dst)
    if PIL_OK:                       # fail early on a file that isn't an image
        try:
            Image.open(dst).close()
        except Exception as e:
            os.remove(dst)
            raise RuntimeError(f"Not a readable image: {e}")
    return set_cover(project, dst)


def _fit_text(draw, text, font_kind, max_w, start_size, min_size=18):
    """Largest font size at which `text` fits `max_w`, plus the wrapped lines."""
    size = start_size
    while size > min_size:
        f = _font(font_kind, size)
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=f) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= 4 and all(draw.textlength(ln, font=f) <= max_w for ln in lines):
            return f, lines
        size = int(size * 0.9)
    f = _font(font_kind, min_size)
    return f, [text]


def quick_cover(project, out_path, accent_hex="#1f6feb", dark=True, style="gradient",
                width=1600, height=2400, author=""):
    """Instant procedural cover: gradient/duotone ground + typography. No ML, no network."""
    if not PIL_OK:
        raise RuntimeError(PIP_HINTS["cover"])
    b = project.bible
    title = book_title(project)
    genre = (b.get("genre") or "").strip()
    acc = _hex_rgb(accent_hex)

    if style == "minimal":
        top = bot = (14, 17, 23) if dark else (246, 247, 249)
    elif style == "duotone":
        top, bot = _shade(acc, 0.35), _shade(acc, 1.25)
    else:                                            # gradient
        top = _shade(acc, 0.28) if dark else _shade(acc, 1.35)
        bot = (10, 13, 18) if dark else (255, 255, 255)

    # paint the ramp one pixel wide and let PIL scale it -- a per-pixel Python
    # loop over 4M pixels takes seconds, this takes milliseconds
    strip = Image.new("RGB", (1, height))
    sp = strip.load()
    for y in range(height):
        sp[0, y] = _mix(top, bot, (y / max(height - 1, 1)) ** 1.25)
    img = strip.resize((width, height), Image.BILINEAR)

    if style != "minimal":
        # a soft off-centre glow so flat gradients don't look like a CSS demo
        glow = Image.new("L", (width, height), 0)
        gd = ImageDraw.Draw(glow)
        r = int(width * 0.62)
        cx, cy = int(width * 0.34), int(height * 0.30)
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=110)
        glow = glow.filter(ImageFilter.GaussianBlur(width // 7))
        img = Image.composite(Image.new("RGB", img.size, _shade(acc, 1.5)), img, glow)

    d = ImageDraw.Draw(img)
    ink = (245, 247, 250) if dark or style != "minimal" else (22, 24, 29)
    dim = _mix(ink, top, 0.45)
    margin = int(width * 0.11)
    inner = width - 2 * margin

    d.rectangle([margin, int(height * 0.055), margin + int(inner * 0.16), int(height * 0.055) + 8],
                fill=acc if style == "minimal" else ink)

    tf, tlines = _fit_text(d, title.upper(), "serif_bold", inner, int(width * 0.135))
    y = int(height * 0.16)
    for ln in tlines:
        d.text((margin, y), ln, font=tf, fill=ink)
        y += int(tf.size * 1.14) if hasattr(tf, "size") else 60

    if genre:
        gf = _font("sans", int(width * 0.030))
        d.text((margin, y + int(height * 0.018)), " · ".join(genre.upper().split()[:5]),
               font=gf, fill=dim)

    if b.get("series"):
        sf = _font("sans_bold", int(width * 0.028))
        d.text((margin, int(height * 0.80)),
               f"{b['series'].replace('_', ' ').upper()}  ·  BOOK {b.get('book_index', 1)}",
               font=sf, fill=acc if style == "minimal" else dim)

    who = (author or "").strip()
    if who:
        af = _font("serif", int(width * 0.048))
        d.text((margin, int(height * 0.855)), who, font=af, fill=ink)

    d.rectangle([margin, int(height * 0.93), width - margin, int(height * 0.93) + 4], fill=dim)
    img.save(out_path, quality=94)
    return set_cover(project, out_path)


def edit_cover(src_path, out_path, crop_ratio=None, brightness=1.0, contrast=1.0,
               title_text="", author_text="", accent_hex="#1f6feb", dark_text=False):
    """The three edits people actually want: reframe, tone, and a text overlay."""
    if not PIL_OK:
        raise RuntimeError(PIP_HINTS["cover"])
    img = Image.open(src_path).convert("RGB")

    if crop_ratio:
        w, h = img.size
        want_w = int(h * crop_ratio)
        if want_w <= w:
            x = (w - want_w) // 2
            img = img.crop((x, 0, x + want_w, h))
        else:
            want_h = int(w / crop_ratio)
            y = max(0, (h - want_h) // 2)
            img = img.crop((0, y, w, y + want_h))

    if abs(brightness - 1.0) > 1e-3:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if abs(contrast - 1.0) > 1e-3:
        img = ImageEnhance.Contrast(img).enhance(contrast)

    if title_text or author_text:
        w, h = img.size
        # a bottom scrim keeps overlaid text readable on any photo
        scrim = Image.new("L", (w, h), 0)
        sd = ImageDraw.Draw(scrim)
        span = int(h * 0.45)
        for i in range(span):
            yy = h - 1 - i
            sd.line([(0, yy), (w, yy)], fill=int(238 * (1 - i / span) ** 1.3))
        img = Image.composite(Image.new("RGB", img.size, (8, 10, 14)), img, scrim)
        d = ImageDraw.Draw(img)
        ink = (18, 20, 25) if dark_text else (246, 248, 251)
        margin = int(w * 0.09)
        y = int(h * 0.985)
        if author_text:
            af = _font("serif", int(w * 0.046))
            y -= int(w * 0.046 * 1.5)
            d.text((margin, y), author_text, font=af, fill=ink)
        if title_text:
            tf, lines = _fit_text(d, title_text.upper(), "serif_bold", w - 2 * margin,
                                  int(w * 0.115))
            step = int(getattr(tf, "size", 60) * 1.12)
            y -= int(w * 0.02) + step * len(lines)
            yy = y
            for ln in lines:
                d.text((margin, yy), ln, font=tf, fill=ink)
                yy += step
            d.rectangle([margin, y - int(w * 0.035), margin + int(w * 0.14),
                         y - int(w * 0.035) + 6], fill=_hex_rgb(accent_hex))

    img.save(out_path, quality=94)
    return out_path


def ai_cover_available():
    return DIFFUSERS_OK


AI_COVER_HINT = (
    "Local AI image generation is off. It needs a multi-GB install:\n\n"
    "    pip install diffusers torch transformers accelerate\n\n"
    "On a CPU-only machine expect several minutes per image and a lot of RAM. "
    "The quick generated cover above is instant and needs nothing."
)


def ai_cover(project, out_path, prompt="", model_id="stabilityai/sd-turbo",
             steps=4, log=None):
    """Optional diffusers path. Deliberately minimal -- it only exists so the
    feature lights up for a user who installs the stack themselves."""
    if not DIFFUSERS_OK:
        raise RuntimeError(AI_COVER_HINT)
    log = log or (lambda _m: None)
    from diffusers import AutoPipelineForText2Image
    import torch
    b = project.bible
    prompt = prompt or (f"book cover art, {b.get('genre') or 'literary fiction'}, "
                        f"{book_title(project)}, dramatic lighting, painterly, no text")
    log(f"loading {model_id} (first run downloads several GB)…")
    pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=torch.float32)
    pipe = pipe.to("cpu")
    log("generating — this takes minutes on CPU…")
    img = pipe(prompt=prompt, num_inference_steps=int(steps), guidance_scale=0.0).images[0]
    img = img.resize((1024, 1536))
    img.save(out_path)
    return set_cover(project, out_path)
