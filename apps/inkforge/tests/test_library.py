def test_library_lists_komikku_manga(client):
    r = client.get("/api/library")
    assert r.status_code == 200
    data = r.json()
    assert data["pdfs"] == []
    assert len(data["mangas"]) == 1
    manga = data["mangas"][0]
    assert manga["name"] == "Test Manga"
    assert len(manga["chapters"]) == 1
    assert manga["chapters"][0]["pages"] == 3


def test_chapter_pages_listed_in_order(client):
    r = client.get("/api/library")
    chapter_id = r.json()["mangas"][0]["chapters"][0]["id"]
    r = client.get(f"/api/komikku/chapter/{chapter_id}/pages")
    assert r.status_code == 200
    assert r.json()["pages"] == ["01.jpg", "02.jpg", "03.jpg"]


def test_page_served_and_traversal_blocked(client):
    r = client.get("/api/library")
    chapter_id = r.json()["mangas"][0]["chapters"][0]["id"]

    r = client.get(f"/api/komikku/page/{chapter_id}/01.jpg")
    assert r.status_code == 200
    assert r.content.startswith(b"\xff\xd8\xff")

    r = client.get(f"/api/komikku/page/{chapter_id}/..%2F..%2Fweb_app.py")
    assert r.status_code == 404


def test_progress_roundtrip(client):
    r = client.get("/api/progress/komikku:10")
    assert r.json()["page"] == 0

    r = client.post("/api/progress/komikku:10", json={"page": 2})
    assert r.status_code == 200

    r = client.get("/api/progress/komikku:10")
    assert r.json()["page"] == 2
