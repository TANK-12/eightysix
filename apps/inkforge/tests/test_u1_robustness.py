"""U1 sweep (2026-10-08): bad input and broken files get a plain answer,
never a 500, and a failed import leaves nothing behind."""

from __future__ import annotations

import io
import json
import threading

import web_app


def _make_pdf_bytes(n_pages: int = 1) -> bytes:
    import pymupdf as fitz

    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page().insert_text((72, 72), "hello")
    data = doc.tobytes()
    doc.close()
    return data


def _import(client, data: bytes, name: str = "book.pdf"):
    return client.post(
        "/api/pdf/import",
        files={"file": (name, io.BytesIO(data), "application/pdf")},
    )


def test_a_broken_pdf_is_refused_and_leaves_no_folder(client):
    r = _import(client, b"this is not a pdf at all")
    assert r.status_code == 400
    assert "not a readable PDF" in r.json()["detail"]
    r = _import(client, b"%PDF-1.4\n garbage that is not a real document")
    assert r.status_code == 400
    leftovers = [p for p in web_app.PDF_DIR.glob("*") if p.is_dir()]
    assert leftovers == []
    assert client.get("/api/library").json()["pdfs"] == []


def test_a_disk_error_is_named_not_blamed_on_the_pdf(client, monkeypatch):
    # Critic (2026-10-08): disk full or no permission read as "not a
    # readable PDF". It is a 500 that says what failed, and still cleans up.
    def full_disk(file, doc_dir):
        doc_dir.mkdir(parents=True)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(web_app, "_store_and_rasterize", full_disk)
    r = _import(client, _make_pdf_bytes())
    assert r.status_code == 500
    assert "No space left on device" in r.json()["detail"]
    assert [p for p in web_app.PDF_DIR.glob("*") if p.is_dir()] == []


def test_a_good_import_after_a_bad_one_still_works(client):
    assert _import(client, b"nope").status_code == 400
    r = _import(client, _make_pdf_bytes(2), "Ünïcode 漫画.pdf")
    assert r.status_code == 200
    assert r.json()["title"] == "Ünïcode 漫画"
    assert len(client.get("/api/library").json()["pdfs"]) == 1


def test_progress_saved_flag_and_bounds(client):
    r = client.get("/api/progress/pdf:abc")
    assert r.json() == {"page": 0, "saved": False}
    assert client.post("/api/progress/pdf:abc", json={"page": 4}).status_code == 200
    r = client.get("/api/progress/pdf:abc").json()
    assert r["page"] == 4 and r["saved"] is True
    assert client.post("/api/progress/pdf:abc", json={"page": -1}).status_code == 422
    assert client.post("/api/progress/pdf:abc", json={"page": "x"}).status_code == 422
    assert client.post("/api/progress/pdf:abc", json={}).status_code == 422
    assert (
        client.post("/api/progress/" + "k" * 301, json={"page": 1}).status_code == 400
    )
    assert client.get("/api/progress/" + "k" * 301).status_code == 400


def test_a_damaged_progress_file_reads_as_empty(client):
    web_app.PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    web_app.PROGRESS_FILE.write_text(json.dumps(["not", "an", "object"]))
    assert client.get("/api/progress/pdf:x").json()["saved"] is False
    web_app.PROGRESS_FILE.write_text(json.dumps({"pdf:x": {"page": "seven"}}))
    assert client.get("/api/progress/pdf:x").json()["saved"] is False
    assert client.post("/api/progress/pdf:x", json={"page": 2}).status_code == 200
    assert client.get("/api/progress/pdf:x").json()["page"] == 2


def test_parallel_progress_writes_keep_every_key(client):
    def save(i: int) -> None:
        client.post(f"/api/progress/pdf:{i}", json={"page": i})

    threads = [threading.Thread(target=save, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    data = json.loads(web_app.PROGRESS_FILE.read_text())
    assert sorted(data) == sorted(f"pdf:{i}" for i in range(20))


def test_an_unreadable_komikku_db_still_lists_pdfs(client, komikku_fixture):
    assert _import(client, _make_pdf_bytes(1)).status_code == 200
    komikku_fixture["db_path"].write_bytes(b"not a sqlite database" * 100)
    r = client.get("/api/library")
    assert r.status_code == 200
    body = r.json()
    assert body["mangas"] == [] and len(body["pdfs"]) == 1
    assert "Komikku" in body["komikku_error"]
    assert client.get("/api/komikku/chapter/10/pages").status_code == 503


def test_a_missing_komikku_db_is_a_404_not_a_crash(client, komikku_fixture):
    komikku_fixture["db_path"].unlink()
    assert client.get("/api/library").json()["mangas"] == []
    assert client.get("/api/komikku/chapter/10/pages").status_code == 404
    assert client.get("/api/komikku/page/10/01.jpg").status_code == 404


def test_odd_page_numbers_are_404(client):
    doc = _import(client, _make_pdf_bytes(1)).json()
    assert client.get(f"/api/pdf/{doc['id']}/page/-1").status_code == 404
    assert client.get(f"/api/pdf/{doc['id']}/page/99999999").status_code == 404
    assert client.get("/api/pdf/..%2F..%2Fetc/page/0").status_code == 404
