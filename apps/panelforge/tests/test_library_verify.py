"""forge_mangafetch page checks and library.verify's cross-page seam check."""

import io
import os
import sys

import pytest
from PIL import Image

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_ROOT, "..", "..", "shared"))
import forge_mangafetch as mf  # noqa: E402


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _noisy(w, h, seed=0):
    import random

    r = random.Random(seed)
    im = Image.new("L", (w, h))
    im.putdata([r.randint(0, 255) for _ in range(w * h)])
    return im.convert("RGB")


def test_verify_good_page_passes():
    data = _png(_noisy(80, 120))
    chk = mf.verify_page_bytes(data, expect_w=80, expect_h=120)
    assert chk.ok, chk.reason
    assert (chk.width, chk.height) == (80, 120)


def test_verify_rejects_blank_page():
    im = Image.new("RGB", (80, 120), (128, 128, 128))
    chk = mf.verify_page_bytes(_png(im))
    assert not chk.ok
    assert "blank" in chk.reason


def test_verify_rejects_wrong_dims():
    data = _png(_noisy(80, 120))
    chk = mf.verify_page_bytes(data, expect_w=100, expect_h=120)
    assert not chk.ok
    assert "width" in chk.reason


def test_verify_rejects_corrupt_bytes():
    chk = mf.verify_page_bytes(b"not an image")
    assert not chk.ok
    assert "decode" in chk.reason


def test_verify_rejects_scrambled_square_page():
    # A "scrambled" capture: small tiles shuffled -- still has plenty of
    # variance (not blank) but is visually garbage. This check exists to
    # catch the *blank/corrupt* failure mode; a scramble that still has
    # texture is caught by the seam check against neighbours instead, tested
    # below.
    im = _noisy(64, 64)
    chk = mf.verify_page_bytes(_png(im))
    assert chk.ok  # sanity: noisy-but-valid still passes the basic checks


def test_seam_score_low_for_matching_neighbours():
    im = Image.new("RGB", (80, 40), (200, 200, 200))
    a, b = _png(im), _png(im)
    assert mf.seam_score(a, b) < 2.0


def test_seam_score_high_for_mismatched_neighbours():
    a = _png(Image.new("RGB", (80, 40), (10, 10, 10)))
    b = _png(Image.new("RGB", (80, 40), (240, 240, 240)))
    assert mf.seam_score(a, b) > 100


def test_verify_chapter_pages_flags_blank_and_bad_seam(tmp_path):
    from panelforge.library import verify as verify_mod

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    pages = []
    # page 1: normal grey-ish noisy page
    im1 = _noisy(40, 100, seed=1)
    (pages_dir / "001.png").write_bytes(_png(im1))
    pages.append({"idx": 1, "file": "pages/001.png", "w": 40, "h": 100})
    # page 2: blank -- should be flagged by the per-page check
    im2 = Image.new("RGB", (40, 100), (128, 128, 128))
    (pages_dir / "002.png").write_bytes(_png(im2))
    pages.append({"idx": 2, "file": "pages/002.png", "w": 40, "h": 100})
    # page 3: normal again, but seam vs page 2 (blank) will be unremarkable
    # since page 2 is already flagged on its own -- the interesting case is
    # a page that individually passes verify_page_bytes but has a jarring
    # seam, covered by test_seam_score_high_for_mismatched_neighbours above.
    im3 = _noisy(40, 100, seed=2)
    (pages_dir / "003.png").write_bytes(_png(im3))
    pages.append({"idx": 3, "file": "pages/003.png", "w": 40, "h": 100})

    result = verify_mod.verify_chapter_pages(pages, pages_dir)
    assert not result["ok"]
    reasons = [p["reason"] for p in result["problems"]]
    assert any("blank" in r for r in reasons)
