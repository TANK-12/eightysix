"""Kindle PDF export: splitting a tall webtoon strip at blank gutter rows,
and the 'full' preset leaving pages alone."""

import importlib
import io

import pytest
from PIL import Image


class FakeJob:
    def log(self, msg):
        pass


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    paths.ensure_roots()
    return tmp_path


def _synthetic_strip(width=800, panel_h=900, n_panels=3, gutter_h=30):
    """n_panels of noisy 'art' separated by flat grey gutters, like a
    webtoon strip with clear panel breaks."""
    import random

    r = random.Random(42)
    total_h = n_panels * panel_h + (n_panels - 1) * gutter_h
    im = Image.new("RGB", (width, total_h), (245, 245, 245))
    y = 0
    for p in range(n_panels):
        panel = Image.new("L", (width, panel_h))
        panel.putdata([r.randint(0, 255) for _ in range(width * panel_h)])
        im.paste(panel.convert("RGB"), (0, y))
        y += panel_h
        y += gutter_h  # gutter left as flat background
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue(), total_h


def test_split_kindle_cuts_in_gutters_not_through_art():
    from panelforge.library import kindle

    data, total_h = _synthetic_strip()
    pieces = kindle.split_kindle(data)
    assert len(pieces) > 1

    # every cut boundary should land inside (or very near) one of the flat
    # gutter bands, not inside a noisy panel.
    panel_h, gutter_h, n_panels = 900, 30, 3
    gutter_bands = []
    y = panel_h
    for _ in range(n_panels - 1):
        gutter_bands.append((y - 5, y + gutter_h + 5))
        y += gutter_h + panel_h

    heights = [Image.open(io.BytesIO(p)).size[1] for p in pieces]
    assert sum(heights) == total_h

    cut_y = 0
    boundaries = []
    for h in heights[:-1]:
        cut_y += h
        boundaries.append(cut_y)
    for b in boundaries:
        assert any(lo <= b <= hi for lo, hi in gutter_bands), (b, gutter_bands)


def test_split_kindle_falls_back_to_hard_cut_without_gutter():
    from panelforge.library import kindle
    import random

    r = random.Random(7)
    im = Image.new("L", (800, 3000))
    im.putdata([r.randint(0, 255) for _ in range(800 * 3000)])
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG")
    pieces = kindle.split_kindle(buf.getvalue())
    assert len(pieces) > 1
    heights = [Image.open(io.BytesIO(p)).size[1] for p in pieces]
    assert sum(heights) == 3000


def test_split_kindle_short_page_not_split():
    from panelforge.library import kindle

    im = Image.new("RGB", (800, 400), (100, 100, 100))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    pieces = kindle.split_kindle(buf.getvalue())
    assert len(pieces) == 1


def test_export_pdf_full_preset_and_toc(data, tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from panelforge.library import kindle
    from panelforge import paths, store

    for chapter_num, chapter in ((1, "0001"), (2, "0002")):
        cdir = paths.chapter_dir("exportseries", chapter)
        pages_dir = cdir / "pages"
        pages_dir.mkdir(parents=True)
        for i in range(1, 3):
            im = Image.new("RGB", (80, 120), (10 * i, 20, 30))
            im.save(pages_dir / f"{i:03d}.png")
        store.write(
            cdir / "chapter.json",
            {
                "schema": 1,
                "series": "exportseries",
                "chapter": chapter,
                "number": chapter_num,
                "title": f"Chapter {chapter_num}",
                "source": {"site": "test", "url": ""},
                "layout": "strip",
                "reading": "ttb",
                "pages": [
                    {
                        "idx": i,
                        "file": f"pages/{i:03d}.png",
                        "w": 80,
                        "h": 120,
                        "capture": "import",
                    }
                    for i in (1, 2)
                ],
            },
        )

    out = tmp_path / "out.pdf"
    kindle.export_pdf("exportseries", ["0001", "0002"], "full", out, FakeJob())
    assert out.exists()

    doc = pymupdf.open(str(out))
    assert doc.page_count == 4  # 2 pages per chapter, unsplit
    toc = doc.get_toc()
    assert [t[1] for t in toc] == ["Chapter 1", "Chapter 2"]
    assert toc[0][2] == 1
    assert toc[1][2] == 3
    doc.close()


def test_resolve_chapters_all_and_selected(data):
    from panelforge.library import kindle
    from panelforge import paths, store

    for chapter in ("0001", "0002", "0003"):
        cdir = paths.chapter_dir("rseries", chapter)
        (cdir / "pages").mkdir(parents=True)

    assert kindle.resolve_chapters("rseries", "all") == ["0001", "0002", "0003"]
    assert kindle.resolve_chapters("rseries", [2]) == ["0002"]
    assert kindle.resolve_chapters("rseries", ["0001", "0003"]) == ["0001", "0003"]
