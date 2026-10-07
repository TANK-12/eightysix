"""Tests for tools/builds.py: rebuild only on change, versions saved once and never deleted, share zips."""

import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import builds  # noqa: E402

PLATFORMS = {
    "local": "linux",
    "platforms": {
        "linux": {
            "label": "Linux",
            "file": "game.x86_64",
            "how_to_run": "run it",
            "installer": "install.sh",
            "extra": ["icon.svg"],
        },
        "windows": {
            "label": "Windows",
            "file": "game.exe",
            "how_to_run": "run it",
            "installer": "install.bat",
            "pack_embedded": True,
        },
        "macos": {
            "label": "macOS",
            "file": "game.zip",
            "how_to_run": "open it",
            "installer": "install.command",
        },
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

    def __call__(self, platform: str, debug: bool, root: Optional[Path] = None) -> int:
        root = root or self.root
        self.calls.append(platform)
        if self.fail:
            return 1
        out = root / "build" / platform
        out.mkdir(parents=True, exist_ok=True)
        source = (root / "data.json").read_text()
        name = PLATFORMS["platforms"][platform]["file"]
        if name.endswith(".zip"):
            with zipfile.ZipFile(out / name, "w") as z:
                info = zipfile.ZipInfo("Game.app/Contents/MacOS/Game")
                info.external_attr = 0o100755 << 16
                z.writestr(info, source)
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

    def fake_checkouts(self) -> None:
        """A version's commit stands in as the data.json it was saved with."""
        self.committed = (self.root / "data.json").read_text()
        for name in ("SHARE_WORK", "checkout_version", "drop_checkout"):
            self.addCleanup(setattr, builds, name, getattr(builds, name))
        builds.SHARE_WORK = self.root / "work"

        def checkout(root: Path, commit: str, dest: Path) -> None:
            dest.mkdir(parents=True)
            (dest / "data.json").write_text(self.committed)

        builds.checkout_version = checkout
        builds.drop_checkout = lambda root, dest: shutil.rmtree(dest)
        for name, text in [
            ("install.sh", "#!/bin/sh"),
            ("install.bat", "@echo off"),
            ("install.command", "#!/bin/sh"),
            ("icon.svg", "<svg/>"),
        ]:
            (self.root / name).write_text(text)

    def share_all(self) -> list[Path]:
        return builds.share(
            self.root, PLATFORMS, ["linux", "windows", "macos"], self.godot
        )

    def test_share_needs_a_saved_version(self) -> None:
        with self.assertRaises(SystemExit):
            builds.share(self.root, PLATFORMS, ["linux"], self.godot)

    def test_share_zips_every_platform_with_an_installer(self) -> None:
        self.save()
        self.fake_checkouts()
        (self.root / "data").mkdir()
        (self.root / "data" / "music.json").write_text(
            '{"entries": {"a": {"set": "ost"}, "b": {"credit": "\\"Song\\" by Someone, CC BY 4.0"}}}'
        )
        zips = self.share_all()
        self.assertEqual(
            [z.name for z in zips],
            [
                f"eightysix-0.1.0-alpha-v001-{p}.zip"
                for p in ("linux", "windows", "macos")
            ],
        )
        self.assertTrue(all(z.parent == self.root / "build" / "share" for z in zips))

        def mode(z: zipfile.ZipFile, name: str) -> int:
            return (z.getinfo(name).external_attr >> 16) & 0o777

        stem = zips[0].stem
        with zipfile.ZipFile(zips[0]) as z:
            self.assertEqual(
                sorted(z.namelist()),
                sorted(
                    f"{stem}/{n}"
                    for n in (
                        "game.x86_64",
                        "game.pck",
                        "install.sh",
                        "icon.svg",
                        "HOW-TO-RUN.txt",
                    )
                ),
            )
            self.assertTrue(mode(z, f"{stem}/game.x86_64") & 0o100, "binary runs")
            self.assertEqual(mode(z, f"{stem}/install.sh"), 0o755)
            self.assertEqual(mode(z, f"{stem}/HOW-TO-RUN.txt"), 0o644)
            self.assertIn("run it", z.read(f"{stem}/HOW-TO-RUN.txt").decode())
            readme = z.read(f"{stem}/HOW-TO-RUN.txt").decode()
            self.assertIn("Your music folder", readme)
            self.assertIn("Settings", readme)
            self.assertIn('Music credits:\n  "Song" by Someone, CC BY 4.0\n', readme)
        stem = zips[1].stem
        with zipfile.ZipFile(zips[1]) as z:
            self.assertEqual(
                sorted(z.namelist()),
                sorted(
                    f"{stem}/{n}" for n in ("game.exe", "install.bat", "HOW-TO-RUN.txt")
                ),
                "the pack is inside the exe: one file to run",
            )
        stem = zips[2].stem
        with zipfile.ZipFile(zips[2]) as z:
            self.assertEqual(mode(z, f"{stem}/Game.app/Contents/MacOS/Game"), 0o755)
            self.assertEqual(mode(z, f"{stem}/install.command"), 0o755)
        self.assertFalse(
            (self.root / "work" / "v001").exists(), "scratch checkout gone"
        )

    def test_share_builds_the_saved_version_not_later_edits(self) -> None:
        self.save()
        self.fake_checkouts()
        self.bump("another session's half-done edit")
        zips = self.share_all()
        with zipfile.ZipFile(zips[0]) as z:
            self.assertEqual(z.read(f"{zips[0].stem}/game.pck").decode(), "one")
        with zipfile.ZipFile(zips[2]) as z:
            self.assertEqual(
                z.read(f"{zips[2].stem}/Game.app/Contents/MacOS/Game").decode(), "one"
            )

    def test_share_keeps_only_the_newest_zips_and_clear_deletes_them_all(self) -> None:
        self.save()
        self.fake_checkouts()
        old_share = Path(builds.versions(self.root)[0]["dir"]) / "share"
        old_share.mkdir()
        (old_share / "old-linux.zip").write_bytes(b"old")
        (self.root / "build" / "share").mkdir(parents=True)
        (self.root / "build" / "share" / "older.zip").write_bytes(b"old")
        zips = self.share_all()
        self.assertEqual(builds.share_zips(self.root), sorted(zips))
        self.assertFalse(old_share.exists(), "the emptied old folder goes too")
        count, freed = builds.clear_shares(self.root)
        self.assertEqual(count, 3)
        self.assertGreater(freed, 0)
        self.assertEqual(builds.share_zips(self.root), [])
        self.assertEqual(len(builds.versions(self.root)), 1, "versions are kept")

    def test_a_failed_export_keeps_the_old_zips(self) -> None:
        self.save()
        self.fake_checkouts()
        first = self.share_all()
        self.godot.fail = True
        made = builds.share(self.root, PLATFORMS, ["windows"], self.godot)
        self.assertEqual(made, [])
        self.assertEqual(builds.share_zips(self.root), sorted(first))

    def test_versions_saved_at_made_time(self) -> None:
        self.save()
        info, created = builds.save_version(
            self.root, PLATFORMS, datetime(2026, 1, 2, 3, 4), {}
        )
        self.assertFalse(created)
        self.assertTrue(info["name"].startswith("001-"))


if __name__ == "__main__":
    unittest.main()
