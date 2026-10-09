"""Delete, reset, rewind, the editable outline and model roles, through the
real FastAPI routes with the data folders pointed at a temp dir."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api(data_dirs, monkeypatch):
    import web_app

    monkeypatch.setattr(web_app.state.catalog, "models", ["small-2B", "big-27B"])
    web_app.state.jobs.clear()
    web_app.state.active_job_id = None
    return TestClient(web_app.app), web_app


def _seed(client, name="My Book"):
    assert client.post("/api/projects", json={"name": name}).status_code == 200
    return name.replace(" ", "_")


def test_outline_edits_are_parsed_back_into_chapters(api):
    client, _ = api
    slug = _seed(client)
    r = client.put(
        f"/api/projects/{slug}/bible",
        json={"outline": "1. Open | a | b | c\n\n2: Second"},
    )
    b = r.json()["bible"]
    assert b["chapter_list"] == ["Open | a | b | c", "Second"]
    assert b["outline"] == "1. Open | a | b | c\n2. Second"


def test_pasted_labels_are_tidied_on_save(api):
    client, _ = api
    slug = _seed(client)
    b = client.put(
        f"/api/projects/{slug}/bible",
        json={
            "pinned_facts": "Pinned facts: No harem.",
            "inspiration_notes": "nspiration notes: Weak to strong.",
            "plot": "Protagonist: Kang. He is left behind.",
        },
    ).json()["bible"]
    assert b["pinned_facts"] == "No harem."
    assert b["inspiration_notes"] == "Weak to strong."
    assert b["plot"] == "Protagonist: Kang. He is left behind."


def test_reset_clears_only_the_chosen_parts(api):
    client, web_app = api
    slug = _seed(client)
    client.put(
        f"/api/projects/{slug}/bible",
        json={"genre": "Hunter", "world_doc": "World", "outline": "1. A | b | c | d"},
    )
    r = client.post(
        f"/api/projects/{slug}/reset", json={"parts": ["outline", "world_doc"]}
    )
    b = r.json()["bible"]
    assert r.json()["reset"] == ["outline", "world_doc"]
    assert b["chapter_list"] == [] and b["world_doc"] == "" and b["genre"] == "Hunter"
    assert (
        client.post(
            f"/api/projects/{slug}/reset", json={"parts": ["everything"]}
        ).status_code
        == 400
    )
    b = client.post(f"/api/projects/{slug}/reset", json={"parts": ["bible"]}).json()[
        "bible"
    ]
    assert b["genre"] == "" and b["title"] == "My Book"


def test_rewind_moves_later_chapters_to_the_trash(api, data_dirs):
    client, web_app = api
    slug = _seed(client)
    from novelforge.project import Project

    p = Project(slug)
    for n in (1, 2, 3):
        p.save_chapter(n, f"chapter {n} text")
        p.state["chapter_summaries"][str(n)] = f"sum {n}"
    p.state["current_chapter"] = 3
    p.state["running_synopsis"] = "all three"
    p.save()
    r = client.post(f"/api/projects/{slug}/rewind", json={"from_chapter": 2}).json()
    assert r["removed"] == 2 and r["chapter_count"] == 1
    assert r["state"]["current_chapter"] == 1
    assert r["state"]["chapter_summaries"] == {"1": "sum 1"}
    assert r["state"]["running_synopsis"] == ""
    trashed = [d for d in os.listdir(data_dirs["trash"]) if "chapters" in d]
    assert len(trashed) == 1
    assert sorted(os.listdir(data_dirs["trash"] / trashed[0])) == [
        "chapter_002.txt",
        "chapter_003.txt",
    ]


def test_codex_entries_delete_one_at_a_time(api):
    client, _ = api
    slug = _seed(client)
    from novelforge.project import Project

    p = Project(slug)
    p.codex["characters"] = {"Kang": {"desc": "x"}, "Yoo": {"desc": "y"}}
    p.codex["facts"] = ["Gates break", "Mana is blue"]
    p.save_codex()
    r = client.delete(
        f"/api/projects/{slug}/codex", params={"bucket": "characters", "key": "Kang"}
    )
    assert list(r.json()["codex"]["characters"]) == ["Yoo"]
    r = client.delete(
        f"/api/projects/{slug}/codex", params={"bucket": "facts", "key": "Mana is blue"}
    )
    assert r.json()["codex"]["facts"] == ["Gates break"]
    assert (
        client.delete(
            f"/api/projects/{slug}/codex", params={"bucket": "facts", "key": "nope"}
        ).status_code
        == 404
    )


def test_delete_project_goes_to_the_trash_and_unlinks_its_series(api, data_dirs):
    client, _ = api
    slug = _seed(client)
    client.post("/api/series", json={"name": "Saga", "planned_books": 2})
    client.post("/api/series/Saga/books", json={"project_name": slug})
    r = client.delete(f"/api/projects/{slug}")
    assert r.status_code == 200 and "project-My_Book" in r.json()["trashed_to"]
    assert slug not in [p["name"] for p in client.get("/api/projects").json()]
    assert client.get("/api/series/Saga").json()["books"] == []
    assert client.delete(f"/api/projects/{slug}").status_code == 404


def test_series_book_removal_and_series_delete(api):
    client, _ = api
    slug = _seed(client)
    client.post("/api/series", json={"name": "Saga"})
    client.post("/api/series/Saga/books", json={"project_name": slug})
    assert client.get(f"/api/projects/{slug}").json()["bible"]["series"] == "Saga"
    r = client.delete(f"/api/series/Saga/books/{slug}")
    assert r.json()["books"] == []
    assert client.get(f"/api/projects/{slug}").json()["bible"]["series"] == ""
    assert client.delete("/api/series/Saga").status_code == 200
    assert client.get("/api/series").json() == []
    assert client.delete("/api/series/Saga").status_code == 404


def test_a_running_job_blocks_destructive_edits_on_its_project(api):
    client, web_app = api
    slug = _seed(client)
    job = web_app.Job("generate", slug)
    web_app.state.jobs[job.id] = job
    web_app.state.active_job_id = job.id
    assert client.delete(f"/api/projects/{slug}").status_code == 409
    assert (
        client.post(
            f"/api/projects/{slug}/reset", json={"parts": ["outline"]}
        ).status_code
        == 409
    )
    job.status = "done"
    assert (
        client.post(
            f"/api/projects/{slug}/reset", json={"parts": ["outline"]}
        ).status_code
        == 200
    )


def test_model_roles_fall_back_writer_then_saved_then_first(api, monkeypatch):
    client, web_app = api
    monkeypatch.setitem(web_app.state.settings, "model", "gone-model")
    assert web_app._resolve_model(None) == "small-2B"  # stale saved model is skipped
    monkeypatch.setitem(web_app.state.settings, "model", "big-27B")
    assert web_app._resolve_model(None) == "big-27B"
    client.post("/api/jan/settings", json={"models": {"writer": "small-2B"}})
    assert web_app._resolve_model(None) == "small-2B"
    assert (
        web_app._resolve_model(None, role="planner") == "small-2B"
    )  # planner follows writer
    client.post("/api/jan/settings", json={"models": {"planner": "big-27B"}})
    assert web_app._resolve_model(None, role="planner") == "big-27B"
    assert web_app._resolve_model("big-27B") == "big-27B"
    st = client.get("/api/state").json()
    assert st["roles"] == {"writer": "small-2B", "planner": "big-27B"}


def test_presets_are_listed_for_the_story_tab(api):
    client, _ = api
    rows = client.get("/api/presets").json()
    ids = [r["id"] for r in rows]
    assert "kr-hunter" in ids and "general" in ids
    assert (
        client.get("/api/presets/kr-hunter").json()["label"].startswith("Korean hunter")
    )
    assert client.get("/api/presets/nope").status_code == 404


def test_a_running_job_blocks_unlinking_its_series(api):
    # Unlinking rewrites the book's bible; the job's own copy would save the
    # old series link back over it.
    client, web_app = api
    slug = _seed(client)
    client.post("/api/series", json={"name": "Saga"})
    client.post("/api/series/Saga/books", json={"project_name": slug})
    job = web_app.Job("generate", slug)
    web_app.state.jobs[job.id] = job
    web_app.state.active_job_id = job.id
    assert client.delete(f"/api/series/Saga/books/{slug}").status_code == 409
    assert client.delete("/api/series/Saga").status_code == 409
    job.status = "done"
    assert client.delete(f"/api/series/Saga/books/{slug}").status_code == 200
    assert client.delete("/api/series/Saga").status_code == 200


def test_a_name_that_is_not_a_folder_name_deletes_nothing(api):
    # "???" slugifies to "untitled"; it must not trash a real "untitled".
    client, _ = api
    _seed(client, "untitled")
    _seed(client, "My_Book")
    for name in ("%3F%3F%3F", "My%20Book", "My%20Book!"):
        assert client.delete(f"/api/projects/{name}").status_code == 404
        assert (
            client.post(f"/api/projects/{name}/rewind", json={"from_chapter": 1})
        ).status_code == 404
    names = [p["name"] for p in client.get("/api/projects").json()]
    assert "untitled" in names and "My_Book" in names


def test_rewind_takes_chapters_past_a_gap_and_never_overwrites_trash(api, data_dirs):
    client, _ = api
    slug = _seed(client)
    from novelforge.project import Project

    p = Project(slug)
    for n in (1, 2, 4):
        p.save_chapter(n, f"chapter {n} text")
    p.save()
    assert (
        client.post(f"/api/projects/{slug}/rewind", json={"from_chapter": 2}).json()[
            "removed"
        ]
        == 2
    )
    assert not os.path.exists(p.chapter_path(4))
    # The same chapter rewound twice within one second keeps both copies.
    p.save_chapter(2, "second take")
    client.post(f"/api/projects/{slug}/rewind", json={"from_chapter": 2})
    trashed = sorted(d for d in os.listdir(data_dirs["trash"]) if "chapters" in d)
    kept = [
        open(data_dirs["trash"] / d / "chapter_002.txt").read().strip()
        for d in trashed
        if (data_dirs["trash"] / d / "chapter_002.txt").exists()
    ]
    assert sorted(kept) == ["chapter 2 text", "second take"]
