"""Shared fixtures: a throwaway Komikku-shaped sqlite db + page files, and
InkForge's own data dir, both under tmp_path so tests never touch the real
~/.local/share/komikku or ~/InkForgeData."""

from __future__ import annotations

import importlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def komikku_fixture(tmp_path):
    db_path = tmp_path / "komikku.db"
    data_dir = tmp_path / "komikku_data"
    server_dir = data_dir / "mangakawaii_en"
    manga_dir = server_dir / "Test Manga"
    chapter_dir = manga_dir / "1"
    chapter_dir.mkdir(parents=True)
    for i in range(1, 4):
        (chapter_dir / f"{i:02d}.jpg").write_bytes(b"\xff\xd8\xff" + bytes([i]))

    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE mangas (id INTEGER PRIMARY KEY, name TEXT, authors TEXT, "
        "status TEXT, in_library INTEGER)"
    )
    con.execute(
        "CREATE TABLE chapters (id INTEGER PRIMARY KEY, manga_id INTEGER, "
        "title TEXT, num TEXT, pages json, downloaded INTEGER, "
        "read_progress TEXT, last_page_read_index INTEGER)"
    )
    con.execute(
        "INSERT INTO mangas VALUES (1, 'Test Manga', 'Some Author', 'ongoing', 1)"
    )
    pages_json = json.dumps(
        [{"image": f"{i:02d}.jpg", "index": i - 1} for i in range(1, 4)]
    )
    con.execute(
        "INSERT INTO chapters VALUES (10, 1, 'Chapter 1', '1', ?, 1, 0, 0)",
        (pages_json,),
    )
    con.commit()
    con.close()
    return {"db_path": db_path, "data_dir": data_dir}


@pytest.fixture()
def client(tmp_path, komikku_fixture, monkeypatch):
    monkeypatch.setenv("INKFORGE_KOMIKKU_DB", str(komikku_fixture["db_path"]))
    monkeypatch.setenv("INKFORGE_KOMIKKU_DATA_DIR", str(komikku_fixture["data_dir"]))
    monkeypatch.setenv("INKFORGE_DATA_DIR", str(tmp_path / "inkforge_data"))

    import web_app

    importlib.reload(web_app)
    return TestClient(web_app.app)
