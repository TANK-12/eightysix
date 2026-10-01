"""Tests for tools/audio/pick_choices.py (lane B4 part 3). Run: python3 -m unittest discover -s tools/audio"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pick_choices  # noqa: E402

RATE = 44100


def read(path: pathlib.Path) -> np.ndarray:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-f",
            "f32le",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


def write(path: pathlib.Path, x: np.ndarray) -> None:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(RATE)]
        + ["-ac", "1", "-i", "-", str(path)],
        input=x.astype(np.float32).tobytes(),
        check=True,
    )


class LoopTest(unittest.TestCase):
    def test_a_loop_repeats_without_a_jump_or_a_dip(self) -> None:
        t = np.arange(int(RATE * 6.0)) / RATE
        rng = np.random.default_rng(3)
        # a hum that drifts in pitch plus noise: a plain cut of it clicks where it wraps
        x = 0.3 * np.sin(
            2 * np.pi * (101.3 * t + 4.0 * t * t)
        ) + 0.005 * rng.standard_normal(len(t))
        with tempfile.TemporaryDirectory() as d:
            src, dst = pathlib.Path(d) / "src.wav", pathlib.Path(d) / "loop.wav"
            write(src, x)
            pick_choices.make_loop(src, dst, 1.13, 3.0, True)
            y = read(dst)
        self.assertAlmostEqual(len(y) / RATE, 3.0, delta=0.01)
        twice = np.concatenate([y, y])
        step = np.abs(np.diff(twice))
        seam = step[len(y) - 3 : len(y) + 2].max()
        # the step across the seam is no bigger than the steps inside the take
        self.assertLessEqual(seam, np.percentile(step, 99.5))
        # no dip: the level around the seam is the take's own level
        rms = lambda a: float(np.sqrt(np.mean(a * a)))  # noqa: E731
        around = twice[len(y) - 2205 : len(y) + 2205]
        self.assertGreater(rms(around), 0.8 * rms(y))


if __name__ == "__main__":
    unittest.main()
