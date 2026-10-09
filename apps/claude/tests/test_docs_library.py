"""The Docs section: dated docs from the declared sources, in folders, newest
first, searchable, and read-only (only listed paths can be read)."""

import os
import time

import pytest
from fastapi.testclient import TestClient

import docs_library
import web_app


@pytest.fixture
def tree(tmp_path):
    lib = tmp_path / "library"
    (lib / "Scores").mkdir(parents=True)
    (lib / "Scores" / "2026-09-28-codec-scores.md").write_text(
        "# Codec scores\n\nVMAF 94.1 on the test clip.\n"
    )
    (lib / "notes.txt").write_text("date: 2026-09-20\nplain notes about the mech\n")
    old = lib / "undated.md"
    old.write_text(
        "---\nname: undated-thing\ndescription: A memory file.\n---\n\nBody\n"
    )
    stamp = time.mktime((2026, 9, 1, 12, 0, 0, 0, 0, -1))
    os.utime(old, (stamp, stamp))
    (lib / "requirements.txt").write_text("fastapi\n")
    (lib / ".venv").mkdir()
    (lib / ".venv" / "hidden.md").write_text("# no\n")
    deep = lib / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "too-deep.md").write_text("# too deep\n")
    other = tmp_path / "other"
    other.mkdir()
    (other / "README.md").write_text("# Other readme\n")
    (tmp_path / "secret.md").write_text("# not listed\n")
    sources = [
        {"folder": "Library", "root": str(lib), "depth": 3, "ext": [".md", ".txt"]},
        {"folder": "Claude/self", "root": str(other), "depth": 1},
    ]
    return tmp_path, sources


def test_listing_dates_folders_and_order(tree):
    _, sources = tree
    docs = docs_library.listing(sources=sources)
    by_name = {d["name"]: d for d in docs["docs"]}
    assert docs["folders"] == ["Library", "Claude"]
    assert set(by_name) == {
        "2026-09-28-codec-scores.md",
        "notes.txt",
        "undated.md",
        "README.md",
    }
    scores = by_name["2026-09-28-codec-scores.md"]
    assert scores["folder"] == ["Library", "Scores"]
    assert (scores["date"], scores["dated_by"]) == ("2026-09-28", "name")
    assert scores["title"] == "Codec scores"
    assert scores["summary"] == "VMAF 94.1 on the test clip."
    assert (by_name["notes.txt"]["date"], by_name["notes.txt"]["dated_by"]) == (
        "2026-09-20",
        "header",
    )
    undated = by_name["undated.md"]
    assert (undated["date"], undated["dated_by"]) == ("2026-09-01", "modified")
    assert undated["title"] == "undated-thing"
    assert undated["summary"] == "A memory file."
    assert by_name["README.md"]["folder"] == ["Claude", "self"]
    dated = [d["date"] for d in docs["docs"]]
    assert dated == sorted(dated, reverse=True)


def test_search_reads_the_text(tree):
    _, sources = tree
    found = docs_library.listing("vmaf clip", sources=sources)["docs"]
    assert [d["name"] for d in found] == ["2026-09-28-codec-scores.md"]
    assert docs_library.listing("mech", sources=sources)["docs"][0]["name"] == (
        "notes.txt"
    )
    assert docs_library.listing("nothing-like-this", sources=sources)["docs"] == []


def test_read_only_listed_paths(tree):
    tmp, sources = tree
    doc = docs_library.read(
        str(tmp / "library" / "Scores" / "2026-09-28-codec-scores.md"), sources
    )
    assert "VMAF 94.1" in doc["text"]
    for path in (tmp / "secret.md", tmp / "library" / ".venv" / "hidden.md"):
        with pytest.raises(KeyError):
            docs_library.read(str(path), sources)
    with pytest.raises(KeyError):
        docs_library.read(
            str(tmp / "library" / "Scores" / ".." / ".." / "secret.md"), sources
        )


def test_api(tree, monkeypatch):
    tmp, sources = tree
    monkeypatch.setattr(docs_library, "load_sources", lambda path=None: sources)
    client = TestClient(web_app.app)
    assert client.get("/api/docs").status_code == 403
    listed = client.get("/api/docs", headers={"X-Forge": "1"}).json()
    assert len(listed["docs"]) == 4
    one = client.get(
        "/api/docs/read",
        params={"path": str(tmp / "other" / "README.md")},
        headers={"X-Forge": "1"},
    )
    assert one.json()["text"] == "# Other readme\n"
    refused = client.get(
        "/api/docs/read",
        params={"path": str(tmp / "secret.md")},
        headers={"X-Forge": "1"},
    )
    assert refused.status_code == 404


def test_real_sources_file_loads():
    sources = docs_library.load_sources()
    assert sources and all({"folder", "root"} <= set(s) for s in sources)
    assert sources[0]["folder"] == "Library"
