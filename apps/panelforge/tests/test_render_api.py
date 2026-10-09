"""Render API through the FastAPI app on a temporary data root: registries,
timeline get/put/auto, style and panel previews, per-shot and full renders."""

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from panelforge import paths, store
from panelforge.render.fixture import add_scene_layers, make_chapter

SERIES, CHAPTER = "test-series", "0001"
TINY = {"height": 90, "fps": 8}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs as jobs_mod

    importlib.reload(paths)
    importlib.reload(jobs_mod)
    paths.ensure_roots()
    assert paths.DATA_ROOT == tmp_path  # never the real ~/PanelForgeData
    add_scene_layers(make_chapter(tmp_path, n_panels=2))
    import web_app

    importlib.reload(web_app)
    return TestClient(web_app.app)


def _wait(client, job_id, timeout=120):
    from panelforge import jobs

    job = jobs.get(job_id)
    assert job is not None
    jobs.wait(job, timeout)
    doc = client.get(f"/api/jobs/{job_id}").json()
    assert doc["state"] == "done", doc.get("error") or doc.get("log")
    return doc["result"]


def _short(client):
    """Shrink the fixture timeline so renders in tests stay under a second each."""
    tl = client.get(f"/api/chapters/{SERIES}/{CHAPTER}/timeline").json()
    for s in tl["shots"]:
        s["dur"] = 0.5
        s["transition_in"] = {"kind": "cut", "dur": 0.0}
    tl["settings"].update(TINY)
    r = client.put(f"/api/chapters/{SERIES}/{CHAPTER}/timeline", json=tl)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_lists_render_module(client):
    h = client.get("/api/health").json()
    assert "panelforge.api.render" in h["modules"]
    assert "panelforge.api.render" not in h["failed"]


def test_registries(client):
    st = client.get("/api/styles").json()
    names = {s["name"]: s for s in st["styles"]}
    assert (
        names["depth3d"]["enabled"]
        and "parallax_strength" in names["depth3d"]["settings"]
    )
    assert st["default"] == "motion"
    tr = client.get("/api/transitions").json()
    assert {t["kind"] for t in tr["transitions"]} >= {
        "cut",
        "fade",
        "slide",
        "whip",
        "zoom-through",
        "match",
    }


def test_timeline_auto_get_put(client):
    base = f"/api/chapters/{SERIES}/{CHAPTER}/timeline"
    assert client.get(base).status_code == 404
    assert client.get("/api/chapters/nope/0001/timeline").status_code == 404
    res = _wait(
        client,
        client.post(base + "/auto", json={"settings": {"style": "depth3d"}}).json()[
            "job_id"
        ],
    )
    assert res["shots"] == 2
    tl = client.get(base).json()
    assert tl["settings"]["style"] == "depth3d" and len(tl["shots"]) == 2
    tl["shots"][0]["dur"] = 4.0
    put = client.put(base, json=tl).json()
    assert put["shots"][0]["edited"] is True and put["shots"][0]["dur"] == 4.0
    assert (
        store.read(paths.chapter_dir(SERIES, CHAPTER) / "timeline.json")["shots"][0][
            "edited"
        ]
        is True
    )
    bad = client.put(base, json={**tl, "settings": {**tl["settings"], "aspect": "4:3"}})
    assert bad.status_code == 400 and "aspect" in bad.json()["detail"]
    assert (
        client.post(base + "/auto", json={"settings": {"style": "nope"}}).status_code
        == 400
    )
    # a second auto keeps the edited shot
    _wait(client, client.post(base + "/auto").json()["job_id"])
    assert client.get(base).json()["shots"][0]["dur"] == 4.0


def test_style_and_panel_previews(client):
    base = f"/api/chapters/{SERIES}/{CHAPTER}"
    _wait(client, client.post(base + "/timeline/auto").json()["job_id"])
    _short(client)
    r = client.post(
        base + "/preview", json={"kind": "styles", "panels": ["p0001"], **TINY}
    )
    res = _wait(client, r.json()["job_id"])
    assert set(res["videos"]) == {
        "scroll",
        "slideshow",
        "motion",
        "depth3d",
        "puppet25d",
        "inbetween",
    }
    for url in res["videos"].values():
        assert url.startswith(f"/data/series/{SERIES}/chapters/{CHAPTER}/previews/")
        assert (paths.DATA_ROOT / url[len("/data/") :]).stat().st_size > 0
    assert res["grid"] and (paths.DATA_ROOT / res["grid"][len("/data/") :]).exists()
    assert client.get(res["grid"]).status_code == 200  # served by the app
    r = client.post(
        base + "/preview",
        json={"kind": "panel", "panel_id": "p0002", "style": "depth3d", **TINY},
    )
    res = _wait(client, r.json()["job_id"])
    assert (
        res["video"].endswith("panel-p0002-depth3d.mp4") and res["probe"]["frames"] == 4
    )
    assert client.post(base + "/preview", json={"kind": "styles"}).status_code == 400
    assert (
        client.post(
            base + "/preview", json={"kind": "panel", "panel_id": "p1", "style": "x"}
        ).status_code
        == 400
    )
    assert client.post(base + "/preview", json={"kind": "other"}).status_code == 400


def test_shot_and_full_render_and_listing(client):
    base = f"/api/chapters/{SERIES}/{CHAPTER}"
    _wait(client, client.post(base + "/timeline/auto").json()["job_id"])
    tl = _short(client)
    sid = tl["shots"][1]["id"]
    assert client.post(base + "/shots/nope/render").status_code == 404
    res = _wait(
        client,
        client.post(
            base + f"/shots/{sid}/render", json={"style": "depth3d", **TINY}
        ).json()["job_id"],
    )
    assert (
        res["video"].endswith(f"previews/shot-{sid}.mp4")
        and res["probe"]["frames"] == 4
    )
    assert client.get("/api/renders").json()["renders"] == []
    r = client.post(
        base + "/render",
        json={
            "aspect": "9:16",
            "bubbles": "erase",
            "style": "depth3d",
            "out_name": "My Cut!",
            **TINY,
        },
    )
    res = _wait(client, r.json()["job_id"])
    assert res["file"].endswith("renders/my-cut.mp4") and res["url"].endswith(
        "renders/my-cut.mp4"
    )
    assert (res["probe"]["width"], res["probe"]["height"]) == (90, 160)
    assert res["probe"]["frames"] == 8 and res["settings"]["bubbles"] == "erase"
    # a second render with the same name never overwrites the first
    r2 = client.post(
        base + "/render",
        json={"aspect": "9:16", "style": "depth3d", "out_name": "My Cut!", **TINY},
    )
    res2 = _wait(client, r2.json()["job_id"])
    assert res2["file"].endswith("renders/my-cut-2.mp4"), res2["file"]
    assert Path(res["file"]).exists() and Path(res2["file"]).exists()
    Path(res2["file"]).unlink()
    listing = client.get("/api/renders").json()["renders"]
    assert listing[0]["style"] == "depth3d" and listing[0]["aspect"] == "9:16"
    assert listing[0]["sound"] == "full"  # from the sidecar beside the film
    assert [x["name"] for x in listing] == ["my-cut.mp4"] and listing[0][
        "series"
    ] == SERIES
    assert client.post(base + "/render", json={"aspect": "4:3"}).status_code == 400
    assert client.post(base + "/render", json={"bubbles": "hide"}).status_code == 400


def test_limit_shots_picks_ids_or_the_first_seconds():
    from panelforge.api.render import _limit_shots

    tl = {
        "shots": [
            {"id": "t1", "dur": 4.0},
            {"id": "t2", "dur": 3.0},
            {"id": "t3", "dur": 2.0},
        ]
    }
    assert _limit_shots(tl, None, None) is None  # whole chapter
    assert _limit_shots(tl, None, 100.0) is None
    assert _limit_shots(tl, None, 5.0) == ["t1", "t2"]
    assert _limit_shots(tl, None, 0.1) == ["t1"]  # always at least one shot
    assert _limit_shots(tl, ["t3", "t1"], None) == ["t1", "t3"]  # timeline order
    assert _limit_shots(tl, ["t3", "t1"], 1.0) == ["t1"]
    with pytest.raises(ValueError):
        _limit_shots(tl, ["nope"], None)


def test_partial_render_leaves_the_saved_timeline_alone(client):
    base = f"/api/chapters/{SERIES}/{CHAPTER}"
    _wait(client, client.post(base + "/timeline/auto").json()["job_id"])
    tl = _short(client)  # 2 shots, 0.5 s each, 8 fps
    assert client.post(base + "/render", json={"shot_ids": ["nope"]}).status_code == 404
    res = _wait(
        client,
        client.post(
            base + "/render", json={"max_seconds": 0.2, "out_name": "lookie", **TINY}
        ).json()["job_id"],
    )
    assert res["probe"]["frames"] == 4  # one shot only
    assert len(client.get(base + "/timeline").json()["shots"]) == 2
    res2 = _wait(
        client,
        client.post(
            base + "/render",
            json={"shot_ids": [tl["shots"][1]["id"]], "out_name": "one-shot", **TINY},
        ).json()["job_id"],
    )
    assert res2["probe"]["frames"] == 4
    assert res2["file"].endswith("renders/one-shot.mp4")


def test_render_settings_from_the_form_reach_the_film(client):
    """Mode, pace, motion strength and backdrop are settings, not decoration:
    what the render tab sends has to end up in the render's settings."""
    base = f"/api/chapters/{SERIES}/{CHAPTER}"
    _wait(client, client.post(base + "/timeline/auto").json()["job_id"])
    _short(client)
    body = {
        "mode": "page-reveal",
        "pace": 1.4,
        "motion_strength": 0.3,
        "backdrop": "stretch",
        "transition": "cut",
        "effects": 0.5,
        "max_seconds": 0.2,
        "out_name": "settings-check",
        **TINY,
    }
    res = _wait(client, client.post(base + "/render", json=body).json()["job_id"])
    st = res["settings"]
    assert st["mode"] == "page-reveal" and st["pace"] == 1.4
    assert st["motion_strength"] == 0.3 and st["backdrop"] == "stretch"
    assert st["transition"] == "cut" and st["effects"] == 0.5
    # a style's own knobs ride along too, merged over the timeline's, style by style
    body.update(style_settings={"scroll": {"highlight": False}}, out_name="knobs-check")
    res = _wait(client, client.post(base + "/render", json=body).json()["job_id"])
    assert res["settings"]["style_settings"]["scroll"] == {"highlight": False}
    assert client.post(base + "/render", json={"mode": "sideways"}).status_code == 400
    assert (
        client.post(base + "/render", json={"backdrop": "rainbow"}).status_code == 400
    )


def test_an_explicit_style_is_not_turned_into_the_scroll_reader(client):
    """Scroll mode gives every shot the scroll style; an explicitly asked-for
    other style has to win (Cinematic 3D and 2.5D 'vanished' that way), while
    a scroll render with no style (the Cast tab's button) stays scroll."""
    base = f"/api/chapters/{SERIES}/{CHAPTER}"
    _wait(client, client.post(base + "/timeline/auto").json()["job_id"])
    tl = _short(client)
    tl["settings"]["mode"] = "scroll"  # the app's default mode since 2026-09-19
    assert client.put(base + "/timeline", json=tl).status_code == 200
    common = {"max_seconds": 0.2, **TINY}
    res = _wait(
        client,
        client.post(
            base + "/render", json={"style": "motion", "out_name": "st", **common}
        ).json()["job_id"],
    )
    assert res["settings"]["mode"] == "panel-to-panel"
    assert res["settings"]["style"] == "motion"
    body = {"style": "motion", "mode": "scroll", "out_name": "st2", **common}
    res = _wait(client, client.post(base + "/render", json=body).json()["job_id"])
    assert res["settings"]["style"] == "motion"
    res = _wait(
        client,
        client.post(
            base + "/render", json={"mode": "scroll", "out_name": "sc", **common}
        ).json()["job_id"],
    )
    assert res["settings"]["mode"] == "scroll"
    assert res["settings"]["style"] == "scroll"
