#!/usr/bin/env python3
"""Reads a b4_sound_check recording (lane B4) and says whether the mix is right.

The bot script (tools/bot/b4_sound_check.json) records the game's own sound while the Juggernaut
stands, walks, sprints, fires, reloads and jumps. This prints the background level while standing,
each scripted moment's level above it, and which sounds played (sound-check.json), then checks:
the standing background is quiet, a 57 mm shot stands well clear of everything else, and no
single tone hums through the standing part.

Usage: tools/audio/sound_check.py [run folder]   (default: the newest images/*-b4_sound_check)
"""

import json
import pathlib
import sys
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/bot/b4_sound_check.json"
STANDING_MAX_DB = -32.0  # rms of the standing second (wind and idle servos only)
SHOT_OVER_BED_DB = 12.0  # a 57 mm shot's loudest 0.25 s against the median of the run
HUM_MAX_SHARE = (
    0.25  # no single frequency bin may hold more of the standing energy than this
)


def load(folder: pathlib.Path) -> tuple[np.ndarray, int]:
    with wave.open(str(folder / "sound-check.wav")) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(
            -1, w.getnchannels()
        )
        return x.astype(float).mean(axis=1) / 32768.0, w.getframerate()


def db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x**2)) + 1e-9))


def main() -> int:
    if len(sys.argv) > 1:
        folder = pathlib.Path(sys.argv[1])
    else:
        folder = sorted((ROOT / "images").glob("*-b4_sound_check"))[-1]
    x, sr = load(folder)
    steps = json.loads(SCRIPT.read_text())["steps"]
    rec_start = next(float(s["at"]) for s in steps if s.get("call") == "record_audio")
    at = lambda t: int((t - rec_start) * sr)  # noqa: E731
    win = sr // 4
    levels = [db(x[i : i + win]) for i in range(0, len(x) - win, win)]
    bed = float(np.median(levels))
    standing = x[at(rec_start + 0.1) : at(rec_start + 0.45)]
    spec = np.abs(np.fft.rfft(standing)) ** 2
    hum_share = float(spec.max() / spec.sum())
    hum_hz = float(np.fft.rfftfreq(len(standing), 1 / sr)[spec.argmax()])
    print(
        f"{folder.name}: median {bed:.1f} dB, standing {db(standing):.1f} dB, loudest tone {hum_hz:.0f} Hz ({hum_share:.0%} of it)"
    )
    ok = True
    shots = [float(s["at"]) for s in steps if s.get("press") == "fire_main"]
    for t in shots:
        seg = x[at(t) : at(t + 0.6)]
        peak = max(db(seg[i : i + win]) for i in range(0, len(seg) - win, win // 4))
        good = peak - bed >= SHOT_OVER_BED_DB
        ok &= good
        print(
            f"  shot at {t:.1f} s: {peak:.1f} dB, {peak - bed:+.1f} over the median {'ok' if good else 'TOO QUIET'}"
        )
    good = db(standing) <= STANDING_MAX_DB
    ok &= good
    print(
        f"  standing background {db(standing):.1f} dB (limit {STANDING_MAX_DB}) {'ok' if good else 'TOO LOUD'}"
    )
    good = hum_share <= HUM_MAX_SHARE
    ok &= good
    print(
        f"  single-tone share {hum_share:.0%} (limit {HUM_MAX_SHARE:.0%}) {'ok' if good else 'HUM'}"
    )
    side = folder / "sound-check.json"
    if side.exists():
        print("  played:", json.loads(side.read_text())["played"])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
