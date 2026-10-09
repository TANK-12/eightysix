"""Scene pipeline on a synthetic chapter with the AI models switched off
(PANELFORGE_SCENE_MODELS=off): scene.json and cast.json shapes, caching,
cast edits through the API, and the understanding rules."""

import importlib

import pytest


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    monkeypatch.setenv("PANELFORGE_SCENE_MODELS", "off")
    from panelforge import jobs, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    paths.ensure_roots()
    return tmp_path


def test_understand_rules_are_monotonic_and_explained():
    from panelforge.scene import understand

    rec = {
        "speed_lines": {"present": True, "strength": 1.0},
        "stats": {"edges": 0.2, "lightness": 0.4},
        "characters": [],
    }
    shout = [{"kind": "shout", "text": "Run!", "style": {"stroke_weight": 1.6}}]
    calm_rec = {
        "speed_lines": None,
        "stats": {"edges": 0.02, "lightness": 0.7},
        "characters": [],
    }
    assert understand.action_level(rec, shout) > understand.action_level(calm_rec, [])
    mood, why = understand.mood(rec, shout, understand.action_level(rec, shout))
    assert mood == "action" and why
    assert understand.mood(calm_rec, [], 0.0)[0] == "calm"
    e = understand.expression({}, shout, "action", 0.8)
    assert e["label"] == "angry" and e["intensity"] > 0.7 and e["why"]
    assert understand.expression({}, [], "calm", 0.0)["label"] == "neutral"
    scared = understand.expression(
        {},
        [{"kind": "whisper", "text": "no...", "style": {"trembling": True}}],
        "sad",
        0.0,
    )
    assert scared["label"] == "scared"
    ac = understand.acoustics(
        {"stats": {"lightness": 0.1}, "characters": [], "background": None},
        [],
        {"kind": "panel"},
    )
    assert ac["space"] == "void"
    comms = understand.acoustics(
        {"stats": {"lightness": 0.5}, "characters": []},
        [{"kind": "speech", "style": {"outline": "rect"}}],
        {"kind": "panel"},
    )
    assert comms["space"] == "comms"


def test_pipeline_and_cast_api(data):
    from fastapi.testclient import TestClient

    from panelforge import jobs, store
    from panelforge.render import fixture
    from panelforge.scene import pipeline
    import web_app

    ch = fixture.make_chapter(data, n_panels=4, scene=False, script=False)
    st = pipeline.run_analyze(ch, None)
    assert st["panels"] == 4 and st["with_depth"] == 4, st
    scene = store.read(ch / "scene.json")
    assert set(scene["panels"]) == {
        p["id"] for p in store.read(ch / "panels.json")["panels"]
    }
    for sp in scene["panels"].values():
        assert sp["mood"] in ("tense", "calm", "action", "sad", "comic", "mystery")
        assert 0.0 <= sp["action"] <= 1.0
        assert sp["acoustics"]["space"] in (
            "small-room",
            "hall",
            "outdoor",
            "vehicle",
            "comms",
            "void",
        )
        assert (ch / sp["depth"]).exists()
        for c in sp["characters"]:
            assert c["expression"]["label"] and (ch / c["cutout"]).exists()
    cast = store.read(ch.parent.parent / "cast.json")
    assert cast["schema"] == 1 and "cast" in cast and "extras" in cast
    assert all(
        c["voice"] is None for c in cast["cast"]
    ), "voices are never auto-assigned"
    n_cache = len(list((ch / "work" / "scene" / "cache").iterdir()))

    # second run reuses the cache and keeps names and voices
    cid = cast["cast"][0]["id"] if cast["cast"] else ""
    if cast["cast"]:
        cast["cast"][0]["name"] = "Luca"
        cast["cast"][0]["voice"] = {
            "kokoro": "am_michael",
            "speed": 1.0,
            "pitch": 0,
            "gain_db": 0,
        }
        store.write(ch.parent.parent / "cast.json", cast)
    pipeline.run_analyze(ch, None)
    assert len(list((ch / "work" / "scene" / "cache").iterdir())) == n_cache
    cast2 = store.read(ch.parent.parent / "cast.json")
    if cast["cast"]:
        me = [c for c in cast2["cast"] if c["id"] == cid][0]
        assert me["name"] == "Luca" and me["voice"]["kokoro"] == "am_michael"

    c = TestClient(web_app.app)
    assert c.get("/api/chapters/test-series/0001/scene").json()["schema"] == 1
    got = c.get("/api/series/test-series/cast").json()
    sc0 = c.get("/api/chapters/test-series/0001/scene").json()
    for sp in sc0["panels"].values():
        for ch_ in sp["characters"]:
            assert ch_["placement"] in ("cast", "extra", "unplaced", "rejected")
            assert (ch_["placement"] in ("cast", "extra")) == bool(
                ch_["cast_id"] or ch_["extra_id"]
            ), ch_
    if got["cast"]:
        r = c.put(
            "/api/series/test-series/cast",
            json={"rename": {got["cast"][0]["id"]: "Mira"}},
        ).json()
        assert r["cast"][0]["name"] == "Mira" and r["cast"][0]["edited"]
    if len(got["cast"]) >= 2:
        a, b = got["cast"][0]["id"], got["cast"][1]["id"]
        r = c.put("/api/series/test-series/cast", json={"merge": [[a, b]]}).json()
        assert b not in {x["id"] for x in r["cast"]}
        sc = c.get("/api/chapters/test-series/0001/scene").json()
        assert all(
            ch_["cast_id"] != b
            for sp in sc["panels"].values()
            for ch_ in sp["characters"]
        )
    assert (
        c.get("/api/series/test-series/assets/backgrounds").json()["kind"]
        == "backgrounds"
    )
    r = c.post("/api/chapters/test-series/0001/analyze").json()
    job = jobs.get(r["job_id"])
    assert job is not None
    job = jobs.wait(job, timeout=300)
    assert job.state == "done", job.error
