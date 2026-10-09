import io


def _make_pdf_bytes(n_pages: int = 2) -> bytes:
    import pymupdf as fitz

    doc = fitz.open()
    for _ in range(n_pages):
        page = doc.new_page()
        page.insert_text((72, 72), "hello inkforge")
    data = doc.tobytes()
    doc.close()
    return data


def test_import_pdf_rasterizes_every_page(client):
    pdf_bytes = _make_pdf_bytes(2)
    r = client.post(
        "/api/pdf/import",
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert r.status_code == 200
    doc = r.json()
    assert doc["title"] == "sample"
    assert doc["pages"] == 2

    r = client.get(f"/api/pdf/{doc['id']}/page/0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"

    r = client.get(f"/api/pdf/{doc['id']}/page/1")
    assert r.status_code == 200

    r = client.get(f"/api/pdf/{doc['id']}/page/2")
    assert r.status_code == 404

    r = client.get("/api/library")
    assert len(r.json()["pdfs"]) == 1


def test_import_rejects_non_pdf(client):
    r = client.post(
        "/api/pdf/import",
        files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert r.status_code == 400
