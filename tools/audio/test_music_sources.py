"""Checks on the music list (lane B4 part 3). Run: python3 -m unittest discover -s tools/audio"""

import json
import pathlib
import subprocess
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = json.loads((HERE / "music_sources.json").read_text())
REGISTRY = json.loads((HERE.parent.parent / "data/music.json").read_text())["entries"]


def minutes(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
        + [str(path)],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return float(out or 0.0) / 60.0


class MusicSourcesTest(unittest.TestCase):
    def test_sets_and_album_order(self) -> None:
        orders = []
        for t in SPEC["tracks"]:
            self.assertIn(t["set"], {"ost", "song", "extra"}, t["title"])
            if t["set"] == "ost":
                orders.append(t["order"])
        self.assertEqual(orders, list(range(1, len(orders) + 1)), "album order 1..n")

    def test_one_original_of_each_song_and_no_hour_loops(self) -> None:
        songs = [
            t["title"].split(" (")[0] for t in SPEC["tracks"] if t["set"] == "song"
        ]
        self.assertEqual(len(songs), len(set(songs)), "each song once")
        for t in SPEC["tracks"]:
            self.assertNotIn("hour", t["title"].lower(), t["title"])

    def test_files_on_disk_are_single_tracks(self) -> None:
        for key, e in REGISTRY.items():
            path = pathlib.Path(e["path"]).expanduser()
            if (
                path.exists() and e["set"] != "extra"
            ):  # the preview reel is a 20-minute digest
                self.assertLess(minutes(path), 12.0, key)

    def test_extras_are_hidden_behind_the_setting(self) -> None:
        for key, e in REGISTRY.items():
            if e["set"] == "extra":
                self.assertEqual(e.get("show_if"), "audio.music_extras", key)
            else:
                self.assertNotIn("show_if", e, key)


if __name__ == "__main__":
    unittest.main()
