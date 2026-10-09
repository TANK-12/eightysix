"""Per-line emotion override endpoint and the rebuild/voice-job paths around
it. Kokoro is monkeypatched (the real model is exercised by hand, see
docs/crew/helper-9.md) so this runs fast and never touches ~/PanelForgeData
(PANELFORGE_DATA points at tmp_path)."""

import importlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from panelforge import paths, store
from panelforge.audio import emotion, kokoro_engine

CALLS: list[dict] = []


def _fake_synthesize(text, voice, speed=1.0, style=None):
    CALLS.append({"text": text, "voice": voice, "speed": speed, "style": style})
    sr = 8000
    n = int(sr * 0.3)
    return np.sin(2 * np.pi * 220 * np.arange(n) / sr).astype(np.float32) * 0.5, sr


BUBBLES = {
    "schema": 1,
    "bubbles": [
        {
            "id": "b1",
            "panel_id": "p1",
            "order": 1,
            "box": [0, 0, 10, 10],
            "kind": "speech",
            "text": "I will NEVER go back!",
            "speaker": "c01",
            "style": {"outline": "jagged", "bold_words": ["NEVER"]},
        },
        {
            "id": "b2",
            "panel_id": "p1",
            "order": 2,
            "box": [0, 0, 10, 10],
            "kind": "speech",
            "text": "Please stay.",
            "speaker": "c01",
            "style": {"outline": "smooth"},
        },
    ],
}
SCENE = {
    "schema": 1,
    "panels": {
        "p1": {
            "mood": "tense",
            "acoustics": {"space": "hall", "size": 0.5},
            "characters": [
                {
                    "cast_id": "c01",
                    "expression": {"label": "angry", "intensity": 0.6, "conf": 0.9},
                }
            ],
        }
    },
    "speakers": {},
}
CAST = {
    "schema": 1,
    "cast": [
        {
            "id": "c01",
            "name": "Kai",
            "voice": {
                "kokoro": "am_michael",
                "speed": 1.0,
                "pitch": 0.0,
                "gain_db": 0.0,
            },
        }
    ],
    "narrator": {"voice": None},
    "extras": [],
    "backgrounds": [],
    "props": [],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    monkeypatch.setattr(kokoro_engine, "synthesize", _fake_synthesize)
    monkeypatch.setattr(kokoro_engine, "style_vector", lambda voice, blend: None)
    CALLS.clear()
    from panelforge import jobs as jobs_mod

    importlib.reload(paths)
    importlib.reload(jobs_mod)
    paths.ensure_roots()
    import web_app

    importlib.reload(web_app)
    c = TestClient(web_app.app)
    cdir = paths.chapter_dir("demo", "0001")
    store.write(cdir / "bubbles.json", BUBBLES)
    store.write(cdir / "scene.json", SCENE)
    store.write(paths.series_dir("demo") / "cast.json", CAST)
    r = c.post("/api/chapters/demo/0001/script/build")
    job = jobs_mod.get(r.json()["job_id"])
    assert job is not None
    jobs_mod.wait(job, timeout=5)
    assert job.state == "done", job.error
    return c


def _line(client, line_id="l0001"):
    doc = client.get("/api/chapters/demo/0001/script").json()
    return next(ln for ln in doc["lines"] if ln["id"] == line_id)


def test_build_uses_scene_cues(client):
    em = _line(client)["emotion"]
    assert em["expression"] == "angry" and em["room"] == "hall"
    assert "jagged outline" in em["cues"] and "angry face" in em["cues"]
    assert em["emphasis"] == ["never"]


def test_knob_override_is_kept_and_spoken(client):
    r = client.post(
        "/api/chapters/demo/0001/script/lines/l0001/emotion",
        json={"gain_db": -9.0, "pitch": 2.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spoken"] is True
    line = _line(client)
    assert line["emotion"]["gain_db"] == -9.0 and line["emotion"]["pitch"] == 2.0
    assert line["emotion"]["source"] == "user"
    assert line["emotion"]["expression"] == "angry"  # untouched cue stays
    assert any("set by hand" in c for c in line["emotion"]["cues"])
    assert line["audio"] == "audio/l0001.wav" and line["dur"] > 0
    assert (paths.chapter_dir("demo", "0001") / "audio" / "l0001.wav").exists()
    # bold word: the line was synthesised in three segments, the bold one slower
    speeds = [c["speed"] for c in CALLS]
    texts = [c["text"] for c in CALLS]
    assert texts == ["I will", "never", "go back!"]
    assert speeds[1] < speeds[0] == speeds[2]

    # rebuild keeps the hand-set emotion
    from panelforge import jobs as jobs_mod

    r = client.post("/api/chapters/demo/0001/script/build")
    job = jobs_mod.get(r.json()["job_id"])
    assert job is not None
    jobs_mod.wait(job, timeout=5)
    line = _line(client)
    assert line["emotion"]["gain_db"] == -9.0 and line["emotion"]["source"] == "user"
    assert line["audio"] == "audio/l0001.wav"


def test_expression_override_reruns_rules(client):
    r = client.post(
        "/api/chapters/demo/0001/script/lines/l0002/emotion",
        json={"expression": "sad", "intensity": 1.0, "room": "comms", "speak": False},
    )
    assert r.status_code == 200, r.text
    line = _line(client, "l0002")
    em = line["emotion"]
    assert em["expression"] == "sad" and em["intensity"] == 1.0
    assert em["eq"] == "radio" and em["room"] == "comms"
    assert em["pitch"] < 0 and em["source"] == "user"
    assert "sad face" in em["cues"] and "comms acoustics" in em["cues"]
    assert line["audio"] is None and r.json()["spoken"] is False


def test_reset_returns_to_automatic_rules(client):
    client.post(
        "/api/chapters/demo/0001/script/lines/l0002/emotion",
        json={"speed": 1.7, "speak": False},
    )
    assert _line(client, "l0002")["emotion"]["speed"] == 1.7
    r = client.post(
        "/api/chapters/demo/0001/script/lines/l0002/emotion",
        json={"reset": True, "speak": False},
    )
    em = _line(client, "l0002")["emotion"]
    assert em["source"] == "auto"
    expected = emotion.rules_for(
        "Please stay.",
        "speech",
        {
            "style": {"outline": "smooth"},
            "balloon_scale": 1.0,
            "mood": "tense",
            "acoustics": {"space": "hall", "size": 0.5},
            "expression": SCENE["panels"]["p1"]["characters"][0]["expression"],
        },
    )
    assert em == expected


def test_bad_values_are_rejected(client):
    for body in ({"expression": "furious"}, {"room": "cathedral"}, {"eq": "phone"}):
        r = client.post("/api/chapters/demo/0001/script/lines/l0001/emotion", json=body)
        assert r.status_code == 400, body
    r = client.post(
        "/api/chapters/demo/0001/script/lines/l9999/emotion", json={"gain_db": 1}
    )
    assert r.status_code == 404


def test_plain_line_is_one_synthesis_call(client):
    CALLS.clear()
    r = client.post(
        "/api/chapters/demo/0001/script/lines/l0002/emotion", json={"gain_db": 1.0}
    )
    assert r.status_code == 200
    assert len(CALLS) == 1 and CALLS[0]["style"] is None


def test_blend_passes_a_style_vector(client, monkeypatch):
    vec = np.ones((510, 1, 256), dtype=np.float32)
    monkeypatch.setattr(
        kokoro_engine, "style_vector", lambda voice, blend: vec if blend else None
    )
    CALLS.clear()
    r = client.post(
        "/api/chapters/demo/0001/script/lines/l0002/emotion",
        json={"blend": {"tone": "dark", "weight": 0.2}},
    )
    assert r.status_code == 200
    assert len(CALLS) == 1 and CALLS[0]["style"] is vec
    assert CALLS[0]["voice"] == "am_michael"  # the pick never changes
