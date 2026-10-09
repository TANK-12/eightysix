"""preview_voice on the voice job: Emerson-2026-09-17's request for a rough
voiced-movie preview before every character has a real voice picked.
Kokoro synthesis is monkeypatched here (it's exercised for real in
test_audio_emotion.py's sibling manual check and via kokoro_engine directly)
so this test runs fast and without the model file.
"""

import numpy as np
from fastapi.testclient import TestClient

from panelforge import paths, store
from panelforge.audio import kokoro_engine


def _fake_synthesize(text, voice, speed=1.0):
    sr = 8000
    n = int(sr * 0.3)
    return np.sin(2 * np.pi * 220 * np.arange(n) / sr).astype(np.float32), sr


def test_preview_voice_fills_gap_but_never_touches_cast(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    monkeypatch.setattr(kokoro_engine, "synthesize", _fake_synthesize)

    import importlib

    from panelforge import jobs as jobs_mod

    importlib.reload(paths)
    importlib.reload(jobs_mod)
    paths.ensure_roots()

    import web_app

    importlib.reload(web_app)
    client = TestClient(web_app.app)

    series, chapter = "demo", "0001"
    cdir = paths.chapter_dir(series, chapter)
    script = {
        "schema": 1,
        "lines": [
            {
                "id": "l0001",
                "bubble_id": "b1",
                "speaker": "c99",
                "text": "Hello there.",
                "kind": "speech",
                "emotion": {"speed": 1.0, "gain_db": 0},
                "audio": None,
                "dur": None,
            }
        ],
        "sfx": [],
        "music": [],
    }
    store.write(cdir / "script.json", script)

    r = client.post(
        f"/api/chapters/{series}/{chapter}/voice", json={"preview_voice": "am_michael"}
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    job = jobs_mod.get(job_id)
    assert job is not None
    jobs_mod.wait(job, timeout=5)

    assert job.state == "done"
    assert job.result["synthesised"] == 1
    assert job.result["previewed"] == 1
    assert job.result["skipped"] == []

    updated = store.read(cdir / "script.json")
    line = updated["lines"][0]
    assert line["audio"] == "audio/l0001.wav"
    assert line["dur"] is not None
    assert (
        "voice_override" not in line
    )  # preview is transient, not persisted as an override

    assert not (paths.series_dir(series) / "cast.json").exists()  # never written


def test_no_preview_voice_still_skips_with_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    monkeypatch.setattr(kokoro_engine, "synthesize", _fake_synthesize)

    import importlib

    from panelforge import jobs as jobs_mod

    importlib.reload(paths)
    importlib.reload(jobs_mod)
    paths.ensure_roots()

    import web_app

    importlib.reload(web_app)
    client = TestClient(web_app.app)

    series, chapter = "demo2", "0001"
    cdir = paths.chapter_dir(series, chapter)
    script = {
        "schema": 1,
        "lines": [
            {
                "id": "l0001",
                "bubble_id": "b1",
                "speaker": "c99",
                "text": "Hello.",
                "kind": "speech",
                "emotion": {},
                "audio": None,
                "dur": None,
            }
        ],
        "sfx": [],
        "music": [],
    }
    store.write(cdir / "script.json", script)

    r = client.post(f"/api/chapters/{series}/{chapter}/voice", json={})
    job = jobs_mod.get(r.json()["job_id"])
    assert job is not None
    jobs_mod.wait(job, timeout=5)

    assert job.result["synthesised"] == 0
    assert job.result["previewed"] == 0
    assert len(job.result["skipped"]) == 1
    assert job.result["skipped"][0]["reason"] == "no voice set"


def test_only_missing_leaves_spoken_lines_alone(tmp_path, monkeypatch):
    """After a replay moves some lines to other speakers (their sound is
    cleared), the voice job can speak just those and leave the rest."""
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    monkeypatch.setattr(kokoro_engine, "synthesize", _fake_synthesize)

    import importlib

    from panelforge import jobs as jobs_mod

    importlib.reload(paths)
    importlib.reload(jobs_mod)
    paths.ensure_roots()

    import web_app

    importlib.reload(web_app)
    client = TestClient(web_app.app)

    series, chapter = "demo", "0001"
    cdir = paths.chapter_dir(series, chapter)
    (cdir / "audio").mkdir(parents=True, exist_ok=True)
    (cdir / "audio" / "l0001.wav").write_bytes(b"old")
    line = lambda i, audio: {  # noqa: E731
        "id": f"l{i:04d}",
        "bubble_id": f"b{i}",
        "speaker": "c99",
        "text": "Hello there.",
        "kind": "speech",
        "emotion": {"speed": 1.0, "gain_db": 0},
        "audio": audio,
        "dur": 1.0 if audio else None,
    }
    store.write(
        cdir / "script.json",
        {
            "schema": 1,
            "lines": [line(1, "audio/l0001.wav"), line(2, None)],
            "sfx": [],
            "music": [],
        },
    )
    r = client.post(
        f"/api/chapters/{series}/{chapter}/voice",
        json={"preview_voice": "am_michael", "only_missing": True},
    )
    job = jobs_mod.get(r.json()["job_id"])
    jobs_mod.wait(job, timeout=5)
    assert job.state == "done", job.error
    assert job.result["synthesised"] == 1
    assert (cdir / "audio" / "l0001.wav").read_bytes() == b"old"
    assert (cdir / "audio" / "l0002.wav").exists()
