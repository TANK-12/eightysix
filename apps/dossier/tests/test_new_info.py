"""The "Get new info" buttons: new information in, old information kept.

No network. Reuses the portal fixture from test_news_archive.
"""

from fastapi.testclient import TestClient

import dossier
import enrich
import web_app
from research import news_archive as archive
from sources.wikipedia import article_from
from test_news_archive import MONTH_HTML, StubFetcher, _held_subject


def _answer(params):
    if params.get("action") == "parse":
        return {"parse": {"text": MONTH_HTML}}
    if params.get("prop") == "redirects":
        return {
            "query": {
                "pages": [
                    {
                        "title": "Volodymyr Zelenskyy",
                        "redirects": [{"title": "Zelensky"}],
                    }
                ]
            }
        }
    if params.get("prop") == "extracts":
        return {
            "query": {
                "pages": [
                    {
                        "title": "Volodymyr Zelenskyy",
                        "extract": "Fresh lead.\n== Presidency ==\nElected in 2019.",
                    }
                ]
            }
        }
    return None


def test_one_subject_gets_new_info_and_keeps_what_it_had(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "months_in_window", lambda *a, **k: ["2022-03"])
    slug = _held_subject(tmp_path)
    other = _held_subject(tmp_path, slug="someone-else", title="Someone Else")
    old_event = {"date": "2019-05-20", "title": "Took office", "kind": "office"}
    dossier.add_events(
        slug,
        [old_event],
        {"phase": "test"},
        article_from("V", "Old.\n== A ==\nB."),
        tmp_path,
    )
    dossier.reindex(tmp_path)

    result = enrich.run(
        fetcher=StubFetcher(_answer),
        root=tmp_path,
        slugs=[slug],
        refresh_articles=True,
    )

    assert result["total"] == 1
    held = dossier.load(slug, tmp_path)
    titles = [e["title"] for e in held["timeline"]]
    assert "Took office" in titles, "an event already held was lost"
    assert sum(1 for e in held["timeline"] if e["kind"] == "news") == 2
    assert held["article"]["sections"][1]["heading"] == "Presidency"
    assert dossier.load(other, tmp_path)["timeline"] == []


def test_without_refresh_a_held_article_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "months_in_window", lambda *a, **k: ["2022-03"])
    slug = _held_subject(tmp_path)
    dossier.add_events(
        slug, [], {"phase": "test"}, article_from("V", "Old.\n== Kept ==\nB."), tmp_path
    )
    dossier.reindex(tmp_path)
    enrich.run(fetcher=StubFetcher(_answer), root=tmp_path)
    assert dossier.load(slug, tmp_path)["article"]["sections"][1]["heading"] == "Kept"


def test_the_button_asks_for_one_subject_with_a_fresh_article(monkeypatch):
    calls = []
    monkeypatch.setattr(dossier, "exists", lambda slug, root=None: True)
    monkeypatch.setattr(enrich, "start", lambda **kw: calls.append(kw) or True)
    monkeypatch.setattr(enrich, "state", lambda root=None: {"running": True})
    response = TestClient(web_app.app).post("/api/subject/x/new-info")
    assert response.status_code == 200
    assert calls == [{"slugs": ["x"], "refresh_articles": True}]


def test_the_button_refuses_while_a_pass_is_running(monkeypatch):
    monkeypatch.setattr(dossier, "exists", lambda slug, root=None: True)
    monkeypatch.setattr(enrich, "start", lambda **kw: False)
    assert TestClient(web_app.app).post("/api/subject/x/new-info").status_code == 409


def test_the_button_404s_for_a_subject_not_held(monkeypatch):
    monkeypatch.setattr(dossier, "exists", lambda slug, root=None: False)
    assert TestClient(web_app.app).post("/api/subject/nope/new-info").status_code == 404
