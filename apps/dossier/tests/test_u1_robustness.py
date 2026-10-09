"""Bad input from the U1 sweep (2026-10-08): a URL slug must never become a path
outside the library, and a wrong-typed number is the caller's mistake (400),
not a server crash (500)."""

import json

import pytest
from fastapi.testclient import TestClient

import dossier
import enrich
import jobqueue
import store
import web_app
from research import seeds


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A one-subject library in a temp folder, used as the data root."""
    root = tmp_path / "DossierData"
    subject = root / "subjects" / "ada-lovelace"
    subject.mkdir(parents=True)
    (subject / "subject.json").write_text(json.dumps({"name": "Ada Lovelace"}))
    (root / "index.json").write_text("[]")
    monkeypatch.setattr(store, "_resolved", store.Root(root, False, "test library"))
    monkeypatch.setattr(jobqueue, "_queue", None)
    return root


@pytest.mark.parametrize("slug", ["%2E%2E", "%2E"])
def test_a_dot_slug_cannot_delete_the_library(library, slug):
    client = TestClient(web_app.app)
    assert client.delete(f"/api/subject/{slug}").status_code == 404
    assert (library / "index.json").is_file()
    assert (library / "subjects" / "ada-lovelace" / "subject.json").is_file()


@pytest.mark.parametrize("slug", ["%2E%2E", "%2E"])
def test_a_dot_slug_reads_as_not_found(library, slug):
    client = TestClient(web_app.app)
    assert client.get(f"/api/subject/{slug}").status_code == 404
    assert (
        client.post(f"/api/subject/{slug}/notes", json={"markdown": "x"}).status_code
        == 404
    )
    assert not (library / "notes.json").exists()


def test_delete_only_takes_a_name_slugify_could_have_made(library):
    assert dossier.delete("..") is False
    assert dossier.delete("Ada-Lovelace") is False
    assert (library / "subjects" / "ada-lovelace").is_dir()


def test_a_held_subject_still_opens_and_deletes(library):
    client = TestClient(web_app.app)
    assert client.get("/api/subject/ada-lovelace").status_code == 200
    assert client.delete("/api/subject/ada-lovelace").status_code == 200
    assert not (library / "subjects" / "ada-lovelace").exists()
    assert (library / "subjects").is_dir()


@pytest.mark.parametrize(
    "path, body",
    [
        ("/api/queue/deepen", {"limit": "abc", "start": False}),
        ("/api/queue/recipe", {"recipe": next(iter(seeds.RECIPES)), "limit": "abc"}),
        ("/api/briefing/rebuild", {"days": "abc", "summary": False}),
        ("/api/briefing/rebuild", {"days": [1], "summary": False}),
        ("/api/watch", {"every_hours": "abc"}),
        ("/api/watch", {"per_sweep": None}),
        ("/api/history", {"limit": "lots"}),
    ],
)
def test_a_wrong_typed_number_is_a_400_not_a_crash(library, monkeypatch, path, body):
    started = []
    monkeypatch.setattr(enrich, "start", lambda **kw: started.append(kw) or True)
    response = TestClient(web_app.app, raise_server_exceptions=False).post(
        path, json=body
    )
    assert response.status_code == 400, response.text
    assert "number" in response.json()["detail"]
    assert started == []


def test_a_negative_briefing_window_is_clamped_not_used(library, monkeypatch):
    seen = []

    def build(days, write_summary):
        seen.append((days, write_summary))
        return {"days": days}

    monkeypatch.setattr(web_app.briefing_mod, "build", build)
    monkeypatch.setattr(web_app.briefing_mod, "save", lambda built, kind: None)
    response = TestClient(web_app.app).post(
        "/api/briefing/rebuild", json={"days": -5, "summary": False}
    )
    assert response.status_code == 200
    assert seen == [(1, False)]


def test_an_overlong_slug_is_not_found_and_slugify_stays_within_it(library):
    long = "x" * (store.MAX_SLUG + 1)
    with pytest.raises(store.BadSlug):
        store.subject_dir(long)
    assert TestClient(web_app.app).get(f"/api/subject/{long}").status_code == 404
    slug = store.slugify("Ada " * 100)
    assert len(slug) <= store.MAX_SLUG and store.slugify(slug) == slug
    assert not slug.endswith("-")
