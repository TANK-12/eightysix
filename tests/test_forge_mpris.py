"""Other media players on the desktop for the hub's Now playing (S7, A9/A30).

shared/forge_mpris.py reads MPRIS players (Firefox, Spotify, mpv...) over
D-Bus: what is playing, and play/pause/next/previous/raise. The parts that
turn MPRIS values into the popup's plain dicts are tested here without a bus;
the live check lists the real players on this desktop.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge_mpris  # noqa: E402


def test_metadata_becomes_a_plain_track():
    track = forge_mpris.track(
        {
            "xesam:title": "Lofi mix",
            "xesam:artist": ["daymoon", "friends"],
            "mpris:artUrl": "https://i.ytimg.com/vi/x/hq.jpg",
            "mpris:length": 3_562_666_000,
        }
    )
    assert track == {
        "title": "Lofi mix",
        "artist": "daymoon, friends",
        "artwork": "https://i.ytimg.com/vi/x/hq.jpg",
        "duration": 3562.666,
    }


def test_missing_metadata_is_empty_not_an_error():
    assert forge_mpris.track({}) == {
        "title": "",
        "artist": "",
        "artwork": "",
        "duration": 0,
    }
    assert forge_mpris.track(None)["title"] == ""


def test_only_web_artwork_or_local_files_are_passed_on():
    assert forge_mpris.track({"mpris:artUrl": "javascript:alert(1)"})["artwork"] == ""
    assert (
        forge_mpris.track({"mpris:artUrl": "file:///tmp/a.png"})["artwork"]
        == "file:///tmp/a.png"
    )


def test_forge_s_own_web_views_are_not_listed_twice():
    assert forge_mpris.foreign("org.mpris.MediaPlayer2.firefox.instance_1_20")
    assert not forge_mpris.foreign(
        "org.mpris.MediaPlayer2.org.webkit.app-c03c93.Sandboxed.instance-145607"
    )
    assert not forge_mpris.foreign("org.freedesktop.Notifications")


def test_playerctld_is_a_mirror_not_a_player():
    # playerctld re-publishes whichever player spoke last, so listing it too
    # would show every track twice
    assert not forge_mpris.foreign("org.mpris.MediaPlayer2.playerctld")


def test_commands_are_a_fixed_list():
    assert forge_mpris.METHODS["toggle"] == "PlayPause"
    assert forge_mpris.METHODS["raise"] == "Raise"
    assert "rm" not in forge_mpris.METHODS


def test_the_live_desktop_answers():
    players = forge_mpris.players()
    assert isinstance(players, list)
    for p in players:
        assert p["bus"].startswith("org.mpris.MediaPlayer2.")
        assert p["state"] in ("playing", "paused", "stopped")


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except (AssertionError, AttributeError, TypeError, KeyError) as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failed else 0)


def test_lineage_walks_up_to_the_parents(tmp_path):
    # a helper (300) under the player (200) under the session (100) under init
    for pid, parent, name in (
        (300, 200, "Web Content"),
        (200, 100, "qobuz"),
        (100, 1, "sh"),
    ):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "stat").write_text(f"{pid} ({name}) S {parent} 1 1")
    assert forge_mpris.lineage(300, str(tmp_path)) == [300, 200, 100]


def test_lineage_of_an_unknown_process_is_just_itself(tmp_path):
    assert forge_mpris.lineage(4242, str(tmp_path)) == [4242]
    assert forge_mpris.lineage(0, str(tmp_path)) == []


def test_raise_tries_the_desktop_before_mpris(monkeypatch):
    calls = []
    monkeypatch.setattr(forge_mpris, "_bus", lambda: object())
    monkeypatch.setattr(forge_mpris, "_root_prop", lambda c, b, n: "qobuz")
    monkeypatch.setattr(
        forge_mpris, "focus", lambda c, b, d: calls.append((b, d)) or True
    )
    assert forge_mpris.control("org.mpris.MediaPlayer2.qobuz", "raise")
    assert calls == [("org.mpris.MediaPlayer2.qobuz", "qobuz")]


def test_this_process_lineage_is_real():
    chain = forge_mpris.lineage(os.getpid())
    assert chain[0] == os.getpid() and chain[1] == os.getppid()
