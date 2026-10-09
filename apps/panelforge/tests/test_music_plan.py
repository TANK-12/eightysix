"""Music changes per stretch of mood, not per panel (see music/plan.py)."""

from panelforge.music import plan


def _panels(spec):
    """ "calm calm tense" per scene -> [(pid, mood, scene)] in reading order."""
    out = []
    n = 0
    for s, moods in enumerate(spec):
        for m in moods.split():
            n += 1
            out.append((f"p{n:04d}", m, f"s{s:02d}"))
    return out


def test_flipping_panel_moods_become_one_segment_per_scene():
    panels = _panels(["calm tense calm tense calm", "tense tense calm tense tense"])
    segs = plan.segments(panels)
    assert [s["mood"] for s in segs] == ["calm", "tense"]
    assert segs[0]["from_panel"] == "p0001" and segs[0]["to_panel"] == "p0005"
    assert segs[1]["from_panel"] == "p0006" and segs[1]["to_panel"] == "p0010"


def test_a_tie_in_a_scene_goes_to_the_stronger_mood():
    segs = plan.segments(_panels(["calm tense calm tense"]))
    assert [s["mood"] for s in segs] == ["tense"]


def test_a_short_scene_joins_the_one_before_and_agreeing_neighbours_join():
    panels = _panels(["calm calm calm calm", "sad", "calm calm calm calm calm"])
    segs = plan.segments(panels)
    assert len(segs) == 1 and segs[0]["mood"] == "calm" and segs[0]["panels"] == 10


def test_a_short_first_scene_joins_the_next():
    panels = _panels(["sad", "tense tense tense tense tense"])
    segs = plan.segments(panels)
    assert len(segs) == 1 and segs[0]["mood"] == "tense"
    assert segs[0]["from_panel"] == "p0001"


def test_panels_without_scenes_are_smoothed_too():
    panels = [
        (f"p{n}", m, None)
        for n, m in enumerate(
            "calm tense calm calm calm calm tense tense tense tense tense".split()
        )
    ]
    segs = plan.segments(panels)
    assert [s["mood"] for s in segs] == ["calm", "tense"], segs


def test_the_real_chapter_shape_gives_a_handful_of_segments():
    import random

    rng = random.Random(3)
    panels = []
    for s in range(21):
        for _ in range(rng.randint(2, 9)):
            panels.append(
                (
                    f"p{len(panels):04d}",
                    rng.choice(["calm", "calm", "tense", "tense", "mystery", "sad"]),
                    f"s{s:02d}",
                )
            )
    segs = plan.segments(panels)
    assert 1 <= len(segs) <= 12, len(segs)
    assert sum(s["panels"] for s in segs) == len(panels)


def test_auto_audio_places_scene_music_and_tells_the_saved_film_plan(
    tmp_path, monkeypatch
):
    """The route uses the planner and rewrites the saved timeline's music
    id list, so a film planned before the pass plays the new segments."""
    import importlib

    from fastapi.testclient import TestClient

    from panelforge import jobs as jobs_mod
    from panelforge import paths, store

    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    importlib.reload(paths)
    importlib.reload(jobs_mod)
    paths.ensure_roots()
    import web_app

    importlib.reload(web_app)
    client = TestClient(web_app.app)
    cdir = paths.chapter_dir("demo", "0001")
    cdir.mkdir(parents=True, exist_ok=True)
    store.write(cdir / "chapter.json", {"schema": 1, "id": "0001"})
    store.write(cdir / "bubbles.json", {"schema": 1, "bubbles": []})
    panels = {}
    for n in range(12):
        panels[f"p{n:04d}"] = {
            "scene_id": "s01" if n < 6 else "s02",
            "mood": ["calm", "tense"][n % 2] if n < 6 else "tense",
        }
    store.write(cdir / "scene.json", {"schema": 1, "panels": panels, "speakers": {}})
    store.write(
        cdir / "script.json", {"schema": 1, "lines": [], "sfx": [], "music": []}
    )
    store.write(cdir / "timeline.json", {"schema": 1, "shots": [], "music": ["m07"]})
    r = client.post("/api/chapters/demo/0001/audio/auto")
    job = jobs_mod.get(r.json()["job_id"])
    jobs_mod.wait(job, timeout=5)
    assert job.state == "done", job.error
    music = store.read(cdir / "script.json")["music"]
    assert [m["mood"] for m in music] == [
        "tense"
    ], music  # ties go to tense; s02 tense; joined
    assert store.read(cdir / "timeline.json")["music"] == [m["id"] for m in music]
