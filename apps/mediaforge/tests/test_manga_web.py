"""The web manga downloader: comix.to goes through PanelForge's fetcher
(faked here, so no Chrome), other sites need Selenium. Fetch returns every
scan group; download lays pages out as Chapter_NNNN/Chapter_NNNN_001.ext and
compiles the PDF and CBZ beside them."""

import sys
import time
from pathlib import Path

import pytest
from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import web_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mediaforge.modules import manga_fetch  # noqa: E402

TITLE = "https://comix.to/title/3nlg-bad-born-blood"
ROWS = [
    {
        "number": 1.0,
        "title": "Ch.1 (Asura Scans)",
        "group": "Asura Scans",
        "url": TITLE + "/1-chapter-1",
    },
    {
        "number": 1.0,
        "title": "Ch.1 (WebToon)",
        "group": "WebToon",
        "url": TITLE + "/2-chapter-1",
    },
    {
        "number": 2.0,
        "title": "Ch.2 (WebToon)",
        "group": "WebToon",
        "url": TITLE + "/3-chapter-2",
    },
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        manga_fetch, "uses_panelforge_fetcher", lambda url: "comix.to" in url
    )

    def fake_fetch(args, log, should_stop=None, progress=None):
        if args[0] == "list":
            assert "--all" in args
            log("found 3 rows")
            return {
                "title": "Bad Born Blood",
                "groups": ["Asura Scans", "WebToon"],
                "chapters": ROWS,
            }
        if args[0] == "get":
            _cmd, _url, folder, name = args[:4]
            out = Path(folder)
            out.mkdir(parents=True, exist_ok=True)
            for i in (1, 2):
                Image.new("RGB", (20, 30), (i * 40, 0, 0)).save(
                    out / f"{name}_{i:03d}.png"
                )
            return {"pages": 2}
        raise AssertionError(args)

    monkeypatch.setattr(manga_fetch, "panelforge_fetch", fake_fetch)
    return TestClient(web_app.app)


def wait(client, job_id):
    for _ in range(100):
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_fetch_lists_every_scan_group(client):
    r = client.post("/api/manga/fetch", json={"url1": TITLE})
    assert r.status_code == 200
    j = wait(client, r.json()["job_id"])
    assert j["status"] == "done", j
    res = j["result"]
    assert res["title"] == "Bad Born Blood"
    assert res["groups"] == ["Asura Scans", "WebToon"]
    assert [(c["num"], c["group"]) for c in res["chapters"]] == [
        (1.0, "Asura Scans"),
        (1.0, "WebToon"),
        (2.0, "WebToon"),
    ]


def test_other_sites_need_selenium(client, monkeypatch):
    monkeypatch.setattr(web_app, "HAVE_SELENIUM", False)
    r = client.post("/api/manga/fetch", json={"url1": "https://example.com/manga"})
    assert r.status_code == 409


def test_download_saves_pages_and_compiles(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        web_app, "HAVE_SELENIUM", False
    )  # the comix.to path must not need it
    r = client.post(
        "/api/manga/download",
        json={
            "chapters": [
                ["Chapter_0001", ROWS[1]["url"]],
                ["Chapter_0002", ROWS[2]["url"]],
            ],
            "out_dir": str(tmp_path),
            "title": "Bad Born Blood",
            "threads": 4,
            "pdf": True,
            "cbz": True,
        },
    )
    assert r.status_code == 200
    j = wait(client, r.json()["job_id"])
    assert j["status"] == "done", j
    root = tmp_path / "Bad Born Blood"
    assert j["result"] == {"out_root": str(root), "done": 2, "failed": 0}
    assert sorted(p.name for p in (root / "Chapter_0001").iterdir()) == [
        "Chapter_0001_001.png",
        "Chapter_0001_002.png",
    ]
    assert (root / "Chapter_0001.pdf").stat().st_size > 0
    assert (root / "Chapter_0002.cbz").stat().st_size > 0


def test_download_refuses_nothing(client):
    assert (
        client.post(
            "/api/manga/download", json={"chapters": [], "out_dir": "/tmp"}
        ).status_code
        == 400
    )
