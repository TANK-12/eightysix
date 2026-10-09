"""sources registry, and library.fetch orchestration against a fake source
(no network -- the live comix.to check is done by hand per HANDOFF.md)."""

import importlib
import io
import sys
import types

import pytest
from PIL import Image


class FakeJob:
    def __init__(self):
        self.lines = []
        self.frac = 0.0

    def log(self, msg):
        self.lines.append(msg)

    def progress(self, frac):
        self.frac = frac

    def check(self):
        pass


def _png_bytes(w, h, fill=(30, 60, 90)):
    im = Image.new("RGB", (w, h), fill)
    # add some noise so it isn't "blank"
    px = im.load()
    for i in range(0, w, 3):
        for j in range(0, h, 5):
            px[i, j] = (fill[0] ^ 255, fill[1], fill[2])
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    paths.ensure_roots()
    return tmp_path


@pytest.fixture()
def fake_source(monkeypatch):
    """Registers a source named 'fake' that needs no network: fetch_title
    returns two chapters, fetch_chapter writes synthetic pages straight to
    out_dir/pages and returns their page dicts, like a real source would."""
    mod = types.ModuleType("panelforge.sources.fake")
    mod.SITE = "fake.test"

    def matches(url):
        return "fake.test" in url

    def fetch_title(url, job):
        job.log("fake fetch_title")
        return {
            "title": "Fake Series",
            "chapters": [
                {"number": 1, "title": "Chapter 1", "url": "https://fake.test/c/1"},
                {"number": 2, "title": "Chapter 2", "url": "https://fake.test/c/2"},
            ],
        }

    def fetch_chapter(url, out_dir, job):
        job.log(f"fake fetch_chapter {url}")
        pages_dir = out_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        pages = []
        for idx in (1, 2, 3):
            data = _png_bytes(40, 60)
            (pages_dir / f"{idx:03d}.png").write_bytes(data)
            pages.append(
                {
                    "idx": idx,
                    "file": f"pages/{idx:03d}.png",
                    "w": 40,
                    "h": 60,
                    "capture": "download",
                }
            )
        return pages

    mod.matches = matches
    mod.fetch_title = fetch_title
    mod.fetch_chapter = fetch_chapter
    sys.modules["panelforge.sources.fake"] = mod

    from panelforge import sources

    sources.REGISTRY["fake"] = "panelforge.sources.fake"
    sources._cache.pop("fake", None)
    yield mod
    sources.REGISTRY.pop("fake", None)
    sources._cache.pop("fake", None)
    sys.modules.pop("panelforge.sources.fake", None)


def test_find_for_url(fake_source):
    from panelforge import sources

    assert sources.find_for_url("https://fake.test/title/x") == "fake"
    assert sources.find_for_url("https://nowhere.example/x") is None


def test_list_sources_includes_comix_and_generic():
    from panelforge import sources

    names = {s["name"] for s in sources.list_sources()}
    assert {"comix", "generic"} <= names


def test_fetch_title_writes_series_json(data, fake_source):
    from panelforge.library import fetch as fetch_mod

    job = FakeJob()
    result = fetch_mod.fetch_title("https://fake.test/title/x", job)
    assert result["series"] == "fake-series"
    assert [c["number"] for c in result["chapters"]] == [1, 2]

    from panelforge import paths, store

    sdoc = store.read(paths.series_dir("fake-series") / "series.json")
    assert sdoc["title"] == "Fake Series"


def test_fetch_chapters_all_writes_chapter_json_and_verifies(data, fake_source):
    from panelforge.library import fetch as fetch_mod
    from panelforge import paths, store

    job = FakeJob()
    result = fetch_mod.fetch_chapters("https://fake.test/title/x", None, "all", job)
    assert result["series"] == "fake-series"
    assert len(result["chapters"]) == 2
    for ch in result["chapters"]:
        assert ch["pages"] == 3
        assert ch["verify"]["ok"]

    cdoc = store.read(paths.chapter_dir("fake-series", "0001") / "chapter.json")
    assert cdoc["number"] == 1
    assert len(cdoc["pages"]) == 3
    assert all(p["capture"] == "download" for p in cdoc["pages"])
    assert all("sha1" in p for p in cdoc["pages"])


def test_fetch_chapters_selected_numbers_only(data, fake_source):
    from panelforge.library import fetch as fetch_mod

    job = FakeJob()
    result = fetch_mod.fetch_chapters("https://fake.test/title/x", None, [2], job)
    assert [c["chapter"] for c in result["chapters"]] == ["0002"]
