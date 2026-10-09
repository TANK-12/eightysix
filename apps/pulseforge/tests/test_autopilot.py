"""Autopilot: recipes, a real render into a package, reruns, Jan fallback, ledger."""

import json
import os
import subprocess
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pulseforge import autopilot, config, formats
from pulseforge import jan as janmod
from pulseforge import project as projmod
from pulseforge import render as rendermod
from pulseforge.recipes import RECIPES
from pulseforge.scenes import registry as scene_registry


def _tone(path, seconds=2.0, sr=22050):
    t = np.arange(int(seconds * sr)) / sr
    y = 0.3 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sin(2 * np.pi * 2 * t))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


@pytest.fixture
def ap(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projmod, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "AUTOPILOT_DIR", tmp_path / "autopilot")
    # never reach the real Jan from a test: it is shared with other sessions
    monkeypatch.setattr(
        janmod,
        "write_upload_text",
        lambda *a, **k: (_ for _ in ()).throw(janmod.JanUnavailable("test")),
    )
    (tmp_path / "projects").mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _tone(inbox / "01 - lazy_sunday.wav")
    return tmp_path, inbox


def _real_render(p, scene, params, fmt, out, log, progress, should_stop):
    return rendermod.render(
        p,
        scene,
        params,
        fmt,
        out,
        config.load_settings(),
        log=lambda m: None,
        progress=progress,
        should_stop=should_stop,
    )


def _fake_render(p, scene, params, fmt, out, log, progress, should_stop):
    ff = config.ffmpeg_caps()["ffmpeg"]
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "color=c=navy:s=320x180:d=2", out],
        capture_output=True,
        check=True,
    )
    return {"duration": 2.0}


def test_recipes_reference_real_scenes_and_formats():
    scenes = {s["id"] for s in scene_registry.scenes_as_list()}
    assert len(RECIPES) >= 3
    for r in RECIPES.values():
        assert r["scene"] in scenes, r["id"]
        assert r["format"] in formats.FORMATS, r["id"]
        assert r["label"] and r["description"]


def test_length_words_and_subtitle():
    assert autopilot.length_words(3600) == "1 hour"
    assert autopilot.length_words(5400) == "1.5 hours"
    assert autopilot.length_words(180) == "3 minutes"
    assert autopilot.length_words(50) == "1 minute"
    r = {"thumb_subtitle": "lofi radio · {length}"}
    assert autopilot.subtitle(r, 7200) == "lofi radio · 2 hours"


def test_song_title_cleans_filenames():
    assert autopilot.song_title("03 - lazy_sunday-FINAL.mp3") == "Lazy Sunday"
    assert autopilot.song_title("Night Drive.flac") == "Night Drive"


@pytest.mark.slow
def test_real_run_makes_a_full_package_and_rerun_skips(ap, monkeypatch):
    tmp, inbox = ap
    monkeypatch.setattr(
        janmod,
        "write_upload_text",
        lambda *a, **k: (_ for _ in ()).throw(janmod.JanUnavailable("down")),
    )
    todo, skipped = autopilot.plan_run(str(inbox), "lofi_drift")
    assert len(todo) == 1 and skipped == []
    autopilot.queue_songs(todo, "lofi_drift")
    done = autopilot.run(todo, "lofi_drift", _real_render, log=lambda m: None)
    assert len(done) == 1

    d = autopilot.package_dir(done[0])
    for name in ("video.mp4", "thumb.jpg", "upload.txt", "CHECKLIST.txt"):
        assert (d / name).exists(), name
    probe = subprocess.run(
        [
            config.ffmpeg_caps()["ffprobe"],
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(d / "video.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    kinds = {s["codec_type"] for s in json.loads(probe.stdout)["streams"]}
    assert kinds == {"video", "audio"}
    text = (d / "upload.txt").read_text()
    assert "Lazy Sunday" in text and "Tags" in text  # the template fallback ran
    assert "Content ID" in (d / "CHECKLIST.txt").read_text()

    todo2, skipped2 = autopilot.plan_run(str(inbox), "lofi_drift")
    assert todo2 == [] and skipped2 == ["01 - lazy_sunday.wav"]
    # a different recipe is a different package
    assert len(autopilot.plan_run(str(inbox), "visualiser_bars")[0]) == 1


def test_failed_song_is_recorded_and_retried(ap):
    _tmp, inbox = ap

    def broken(*a, **k):
        raise RuntimeError("ffmpeg fell over")

    todo, _ = autopilot.plan_run(str(inbox), "lofi_drift")
    autopilot.queue_songs(todo, "lofi_drift")
    assert autopilot.run(todo, "lofi_drift", broken, log=lambda m: None) == []
    rec = autopilot.packages()[todo[0]["slug"]]
    assert rec["status"] == "failed" and "fell over" in rec["error"]
    assert len(autopilot.plan_run(str(inbox), "lofi_drift")[0]) == 1


def test_art_folder_rotates_images(ap, tmp_path):
    _tmp, inbox = ap
    _tone(inbox / "02 - second.wav")
    art = tmp_path / "art"
    art.mkdir()
    for n in ("a.png", "b.png"):
        (art / n).write_bytes(b"x")
    todo, _ = autopilot.plan_run(str(inbox), "lofi_drift", str(art))
    assert [os.path.basename(t["images"][0]) for t in todo] == ["a.png", "b.png"]


def test_ledger_totals_and_month_replacement(ap):
    _tmp, inbox = ap
    _tone(inbox / "02 - second.wav")
    todo, _ = autopilot.plan_run(str(inbox), "lofi_drift")
    autopilot.queue_songs(todo, "lofi_drift")
    autopilot.run(todo, "lofi_drift", _fake_render, log=lambda m: None)
    a, b = (t["slug"] for t in todo)
    autopilot.mark_uploaded(a, "https://youtu.be/x")
    autopilot.record_figures(a, "2026-09", 1000, 1.5)
    autopilot.record_figures(a, "2026-09", 1200, 2.25)  # replaces, not adds
    autopilot.record_figures(a, "2026-10", 300, 0.5)
    autopilot.record_figures(b, "2026-10", 10, 0.01)
    led = autopilot.ledger()
    assert led["total"] == {"views": 1510, "revenue": 2.76}
    assert led["per_recipe"] == [
        {"recipe": "lofi_drift", "videos": 2, "views": 1510, "revenue": 2.76}
    ]
    assert led["per_video"][0]["slug"] == a and led["per_video"][0]["url"]
    with pytest.raises(ValueError):
        autopilot.record_figures(a, "2026-13", 1, 1)
    with pytest.raises(ValueError):
        autopilot.record_figures(a, "2026-09", -1, 1)


def test_routes(ap, monkeypatch):
    _tmp, inbox = ap
    import web_app

    monkeypatch.setattr(web_app, "_autopilot_render", _fake_render)
    c = TestClient(web_app.app)
    ids = {r["id"] for r in c.get("/api/autopilot/recipes").json()["recipes"]}
    assert "lofi_drift" in ids
    assert (
        c.post(
            "/api/autopilot/run", json={"inbox": "/nope", "recipe": "lofi_drift"}
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/api/autopilot/run", json={"inbox": str(inbox), "recipe": "nope"}
        ).status_code
        == 400
    )
    empty = inbox.parent / "empty"
    empty.mkdir()
    assert (
        c.post(
            "/api/autopilot/run", json={"inbox": str(empty), "recipe": "lofi_drift"}
        ).status_code
        == 409
    )

    r = c.post(
        "/api/autopilot/run", json={"inbox": str(inbox), "recipe": "lofi_drift"}
    ).json()
    assert r["job_id"] and len(r["queued"]) == 1
    job = web_app.state.jobs[r["job_id"]]
    for _ in range(600):
        if job.status in ("done", "error"):
            break
        import time

        time.sleep(0.05)
    assert job.status == "done", job.error
    pk = c.get("/api/autopilot/packages").json()["packages"]
    assert pk[0]["status"] == "ready" and pk[0]["video"]
    assert c.get(pk[0]["thumb"]).status_code == 200

    slug = pk[0]["slug"]
    led = c.post(
        "/api/autopilot/ledger",
        json={
            "slug": slug,
            "action": "figures",
            "month": "2026-09",
            "views": 5,
            "revenue": 0.1,
        },
    ).json()
    assert led["total"]["views"] == 5
    assert (
        c.post(
            "/api/autopilot/ledger",
            json={"slug": "ghost", "action": "uploaded", "url": ""},
        ).status_code
        == 404
    )
    assert (
        c.post(
            "/api/autopilot/ledger", json={"slug": slug, "action": "wat"}
        ).status_code
        == 400
    )


def test_folder_recipe_makes_one_mix_and_needs_pictures(ap, tmp_path):
    _tmp, inbox = ap
    _tone(inbox / "02 - second.wav")
    with pytest.raises(ValueError, match="pictures"):
        autopilot.plan_run(str(inbox), "lofi_radio")
    art = tmp_path / "art"
    art.mkdir()
    (art / "a.png").write_bytes(b"x")
    todo, _ = autopilot.plan_run(str(inbox), "lofi_radio", str(art))
    assert len(todo) == 1 and len(todo[0]["songs"]) == 2
    autopilot.queue_songs(todo, "lofi_radio")
    again, skipped = autopilot.plan_run(str(inbox), "lofi_radio", str(art))
    assert again == [] and skipped == ["2 songs"]
    _tone(inbox / "03 - third.wav")  # a new song means a new mix
    assert len(autopilot.plan_run(str(inbox), "lofi_radio", str(art))[0]) == 1


@pytest.mark.slow
def test_real_lofi_radio_mix(ap, tmp_path, monkeypatch):
    """The whole living-still path: shots, preset, grade, rain, target length,
    chapters. Shortened to 12 s so it runs in a test."""
    _tmp, inbox = ap
    _tone(inbox / "02 - second.wav")
    art = tmp_path / "art"
    art.mkdir()
    img = np.zeros((360, 640, 3), np.uint8)
    img[:180] = (90, 120, 200)  # sky over water
    img[180:] = (40, 60, 90)
    from PIL import Image

    Image.fromarray(img).save(art / "scene.png")
    import web_app
    from pulseforge import recipes

    monkeypatch.setitem(recipes.RECIPES["lofi_radio"], "minutes", 0.2)
    monkeypatch.setattr(
        janmod,
        "write_upload_text",
        lambda *a, **k: (_ for _ in ()).throw(janmod.JanUnavailable("down")),
    )
    todo, _ = autopilot.plan_run(str(inbox), "lofi_radio", str(art))
    autopilot.queue_songs(todo, "lofi_radio")
    done = autopilot.run(
        todo,
        "lofi_radio",
        _real_render,
        log=lambda m: None,
        prepare_fn=web_app._autopilot_prepare,
        chapters_fn=web_app._autopilot_chapters,
    )
    assert done, autopilot.packages()
    p = projmod.Project(todo[0]["slug"])
    assert not p.data.get("target_seconds")  # one pass, then a copied repeat
    assert len(p.data["shots"]) == 2  # a shot per song
    assert p.data["ambience"]["bed"] == "rain"
    assert all(s["hold"] == "song" for s in p.data["shots"])
    assert p.data["shots"][0]["look"]["grade"] == "faded"
    d = autopilot.package_dir(done[0])
    probe = subprocess.run(
        [
            config.ffmpeg_caps()["ffprobe"],
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(d / "video.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(probe.stdout) == pytest.approx(12.0, abs=1.0)
    text = (d / "upload.txt").read_text()
    assert "0:00 Lazy Sunday" in text  # chapters, with cleaned titles
    # "inbox" is generic, so the recipe names it, and the tagline fills the rest
    assert "Lofi Radio | 12 seconds" not in text
    assert text.splitlines()[1].startswith("Lofi Radio | ")
    assert "lofi beats to study and relax to" in text


def _picture(path):
    from PIL import Image

    img = np.zeros((360, 640, 3), np.uint8)
    img[:180] = (90, 120, 200)
    img[180:] = (40, 60, 90)
    Image.fromarray(img).save(path)


def test_browse_lists_folders_and_stays_in_home(ap, monkeypatch):
    tmp, inbox = ap
    monkeypatch.setenv("HOME", str(tmp))
    got = autopilot.browse(str(tmp))
    names = {d["name"]: d for d in got["dirs"]}
    assert names["inbox"]["songs"] == 1 and got["parent"] is None
    assert autopilot.browse(str(inbox))["parent"] == str(tmp)
    with pytest.raises(ValueError):
        autopilot.browse("/etc")


def test_scan_says_what_make_would_do(ap, tmp_path):
    _tmp, inbox = ap
    _tone(inbox / "02 - second.wav")
    got = autopilot.scan(str(inbox), "", "lofi_drift")
    assert got["songs"] == 2 and got["to_make"] == 2 and got["problem"] is None
    assert got["minutes"] == pytest.approx(0.1, abs=0.05)
    radio = autopilot.scan(str(inbox), "", "lofi_radio")
    assert radio["to_make"] == 0 and "pictures" in radio["problem"]
    assert autopilot.scan("", "", "lofi_drift")["problem"]
    art = tmp_path / "art"
    art.mkdir()
    _picture(art / "b.png")
    _picture(art / "a.png")
    assert autopilot.scan(str(inbox), str(art), "lofi_radio")["first_picture"].endswith(
        "a.png"
    )


def test_previews_for_every_recipe_are_real_and_cached(ap, tmp_path):
    import web_app

    art = tmp_path / "art"
    art.mkdir()
    _picture(art / "scene.png")
    c = TestClient(web_app.app)
    for rid in RECIPES:
        r = c.get(
            "/api/autopilot/preview",
            params={"recipe": rid, "image": str(art / "scene.png"), "w": 320},
        )
        assert r.status_code == 200, (rid, r.text)
        assert r.content[:4] == b"\x89PNG"
    assert len(list((autopilot.root() / "previews").iterdir())) == len(RECIPES)
    assert (
        c.get("/api/autopilot/preview", params={"recipe": "lofi_radio"}).status_code
        == 409
    )
    assert (
        c.get("/api/autopilot/preview", params={"recipe": "lofi_drift"}).status_code
        == 200
    )
    assert web_app.PREVIEW_SLUG not in {
        p["slug"] for p in c.get("/api/projects").json()
    }


def test_package_text_round_trips(ap):
    _tmp, inbox = ap
    todo, _ = autopilot.plan_run(str(inbox), "lofi_drift")
    autopilot.queue_songs(todo, "lofi_drift")
    autopilot.run(todo, "lofi_drift", _fake_render, log=lambda m: None)
    slug = todo[0]["slug"]
    stored = autopilot.upload_text_of(slug)
    assert stored["title"].startswith("Lazy Sunday") and stored["tags"]
    # an older package without stored text reads upload.txt instead
    pk = autopilot.packages()
    pk[slug].pop("text")
    autopilot._save("packages.json", pk)
    assert autopilot.upload_text_of(slug) == stored
