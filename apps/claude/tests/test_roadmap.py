"""A28: the roadmap tab reads the session briefs in ~/Forge/sessions and the
forge board's open notes. Each brief is a constellation, each ledger item a
star whose state comes from the brief's ## State lines."""

import json
import time

import pytest

import roadmap

S7 = """# S7: Forge polish pass (show-my-dad edition) — session "Hub"

Session ejb-47, solo. Emerson: "polish".

## Ledger
- A1 "do all the work, you're Opus max" -> everything in this one session,
  no helper agents. [constraint]
- A2 "polish the forge related stuff ... really polished before I show my
  dad" -> look-and-feel pass over hub. [core]
- A8 "make the browser load better, it's a bit finicky" -> find what is
  finicky. [core]
  -> handed to S8 (`2026-09-26-S8-claude-enjoy-browser.md`).
- A9 "media button take me where the media is playing" -> a popup. [core]
- A13 "in the preset size text popup I can't name presets" -> typing stays
  in that box. The words ## State in a ledger line must not end the ledger. [core]
- A16 "the full screen is still broken" -> never leaves a band. [core]
- A17-A19 "also build a terminal app and file explorer" -> three new apps;
  brief written as `2026-09-26-S9-terminal-files-code.md` for another session.
- Split (Emerson: "send more tasks off"): S8 = ejb-9e.
- A22 "make the forge app work across many monitors" -> multi-monitor. [core]
- A31 "if you run out, switch the jobs over" -> hand work on. [core]

## State
- Baseline 2026-09-26: tests pass.
- A13 done + checked: hub keydown skips text fields.
- A16 part 1 done + checked (unit), real window not seen: forge.FullScreen
  keeps wishes apart. A99 in a wrapped line is not a subject.
- A16 band done + checked by S7.
- A9 + A27 + A30 done + checked: Now playing.
- A22 not done: needs a restart to try.
- A31 open, waiting on Emerson's pick.
"""

S8 = """# S8: Enjoy-style Claude app + Browser loading — session "Chat"

## Ledger
- **A15** "make a version of the claude app" -> a second layout. [core]
- **A8** "make the browser load better" -> find it. [core]

## State
- A8 done+checked off screen: old pages stacked.
- A15 + A28 not done beyond chunk 1. Chunk plan (a fresh session resumes from the first unchecked chunk):
  1. [done+checked, tests 12 passed] backend
"""

S3 = """# S3: Drift Peaks, audio everywhere, Media downloader

## Ledger (Emerson's words, then what it means)
- **A8** "the youtube downloader is not working" -> fix it. [core]
- **A5** "framerate doesn't show up" -> show it. [detail]
- **A18** Comix: "I will only go searching for the library page" -> list all. [core]
- **A21** "hub music folder" -> a folder. [core]

## State
- **A8 done + checked** (2026-09-25). yt-dlp was fine.
- **A5 done, checked headless** (2026-09-25). The counter was never hidden.
- **A21 done, checked headless; A18 done** (2026-09-25): folder and link.
"""

S2 = """# S2: the Forge hub shell

## Ledger
- **A15** "fix the text size slider" -> raising it. [core]

## State
- A15a App size, done + checked (not yet seen in the real window): forge.py
- A15b-d done + checked: Text size.
"""

S4 = """# S4: Blender + Godot tooling

## Ledger
- **A1** "for the blender mech godot thing" -> finish. [core]
- **A22** "acchan fast" -> fast. [core]

## State
- **A22a done + checked.** Cause: acchan.service.
- **A22b not done yet.**
"""

S9 = """# S9: Terminal, Files and a VS Code-compatible editor — session "Tools"

## Ledger
- **A17** "terminal app" -> a real terminal. [core]
- **A18** "file explorer perfect app" -> a file manager. [core]

## State
- A18 Files: done+checked. apps/files, port 8458.
"""

NO_LEDGER = """# Media players, music button and visualiser fix (ejb-70)

## State
- done+checked: Media library player plays files.
"""


@pytest.fixture
def sessions(tmp_path):
    d = tmp_path / "sessions"
    d.mkdir()
    (d / "2026-09-26-S7-forge-polish.md").write_text(S7)
    (d / "2026-09-26-S8-claude-enjoy-browser.md").write_text(S8)
    (d / "2026-09-25-S3-driftpeaks.md").write_text(S3)
    (d / "2026-09-26-S9-terminal-files-code.md").write_text(S9)
    (d / "2026-09-25-S2-hub-shell.md").write_text(S2)
    (d / "2026-09-25-S4-blender.md").write_text(S4)
    (d / "2026-09-25-media-visualiser-fix.md").write_text(NO_LEDGER)
    (d / "README.md").write_text('# Sessions\n\n## Ledger\n- **A1** "x" -> y\n')
    (d / "STATUS.md").write_text("# Status\n")
    (d / "QUICKSTART.md").write_text("# Quick start\n")
    return d


def session(data, slot, date="2026-09-26"):
    return next(s for s in data["sessions"] if s["slot"] == slot and s["date"] == date)


def item(s, aid):
    return next(i for i in s["items"] if i["id"] == aid)


def test_only_dated_briefs_are_read(sessions):
    files = sorted(s["file"] for s in roadmap.build(sessions, None)["sessions"])
    assert "README.md" not in files and "STATUS.md" not in files
    assert len(files) == 7


def test_title_slot_name_topic_and_date(sessions):
    s7 = session(roadmap.build(sessions, None), "S7")
    assert s7["name"] == "Hub" and s7["date"] == "2026-09-26"
    assert s7["topic"] == "Forge polish pass (show-my-dad edition)"
    s3 = session(roadmap.build(sessions, None), "S3", "2026-09-25")
    assert (
        s3["name"] == ""
        and s3["topic"] == "Drift Peaks, audio everywhere, Media downloader"
    )


def test_ledger_items_carry_quote_meaning_and_tag(sessions):
    s7 = session(roadmap.build(sessions, None), "S7")
    a2 = item(s7, "A2")
    assert (
        a2["quote"].startswith("polish the forge related stuff")
        and "show my dad" in a2["quote"]
    )
    assert a2["meaning"].startswith("look-and-feel pass") and a2["tag"] == "core"
    assert item(s7, "A1")["tag"] == "constraint"
    s3 = session(roadmap.build(sessions, None), "S3", "2026-09-25")
    assert (
        item(s3, "A18")["quote"].startswith("I will only go")
        and item(s3, "A18")["label"] == "Comix"
    )


def test_a_range_is_one_star_per_id_and_lines_without_an_id_are_skipped(sessions):
    ids = [i["id"] for i in session(roadmap.build(sessions, None), "S7")["items"]]
    assert ids == [
        "A1",
        "A2",
        "A8",
        "A9",
        "A13",
        "A16",
        "A17",
        "A18",
        "A19",
        "A22",
        "A31",
    ]


def test_the_words_state_inside_a_ledger_line_do_not_end_the_ledger(sessions):
    s7 = session(roadmap.build(sessions, None), "S7")
    assert "A22" in [i["id"] for i in s7["items"]]


def test_states_from_the_state_lines(sessions):
    s7 = session(roadmap.build(sessions, None), "S7")
    assert item(s7, "A13")["state"] == "done+checked"
    assert item(s7, "A16")["state"] == "done+checked"  # two lines, both done
    assert item(s7, "A9")["state"] == "done+checked"  # "A9 + A27 + A30"
    assert item(s7, "A22")["state"] == "not done"
    assert item(s7, "A31")["state"] == "blocked"
    assert item(s7, "A2")["state"] == "not done"  # no State line at all
    assert "A99" not in [i["id"] for i in s7["items"]]
    assert "Now playing" in item(s7, "A9")["note"]


def test_bold_and_comma_forms(sessions):
    s3 = session(roadmap.build(sessions, None), "S3", "2026-09-25")
    assert item(s3, "A8")["state"] == "done+checked"
    assert item(s3, "A5")["state"] == "done+checked"
    assert item(s3, "A21")["state"] == "done+checked"
    assert item(s3, "A18")["state"] == "done not checked"


def test_sub_items_roll_up_to_their_item(sessions):
    s2 = session(roadmap.build(sessions, None), "S2", "2026-09-25")
    assert item(s2, "A15")["state"] == "done+checked"
    s4 = session(roadmap.build(sessions, None), "S4", "2026-09-25")
    assert item(s4, "A22")["state"] == "in progress"  # A22a done, A22b not


def test_a_chunk_list_under_a_state_line_does_not_change_its_state(sessions):
    s8 = session(roadmap.build(sessions, None), "S8")
    assert item(s8, "A15")["state"] == "not done"
    assert item(s8, "A8")["state"] == "done+checked"


def test_a_handed_on_item_follows_the_session_it_went_to(sessions):
    s7 = session(roadmap.build(sessions, None), "S7")
    a8 = item(s7, "A8")
    assert a8["moved_to"] == "S8" and a8["state"] == "done+checked"


def test_a_brief_written_for_another_session_counts_as_handed_on(sessions):
    s7 = session(roadmap.build(sessions, None), "S7")
    assert (
        item(s7, "A18")["moved_to"] == "S9"
        and item(s7, "A18")["state"] == "done+checked"
    )
    assert item(s7, "A17")["state"] == "not done"  # S9 has no State line for it
    assert item(s7, "A19")["state"] == "moved"  # S9 has no A19 at all


def test_counts_leave_constraints_out(sessions):
    s7 = session(roadmap.build(sessions, None), "S7")
    assert s7["counts"]["total"] == 10  # 11 stars, one a constraint
    assert s7["counts"]["done"] == 5  # A8, A9, A13, A16, A18


def test_a_brief_without_a_ledger_keeps_its_state_lines(sessions):
    s = next(x for x in roadmap.build(sessions, None)["sessions"] if x["slot"] == "")
    assert s["items"] == [] and s["state"][0].startswith("done+checked: Media")
    assert s["topic"].startswith("Media players")


def test_open_board_notes_newest_first(tmp_path, sessions):
    board = tmp_path / "board.json"
    now = time.time()
    board.write_text(
        json.dumps(
            {
                "members": {},
                "notes": [
                    {
                        "id": 1,
                        "t": now - 60,
                        "from": "ejb-47",
                        "to": None,
                        "text": "old",
                    },
                    {
                        "id": 2,
                        "t": now - 30,
                        "from": "Emerson",
                        "to": None,
                        "text": "hi",
                        "ack": True,
                    },
                    {
                        "id": 3,
                        "t": now - 10,
                        "from": "ejb-9e",
                        "to": "Emerson",
                        "text": "pick one",
                    },
                ],
            }
        )
    )
    notes = roadmap.build(sessions, board)["notes"]
    assert [n["id"] for n in notes] == [3, 1]
    assert notes[0]["to"] == "Emerson" and notes[0]["text"] == "pick one"


def test_a_missing_folder_or_board_is_empty_not_an_error(tmp_path):
    data = roadmap.build(tmp_path / "nowhere", tmp_path / "nothing.json")
    assert data["sessions"] == [] and data["notes"] == []
    (tmp_path / "bad.json").write_text("{not json")
    assert roadmap.build(tmp_path / "nowhere", tmp_path / "bad.json")["notes"] == []


def test_newest_sessions_first(sessions):
    dates = [s["date"] for s in roadmap.build(sessions, None)["sessions"]]
    assert dates == sorted(dates, reverse=True)


def test_the_route_serves_the_roadmap_and_needs_the_forge_header(
    sessions, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient

    import web_app

    monkeypatch.setattr(roadmap, "SESSIONS", sessions)
    monkeypatch.setattr(roadmap, "BOARD", tmp_path / "no-board.json")
    client = TestClient(web_app.app)
    assert client.get("/api/roadmap").status_code == 403
    got = client.get("/api/roadmap", headers={"X-Forge": "1"})
    assert got.status_code == 200
    slots = [s["slot"] for s in got.json()["sessions"]]
    assert "S7" in slots and got.json()["notes"] == []
