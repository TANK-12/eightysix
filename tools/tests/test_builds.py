"""Tests for tools/builds.py: rebuild only on change, versions saved once and never deleted, share zips."""

import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import builds  # noqa: E402

PLATFORMS = {
    "local": "linux",
    "platforms": {
        "linux": {"label": "Linux", "file": "game.x86_64", "how_to_run": "run it"},
        "windows": {"label": "Windows", "file": "game.exe", "how_to_run": "run it"},
        "macos": {"label": "macOS", "file": "game.zip", "how_to_run": "open it"},
    },
    "watch_ignore": ["build", "images"],
    "watch_ignore_files": ["*.md"],
}


class FakeGodot:
    """Stands in for a Godot export: writes the binary and a pack whose content is the source."""

    def __init__(self, root: Path):
        self.root = root
        self.calls: list[str] = []
        self.fail = False

    def __call__(self, platform: str, debug: bool) -> int:
        self.calls.append(platform)
        if self.fail:
            return 1
        out = self.root / "build" / platform
        out.mkdir(parents=True, exist_ok=True)
        source = (self.root / "data.json").read_text()
        name = PLATFORMS["platforms"][platform]["file"]
        if name.endswith(".zip"):
            with zipfile.ZipFile(out / name, "w") as z:
                z.writestr("Game.app/data", source)
        else:
            (out / name).write_bytes(b"template")
            (out / name).chmod(0o755)
            (out / (Path(name).stem + ".pck")).write_text(source)
        return 0


class Builds(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "project.godot").write_text('config/version="0.1.0-alpha"\n')
        (self.root / "data.json").write_text("one")
        self.godot = FakeGodot(self.root)
        builds.godot_version = lambda: "4.7.2.stable"
        builds.git_state = lambda root: ("abc1234", False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ensure(self) -> Path:
        binary = builds.ensure(self.root, PLATFORMS, self.godot)
        assert binary is not None
        return binary

    def save(self, note: str = "a finished part") -> Path:
        info, _ = builds.save(self.root, PLATFORMS, self.godot, note)
        return builds.version_binary(info, PLATFORMS)

    def bump(self, text: str) -> None:
        path = self.root / "data.json"
        path.write_text(text)
        st = path.stat()
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    def test_play_builds_but_never_saves_a_version(self) -> None:
        binary = self.ensure()
        self.assertEqual(self.godot.calls, ["linux"])
        self.assertEqual(binary, self.root / "build" / "linux" / "game.x86_64")
        self.assertTrue(binary.is_file())
        self.bump("two")
        self.ensure()
        self.assertEqual(builds.versions(self.root), [], "Play numbers nothing")

    def test_save_numbers_a_version_with_its_note_and_commit(self) -> None:
        self.save("sound and the look pass")
        saved = builds.versions(self.root)
        self.assertEqual([v["number"] for v in saved], [1])
        self.assertEqual(saved[0]["game_version"], "0.1.0-alpha")
        self.assertEqual(saved[0]["commit"], "abc1234")
        self.assertEqual(saved[0]["note"], "sound and the look pass")
        self.assertFalse(saved[0]["dirty"])

    def test_save_refuses_uncommitted_changes_and_an_empty_note(self) -> None:
        builds.git_state = lambda root: ("abc1234", True)
        with self.assertRaises(builds.Refused):
            self.save()
        builds.git_state = lambda root: ("abc1234", False)
        with self.assertRaises(builds.Refused):
            self.save("  ")
        self.assertEqual(builds.versions(self.root), [])

    def test_unchanged_source_does_not_rebuild(self) -> None:
        self.save()
        (self.root / "NOTES.md").write_text("docs never need a rebuild")
        (self.root / "images").mkdir()
        (self.root / "images" / "shot.png").write_bytes(b"png")
        self.ensure()
        self.save()
        self.assertEqual(self.godot.calls, ["linux"])
        self.assertEqual(len(builds.versions(self.root)), 1)

    def test_change_saves_new_version_keeps_old_and_links_binary(self) -> None:
        first = self.save()
        self.bump("two")
        second = self.save()
        self.assertEqual(self.godot.calls, ["linux", "linux"])
        numbers = [v["number"] for v in builds.versions(self.root)]
        self.assertEqual(numbers, [2, 1], "newest first, the old one kept")
        self.assertEqual(
            first.stat().st_ino, second.stat().st_ino, "same template, one copy"
        )
        self.assertEqual((first.parent / "game.pck").read_text(), "one")
        self.assertEqual((second.parent / "game.pck").read_text(), "two")
        self.assertEqual(builds.pick(self.root, PLATFORMS, "previous"), first)
        self.assertEqual(builds.pick(self.root, PLATFORMS, "1"), first)

    def test_same_pack_after_rebuild_is_not_a_new_version(self) -> None:
        self.save()
        self.bump("one")
        self.save()
        self.assertEqual(len(self.godot.calls), 2)
        self.assertEqual(len(builds.versions(self.root)), 1)

    def test_failed_rebuild_plays_last_good_version(self) -> None:
        good = self.save()
        self.bump("broken")
        self.godot.fail = True
        self.assertEqual(builds.ensure(self.root, PLATFORMS, self.godot), good)
        with self.assertRaises(builds.Refused):
            self.save()
        self.godot.fail = False
        self.assertNotEqual(self.ensure(), good, "tries again next launch")

    def test_share_needs_the_current_game_saved(self) -> None:
        with self.assertRaises(SystemExit):
            builds.share(self.root, PLATFORMS, ["linux"], self.godot)

    def test_share_zips_every_platform_with_how_to_run(self) -> None:
        self.save()
        zips = builds.share(
            self.root, PLATFORMS, ["linux", "windows", "macos"], self.godot
        )
        self.assertEqual(
            [z.name for z in zips],
            [
                f"eightysix-0.1.0-alpha-v001-{p}.zip"
                for p in ("linux", "windows", "macos")
            ],
        )
        with zipfile.ZipFile(zips[0]) as z:
            names = z.namelist()
            stem = zips[0].stem
            self.assertIn(f"{stem}/game.x86_64", names)
            self.assertIn(f"{stem}/game.pck", names)
            self.assertIn("run it", z.read(f"{stem}/HOW-TO-RUN.txt").decode())
            mode = z.getinfo(f"{stem}/game.x86_64").external_attr >> 16
            self.assertTrue(mode & 0o100, "Linux binary stays executable")
        with zipfile.ZipFile(zips[2]) as z:
            self.assertIn("Game.app/data", z.namelist())
            self.assertIn("HOW-TO-RUN.txt", z.namelist())
        share_dir = zips[0].parent
        self.assertEqual(sorted(p.suffix for p in share_dir.iterdir()), [".zip"] * 3)
        info = json.loads((share_dir.parent / "VERSION.json").read_text())
        self.assertEqual(info["number"], 1)

    def test_versions_saved_at_made_time(self) -> None:
        self.save()
        info, created = builds.save_version(
            self.root, PLATFORMS, datetime(2026, 1, 2, 3, 4), {}
        )
        self.assertFalse(created)
        self.assertTrue(info["name"].startswith("001-"))


if __name__ == "__main__":
    unittest.main()
