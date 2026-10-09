"""Detect: lettering style measures, merge on re-detect, the pipeline and API
on a synthetic two-page chapter (never the real ~/PanelForgeData)."""

import importlib
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/noto/"
HAVE_TESS = shutil.which("tesseract") is not None


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    paths.ensure_roots()
    return tmp_path


def _font(name, size):
    return ImageFont.truetype(FONT_DIR + name, size)


def _text_image(text, name="NotoSans-Regular.ttf", size=40, shear=0.0):
    img = Image.new("L", (60 + size * len(text), size * 2), 255)
    ImageDraw.Draw(img).text((20, size // 3), text, font=_font(name, size), fill=0)
    if shear:
        w, h = img.size
        img = img.transform(
            (w + int(abs(shear) * h), h),
            Image.Transform.AFFINE,
            (1, shear, -shear * h if shear > 0 else 0, 0, 1, 0),
            fillcolor=255,
        )
    return np.array(img)


def test_style_measures_bold_italic_and_plain():
    from panelforge.detect import style

    def measure(arr):
        ys, xs = np.nonzero(arr < 128)
        return style.measure_word(
            arr,
            (
                int(xs.min()),
                int(ys.min()),
                int(xs.max() - xs.min() + 1),
                int(ys.max() - ys.min() + 1),
            ),
        )

    plain = measure(_text_image("HELLO"))
    bold = measure(_text_image("HELLO", "NotoSans-Bold.ttf"))
    italic = measure(_text_image("HELLO", shear=0.3))
    assert bold["stroke"] > 1.25 * plain["stroke"]
    assert abs(plain["shear"]) < style.ITALIC_SHEAR
    assert italic["shear"] > style.ITALIC_SHEAR
    assert plain["rough"] < style.TREMBLE_ROUGH


def test_bubble_style_bold_words_and_relative_scale():
    from panelforge.detect import style

    words = [
        {"text": "I", "stroke": 4.0, "shear": 0.0, "rough": 1.05, "ink": 50},
        {"text": "WILL", "stroke": 4.2, "shear": 0.0, "rough": 1.05, "ink": 200},
        {"text": "NEVER", "stroke": 7.0, "shear": 0.0, "rough": 1.05, "ink": 300},
        {"text": "YIELD", "stroke": 4.1, "shear": 0.0, "rough": 1.05, "ink": 250},
    ]
    st = style.bubble_style(
        "shout",
        {"roughness": 1.3, "defects": 12},
        True,
        words,
        30.0,
        0.05,
        "#000000",
        20.0,
        4.0,
    )
    assert st["outline"] == "jagged"
    assert st["bold_words"] == ["NEVER"]
    assert st["text_scale"] == 1.5
    assert st["stroke_weight"] == pytest.approx(4.15 / 4.0, abs=0.02)
    assert not st["italic"] and not st["wavy"] and not st["trembling"]
    assert (
        style.outline_for("speech", {"roughness": 1.0, "defects": 0}, False) == "none"
    )
    assert style.outline_for("thought", {}, True) == "cloud"
    assert (
        style.outline_for("speech", {"rect_fill": 0.95, "defects": 0}, True) == "rect"
    )


def test_merge_keeps_ids_and_edits():
    from panelforge.detect import merge

    old = [
        {
            "id": "b0001",
            "box": [0, 0, 100, 50],
            "text": "old one",
            "edited": False,
            "order": 1,
        },
        {
            "id": "b0002",
            "box": [0, 100, 100, 50],
            "text": "fixed by hand",
            "edited": True,
            "order": 2,
        },
        {
            "id": "b0003",
            "box": [0, 300, 100, 50],
            "text": "drawn in by hand",
            "edited": True,
            "order": 3,
        },
        {
            "id": "b0004",
            "box": [0, 500, 100, 50],
            "text": "stale",
            "edited": False,
            "order": 4,
        },
    ]
    new = [
        {
            "id": "b0001",
            "box": [2, 1, 100, 50],
            "text": "new one",
            "edited": False,
            "order": 1,
        },
        {
            "id": "b0002",
            "box": [0, 102, 100, 50],
            "text": "re-read",
            "edited": False,
            "order": 2,
        },
        {
            "id": "b0003",
            "box": [0, 200, 100, 50],
            "text": "brand new",
            "edited": False,
            "order": 3,
        },
    ]
    out = merge.merge(old, new, "b")
    by_id = {o["id"]: o for o in out}
    assert by_id["b0001"]["text"] == "new one"
    assert by_id["b0002"]["text"] == "fixed by hand" and by_id["b0002"]["edited"]
    assert by_id["b0003"]["text"] == "drawn in by hand"
    assert "b0004" not in by_id
    assert by_id["b0005"]["text"] == "brand new"
    assert [o["order"] for o in out] == [1, 2, 3, 4]
    assert [o["box"][1] for o in out] == sorted(o["box"][1] for o in out)


def make_chapter(root, series="synthetic", chapter="0001"):
    """Two 800x1280 pages: four framed panels with a drawing and a bubble each."""
    from panelforge import store

    ch = root / "series" / series / "chapters" / chapter
    (ch / "pages").mkdir(parents=True)
    texts = ["HELLO THERE FRIEND", "WE MUST GO NOW", "WAIT FOR ME", "THE END IS NEAR"]
    pages = []
    k = 0
    for pi in range(2):
        img = Image.new("RGB", (800, 1280), (255, 255, 255))
        d = ImageDraw.Draw(img)
        for row in range(2):
            y0 = 60 + row * 600
            d.rectangle(
                [40, y0, 760, y0 + 520],
                fill=(120 + 30 * k, 140, 160),
                outline=(0, 0, 0),
                width=5,
            )
            d.ellipse(
                [300, y0 + 220, 500, y0 + 420],
                fill=(230, 200, 180),
                outline=(0, 0, 0),
                width=4,
            )
            d.rectangle([250, y0 + 400, 550, y0 + 515], fill=(60, 60, 120))
            d.ellipse(
                [80, y0 + 40, 560, y0 + 190],
                fill=(255, 255, 255),
                outline=(0, 0, 0),
                width=4,
            )
            d.text(
                (120, y0 + 85),
                texts[k],
                font=_font("NotoSans-Bold.ttf", 34),
                fill=(0, 0, 0),
            )
            k += 1
        f = f"pages/{pi + 1:03d}.png"
        img.save(ch / f)
        pages.append(
            {
                "idx": pi + 1,
                "file": f,
                "w": 800,
                "h": 1280,
                "sha1": "",
                "capture": "import",
            }
        )
    store.write(
        ch / "chapter.json",
        {
            "schema": 1,
            "series": series,
            "chapter": chapter,
            "number": 1,
            "title": "t",
            "source": {},
            "layout": "strip",
            "reading": "ttb",
            "pages": pages,
        },
    )
    return ch, texts


def test_pipeline_and_api_on_synthetic_chapter(data):
    from fastapi.testclient import TestClient

    from panelforge import jobs, store
    from panelforge.detect import pipeline
    import web_app

    ch, texts = make_chapter(data)
    st = pipeline.run_detect(ch, None)
    assert st["panels"] == 4, st
    panels = store.read(ch / "panels.json")["panels"]
    assert [p["id"] for p in panels] == ["p0001", "p0002", "p0003", "p0004"]
    for p in panels:
        crop = cv2.imread(str(ch / p["image"]))
        assert crop is not None and crop.shape[1] == p["box"][2]
    bubbles = store.read(ch / "bubbles.json")["bubbles"]
    if HAVE_TESS:
        assert st["bubbles_with_text"] >= 3, st
        joined = " ".join(b["text"].lower() for b in bubbles)
        hits = sum(1 for t in texts if t.lower() in joined)
        assert hits >= 3, joined
        assert all(
            "style" in b
            and b["style"]["outline"]
            in ("smooth", "wobbly", "rect", "cloud", "jagged", "dashed", "none")
            for b in bubbles
        )
        assert {b["panel_id"] for b in bubbles} <= {p["id"] for p in panels}

    # the API: edit one bubble, re-detect, the edit survives with its id
    c = TestClient(web_app.app)
    doc = c.get("/api/chapters/synthetic/0001/bubbles").json()
    assert doc["bubbles"] == bubbles
    if bubbles:
        doc["bubbles"][0]["text"] = "Fixed by Emerson"
        put = c.put("/api/chapters/synthetic/0001/bubbles", json=doc).json()
        assert put["bubbles"][0]["edited"] is True
        bid = put["bubbles"][0]["id"]
        r = c.post("/api/chapters/synthetic/0001/detect").json()
        job = jobs.get(r["job_id"])
        assert job is not None
        job = jobs.wait(job, timeout=300)
        assert job.state == "done", job.error
        again = c.get("/api/chapters/synthetic/0001/bubbles").json()["bubbles"]
        kept = [b for b in again if b["id"] == bid]
        assert kept and kept[0]["text"] == "Fixed by Emerson" and kept[0]["edited"]
        assert (
            c.get("/api/chapters/synthetic/0001/detect/stats").json()["edited_bubbles"]
            == 1
        )
    assert c.get("/api/chapters/synthetic/0001/panels/p0001/image").status_code == 200
    # the crops are a cache: with them cleaned away the panel is cut from the
    # strip instead (the Timeline's shot thumbnails were blank without this)
    shutil.rmtree(ch / "work" / "detect" / "panels")
    r = c.get("/api/chapters/synthetic/0001/panels/p0001/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert c.get("/api/chapters/synthetic/0001/panels/p9999/image").status_code == 404
    assert c.get("/api/chapters/nope/0001/panels").status_code == 404


def test_panel_box_grows_to_cover_its_lettering():
    """A caption drawn a few pixels past the gutter edge must stay in the crop."""
    from panelforge.detect import panels as P

    strip = {"width": 800, "height": 2000}
    panels = [
        {"id": "p0001", "box": [100, 100, 600, 400], "edited": False},
        {"id": "p0002", "box": [100, 560, 600, 400], "edited": False},
    ]
    bubbles = [
        {
            "id": "b1",
            "panel_id": "p0001",
            "box": [94, 380, 612, 60],
        },  # wider than the panel
        {"id": "b2", "panel_id": "p0002", "box": [200, 600, 100, 40]},  # well inside
    ]
    changed = P.grow_to_text(panels, bubbles, strip)
    assert changed == ["p0001"]
    x, y, w, h = panels[0]["box"]
    assert x <= 94 and x + w >= 706  # the caption is inside now
    assert panels[1]["box"] == [100, 560, 600, 400]  # untouched


def test_panel_growth_is_capped_and_stays_out_of_its_neighbour():
    from panelforge.detect import panels as P

    strip = {"width": 800, "height": 2000}
    panels = [
        {"id": "p0001", "box": [100, 100, 600, 400], "edited": False},
        {"id": "p0002", "box": [100, 520, 600, 400], "edited": False},
    ]
    bubbles = [
        # a caption box that reaches far below, into the next panel
        {"id": "b1", "panel_id": "p0001", "box": [200, 300, 100, 400]},
        # and one that would drag the panel way off to the left
        {"id": "b2", "panel_id": "p0001", "box": [-300, 200, 100, 40]},
    ]
    P.grow_to_text(panels, bubbles, strip)
    x, y, w, h = panels[0]["box"]
    assert y + h <= 520  # never eats into p0002
    assert x >= 100 - 48  # capped growth, and never past the strip edge
    assert x >= 0


def test_a_hand_edited_panel_is_never_grown():
    from panelforge.detect import panels as P

    strip = {"width": 800, "height": 2000}
    panels = [{"id": "p0001", "box": [100, 100, 600, 400], "edited": True}]
    bubbles = [{"id": "b1", "panel_id": "p0001", "box": [80, 380, 640, 60]}]
    assert P.grow_to_text(panels, bubbles, strip) == []
    assert panels[0]["box"] == [100, 100, 600, 400]


def _tilted_caption_page(tmp_path, text, angle):
    """One white page with a level balloon and a borderless caption drawn at
    `angle` degrees (positive runs downhill to the right, like image y)."""
    from PIL import Image as PImage

    page = PImage.new("RGB", (800, 1280), (255, 255, 255))
    d = ImageDraw.Draw(page)
    d.ellipse([80, 60, 620, 220], fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    d.text(
        (130, 105), "HELLO THERE FRIEND", font=_font("NotoSans-Bold.ttf", 34), fill=0
    )
    cap = PImage.new("RGBA", (620, 260), (255, 255, 255, 0))
    cd = ImageDraw.Draw(cap)
    for i, line in enumerate(text.split("\n")):
        cd.text(
            (30, 20 + i * 70),
            line,
            font=_font("NotoSerif-Bold.ttf", 44),
            fill=(150, 40, 30, 255),
        )
    # PIL rotates counter-clockwise; a downhill-to-the-right baseline is clockwise
    cap = cap.rotate(-angle, resample=PImage.Resampling.BICUBIC, expand=True)
    page.paste(cap, (90, 500), cap)
    (tmp_path / "pages").mkdir(exist_ok=True)
    page.save(tmp_path / "pages" / "001.png")
    strip = {
        "schema": 1,
        "width": 800,
        "height": 1280,
        "segments": [{"page_idx": 1, "strip_y": 0, "h": 1280, "file": "pages/001.png"}],
    }
    return strip


def test_tilted_lettering_gets_its_skew_measured(tmp_path):
    from panelforge.detect import text as T
    from panelforge.detect.strip import StripReader

    strip = _tilted_caption_page(
        tmp_path, "TO ELIMINATE\nANY ENEMIES WHO\nWOULD THREATEN", -17.0
    )
    reader = StripReader(tmp_path, strip)
    blocks = [b for b in T.find_blocks(reader.rows(0, 1280)) if b.polarity == "dark"]
    by_y = sorted(blocks, key=lambda b: b.box[1])
    assert len(by_y) == 2, [(b.box, len(b.lines)) for b in blocks]
    level, tilted = by_y
    assert abs(level.angle) < 1.5, level.angle
    assert -20 < tilted.angle < -14, tilted.angle
    # the three drawn lines stay in one block, even though wide word gaps
    # may split a tilted line into pieces
    assert len(tilted.lines) >= 3 and tilted.box[3] > 200, tilted.box
    # letter height ignores punctuation and specks
    assert all(l.h > 20 for l in tilted.lines), [l.h for l in tilted.lines]


@pytest.mark.skipif(not HAVE_TESS, reason="tesseract not installed")
def test_tilted_caption_is_read_after_levelling(tmp_path):
    from panelforge.detect import bubbles as Bu
    from panelforge.detect.strip import StripReader

    strip = _tilted_caption_page(
        tmp_path, "TO ELIMINATE\nANY ENEMIES WHO\nWOULD THREATEN", -17.0
    )
    reader = StripReader(tmp_path, strip)
    panels = [{"id": "p0001", "box": [0, 0, 800, 1280], "order": 1}]
    out = Bu.detect_bubbles(reader, panels)
    texts = {b["text"].lower() for b in out}
    joined = " ".join(sorted(texts))
    assert "hello there friend" in joined, joined
    assert "eliminate" in joined and "threaten" in joined, joined
    cap = [b for b in out if "eliminate" in b["text"].lower()][0]
    assert cap["kind"] == "caption", cap["kind"]
    assert cap["ocr_conf"] >= 0.7, cap["ocr_conf"]


def test_light_lettering_in_a_dark_box_is_screen_text():
    from panelforge.detect import bubbles as Bu

    c = Bu.Cand([], (0, 0, 10, 10), "light", 12.0)
    c.balloon = object()  # a closed box was found
    c.raw = "SYSTEM ERROR DETECTED"
    c.feats = {"rect_fill": 0.87}
    assert Bu.is_screen_text(c)
    c.feats = {"rect_fill": 0.5}  # a rounded dark balloon with a sentence: speech
    assert not Bu.is_screen_text(c)
    c.raw = "ERROR"  # ... but a single word in it is a readout
    assert Bu.is_screen_text(c)
    c.raw = "SYSTEM ERROR DETECTED"
    c.feats = {"rect_fill": 0.9}
    c.polarity = "dark"  # ordinary dark letters in a caption box
    assert not Bu.is_screen_text(c)


def test_a_sentence_in_a_dark_box_is_a_caption_not_a_readout():
    from panelforge.detect import bubbles as Bu

    c = Bu.Cand([], (0, 0, 10, 10), "light", 12.0)
    c.balloon = object()
    c.feats = {"rect_fill": 0.9}
    c.raw = "AND EARTH WAS DESTROYED."  # chapter 1's white-on-black prologue
    assert not Bu.is_screen_text(c)
    c.raw = "TARGET LOCKED"
    assert Bu.is_screen_text(c)


def test_open_lettering_is_a_sound_word_only_when_big_for_the_chapter():
    """A fixed 28 px made every caption of a high-resolution webtoon a sound
    word (chapter 1, 16:50): the bar is relative to the usual letter height."""
    from panelforge.detect import bubbles as Bu

    # busy art around the lettering, so the ring is not a flat caption box
    img = np.random.default_rng(1).integers(0, 255, (200, 200, 3), dtype=np.uint8)

    class Reader:
        def crop(self, box):
            x, y, w, h = [int(v) for v in box]
            return img[y : y + h, x : x + w]

    c = Bu.Cand([], (40, 40, 100, 30), "dark", 30.0)  # 30 px letters, no balloon
    Bu.classify(Reader(), c, med_line_h=28.0)  # usual letters are 28 px
    assert c.kind == "caption"
    Bu.classify(Reader(), c, med_line_h=12.0)  # usual letters are 12 px
    assert c.kind == "sfx"
    c.raw = "..AND EARTH WAS DESTROYED."  # big, but a sentence: a caption
    Bu.classify(Reader(), c, med_line_h=12.0)
    assert c.kind == "caption"


def test_series_words_api_round_trips_and_feeds_the_glossary(data):
    from fastapi.testclient import TestClient

    from panelforge import paths
    from panelforge.detect import normalize as N
    import web_app

    ch = paths.chapter_dir("synthetic", "0001")
    ch.mkdir(parents=True, exist_ok=True)
    c = TestClient(web_app.app)
    r = c.put(
        "/api/series/synthetic/words",
        json={"words": ["Novus", " "], "banned": ["yoou"]},
    )
    assert r.status_code == 200 and r.json()["words"] == ["Novus"]
    got = c.get("/api/series/synthetic/words").json()
    assert got["words"] == ["Novus"] and got["banned"] == ["yoou"]
    assert "novus" in got["learned"]
    N.GLOSSARY.clear()


def test_caption_slanting_downhill_is_read_too(tmp_path):
    """Emerson (18:25): uphill text reads, downhill text does not."""
    from panelforge.detect import bubbles as Bu
    from panelforge.detect.strip import StripReader

    strip = _tilted_caption_page(
        tmp_path, "TO ELIMINATE\nANY ENEMIES WHO\nWOULD THREATEN", 25.0
    )
    reader = StripReader(tmp_path, strip)
    panels = [{"id": "p0001", "box": [0, 0, 800, 1280], "order": 1}]
    out = Bu.detect_bubbles(reader, panels)
    joined = " ".join(sorted(b["text"].lower() for b in out))
    assert "eliminate" in joined and "threaten" in joined, joined
    # the tilt is kept on the record, so tilted lettering can be found later
    tilted = [b for b in out if "threaten" in b["text"].lower()]
    assert tilted and 14 < tilted[0]["angle"] < 36, [b["angle"] for b in out]


def test_balloon_crop_route_cuts_the_drawn_balloon_with_a_margin(data):
    """The lines editor shows each line's balloon as drawn: the route cuts
    the balloon's box (plus a margin) out of the strip and answers a JPEG."""
    import io

    from fastapi.testclient import TestClient

    from panelforge import paths, store
    import web_app

    ch = paths.chapter_dir("synthetic", "0001")
    (ch / "pages").mkdir(parents=True, exist_ok=True)
    page = Image.new("RGB", (800, 600), (255, 255, 255))
    page.paste((200, 30, 30), (100, 200, 300, 260))  # a red "balloon"
    page.save(ch / "pages" / "001.png")
    store.write(ch / "chapter.json", {"schema": 1, "id": "0001"})
    store.write(
        ch / "strip.json",
        {
            "schema": 1,
            "width": 800,
            "height": 600,
            "segments": [
                {"page_idx": 1, "strip_y": 0, "h": 600, "file": "pages/001.png"}
            ],
        },
    )
    store.write(
        ch / "bubbles.json",
        {"schema": 1, "bubbles": [{"id": "b0001", "box": [100, 200, 200, 60]}]},
    )
    c = TestClient(web_app.app)
    r = c.get("/api/chapters/synthetic/0001/bubbles/b0001/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (200 + 28, 60 + 28), img.size
    assert img.getpixel((14 + 100, 14 + 30))[0] > 150  # the balloon is inside
    assert img.getpixel((2, 2))[0] > 240  # and the margin is the page around it
    assert c.get("/api/chapters/synthetic/0001/bubbles/nope/image").status_code == 404


def test_a_doubtful_read_is_not_rescued_by_splitting_its_words():
    """ "_WASIN HE WORKGS." at 0.50 was spoken aloud on chapter 1 because
    WASIN -> WAS IN and WORKGS -> WOR KGS both "split into known words".
    A split only counts on a confident read; the same words at 0.8 pass."""
    from panelforge.detect import bubbles as Bu

    c = Bu.Cand([], (0, 0, 100, 40), "light", 20.0)
    c.balloon = object()
    c.raw = "_WASIN HE WORKGS."
    c.conf = 0.501
    assert not Bu.looks_like_text(c)
    c.raw = "WASIN THE WORKSHOP."
    c.conf = 0.8
    assert Bu.looks_like_text(c)


def test_emersons_downhill_caption_is_read(tmp_path):
    """Chapter 1, page 8: "THE IMPERIAL GUARD'S SOLE REASON FOR BEING IS IN
    THIS..." runs downhill at about 25 degrees and was never read -- the
    last letters of one line sit at the height of the first letters of the
    next, so the old grouping made one six-line "line". Real crop."""
    import cv2

    from panelforge.detect import bubbles as Bu
    from panelforge.detect import text as T
    from panelforge.detect.strip import StripReader

    crop = cv2.imread(
        str(Path(__file__).parent / "fixtures" / "c01-p08-downhill-caption.jpg")
    )
    assert crop is not None
    blocks = [b for b in T.find_blocks(crop) if b.polarity == "dark" and b.box[2] > 300]
    assert blocks, "no block formed"
    assert 4 <= len(blocks[0].lines) <= 7, [len(l.comps) for l in blocks[0].lines]
    assert 15 < blocks[0].angle < 35, blocks[0].angle
    # and the reader's whole path gets the words
    page = cv2.copyMakeBorder(
        crop,
        0,
        1280 - crop.shape[0],
        0,
        800 - crop.shape[1],
        cv2.BORDER_CONSTANT,
        value=(255, 255, 255),
    )
    (tmp_path / "pages").mkdir()
    cv2.imwrite(str(tmp_path / "pages" / "001.png"), page)
    strip = {
        "schema": 1,
        "width": 800,
        "height": 1280,
        "segments": [{"page_idx": 1, "strip_y": 0, "h": 1280, "file": "pages/001.png"}],
    }
    out = Bu.detect_bubbles(
        StripReader(tmp_path, strip),
        [{"id": "p0001", "box": [0, 0, 800, 1280], "order": 1}],
    )
    joined = " ".join(b["text"].lower() for b in out)
    assert "imperial" in joined and "reason" in joined, joined
