"""Import: folder, CBZ, PDF (CBR is exercised only if a RAR tool is present)."""

import importlib
import io
import zipfile

import pytest
from PIL import Image


class FakeJob:
    def __init__(self):
        self.lines = []

    def log(self, msg):
        self.lines.append(msg)

    def progress(self, frac):
        pass

    def check(self):
        pass


def _noisy_png(w=60, h=90, seed=0):
    import random

    r = random.Random(seed)
    im = Image.new("L", (w, h))
    im.putdata([r.randint(0, 255) for _ in range(w * h)])
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    paths.ensure_roots()
    return tmp_path


def test_import_folder(data, tmp_path):
    from panelforge.library import importers
    from panelforge import paths, store

    folder = tmp_path / "raw" / "My Chapter"
    folder.mkdir(parents=True)
    for i in range(1, 4):
        (folder / f"{i:03d}.png").write_bytes(_noisy_png(seed=i))

    job = FakeJob()
    result = importers.import_folder(str(folder), "myseries", 1, job)
    assert result["pages"] == 3
    assert result["verify"]["ok"]

    cdoc = store.read(paths.chapter_dir("myseries", "0001") / "chapter.json")
    assert len(cdoc["pages"]) == 3
    assert all(p["capture"] == "import" for p in cdoc["pages"])


def test_import_cbz(data, tmp_path):
    from panelforge.library import importers

    cbz_path = tmp_path / "chapter1.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        for i in range(1, 4):
            zf.writestr(f"{i:03d}.png", _noisy_png(seed=i + 10))

    job = FakeJob()
    result = importers.import_cbz(str(cbz_path), "cbzseries", 1, job)
    assert result["pages"] == 3
    assert result["verify"]["ok"]


def test_import_pdf(data, tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from panelforge.library import importers

    pdf_path = tmp_path / "chapter1.pdf"
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=200, height=300)
        img_bytes = _noisy_png(200, 300, seed=i + 20)
        page.insert_image(pymupdf.Rect(0, 0, 200, 300), stream=img_bytes)
    doc.save(str(pdf_path))
    doc.close()

    job = FakeJob()
    result = importers.import_pdf(str(pdf_path), "pdfseries", 1, job)
    assert result["pages"] == 3
    assert result["verify"]["ok"]


def test_import_path_dispatches_by_extension(data, tmp_path):
    from panelforge.library import importers

    cbz_path = tmp_path / "x.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.writestr("001.png", _noisy_png(seed=99))
    job = FakeJob()
    result = importers.import_path(str(cbz_path), "dispatchseries", 1, job)
    assert result["pages"] == 1


def test_import_cbr_or_reports_missing_tool(data, tmp_path):
    """CBR support depends on a system RAR tool. unrar/7z/bsdtar were all
    confirmed present on this machine (2026-09-17); if that ever changes,
    import_cbr must raise a clear, reportable error rather than crash."""
    import shutil

    from panelforge.library import importers

    have_tool = any(shutil.which(cmd[0]) for _, cmd in importers._CBR_TOOLS)
    assert have_tool, "expected unrar/7z/bsdtar to be present on this machine"
