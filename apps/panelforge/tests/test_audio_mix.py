"""mix_timeline: the audio/render hand-off. Builds a small fake chapter
(script.json + rendered line wavs) and checks levels, no clipping, and that
music ducks under dialogue."""

import numpy as np
import pytest

from panelforge.audio import dsp
from panelforge.audio.mix import mix_timeline


@pytest.fixture()
def chapter(tmp_path):
    cdir = tmp_path
    sr = dsp.SR
    tone = (np.sin(2 * np.pi * 300 * np.arange(int(1.0 * sr)) / sr) * 0.6).astype(
        np.float32
    )
    dsp.write_wav(cdir / "audio" / "l0001.wav", tone, sr)
    dsp.write_wav(cdir / "audio" / "l0002.wav", tone, sr)

    script = {
        "schema": 1,
        "lines": [
            {
                "id": "l0001",
                "bubble_id": "b1",
                "speaker": "c01",
                "text": "hi",
                "kind": "speech",
                "emotion": {},
                "audio": "audio/l0001.wav",
                "dur": 1.0,
            },
            {
                "id": "l0002",
                "bubble_id": "b2",
                "speaker": "c01",
                "text": "bye",
                "kind": "speech",
                "emotion": {},
                "audio": "audio/l0002.wav",
                "dur": 1.0,
            },
        ],
        "sfx": [
            {
                "id": "x0001",
                "panel_id": "p0001",
                "source": "auto",
                "sound": "synth:clank",
                "at": "panel-start",
                "gain_db": 0,
            }
        ],
        "music": [
            {
                "id": "m01",
                "from_panel": "p0001",
                "to_panel": "p0002",
                "mood": "calm",
                "track": None,
                "source": "auto",
                "gain_db": -14,
            }
        ],
    }
    (cdir / "script.json").parent.mkdir(parents=True, exist_ok=True)
    import json

    (cdir / "script.json").write_text(json.dumps(script))
    return cdir


@pytest.fixture()
def timeline():
    return {
        "shots": [
            {
                "id": "t0001",
                "panel_id": "p0001",
                "start": 0.0,
                "dur": 2.0,
                "lines": [{"line_id": "l0001", "at": 0.1}],
                "sfx": ["x0001"],
            },
            {
                "id": "t0002",
                "panel_id": "p0002",
                "start": 2.0,
                "dur": 2.0,
                "lines": [{"line_id": "l0002", "at": 0.1}],
                "sfx": [],
            },
        ],
        "music": ["m01"],
    }


def test_mix_produces_nonsilent_no_clip_wav(chapter, timeline, tmp_path):
    out = mix_timeline(chapter, timeline, tmp_path / "mixed.wav")
    assert out.exists()
    samples, sr = dsp.read_wav(out)
    assert sr == dsp.SR
    assert samples.ndim == 2 and samples.shape[1] == 2
    assert np.max(np.abs(samples)) > 0.05
    assert np.max(np.abs(samples)) <= 1.0


def test_duck_lowers_music_under_voice_regions():
    sr = dsp.SR
    music = np.ones((sr * 4, 2), dtype=np.float32) * 0.5
    ducked = dsp.duck(music, sr, [(1.0, 1.0)], amount_db=-10.0, edge_s=0.05)
    inside = np.sqrt(np.mean(ducked[int(1.3 * sr) : int(1.7 * sr)] ** 2))
    outside = np.sqrt(np.mean(ducked[int(2.5 * sr) : int(3.0 * sr)] ** 2))
    assert inside < outside * 0.5  # clearly quieter under the voice region


def test_a_muted_line_keeps_its_place_but_makes_no_sound(chapter, timeline, tmp_path):
    """The Timeline tab's Mute tick box: the line's audio is left out of the
    mix while its slot in the timing is untouched."""
    import json

    loud = mix_timeline(chapter, timeline, tmp_path / "loud.wav")
    a, _ = dsp.read_wav(loud)
    script = json.loads((chapter / "script.json").read_text())
    for ln in script["lines"]:
        ln["muted"] = True
    (chapter / "script.json").write_text(json.dumps(script))
    quiet = mix_timeline(chapter, timeline, tmp_path / "quiet.wav")
    b, _ = dsp.read_wav(quiet)
    assert a.shape == b.shape
    assert np.max(np.abs(b)) < np.max(np.abs(a)) * 0.5
