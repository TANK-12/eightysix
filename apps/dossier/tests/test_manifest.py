"""The crash manifest: a plain record, rewritten every few minutes, of what was
running, so a laptop crash leaves a readable account of where things stood."""

import json

import manifest


def queue_state():
    return {
        "counts": {"queued": 140, "running": 2, "done": 8, "failed": 1, "skipped": 0},
        "paused": False,
        "active_queue": {"id": "q1", "name": "Standard pass", "redo_held": True},
        "in_flight": [
            {"name": "Angela Merkel", "phase": "deep", "started": "2026-09-15T20:00"},
            {"name": "Olaf Scholz", "phase": "deep", "started": "2026-09-15T20:05"},
        ],
        "errors": [{"name": "Moldova", "error": "finished without all its claims"}],
        "jobs": [
            {"name": "Donald Trump", "status": "done", "finished": "2026-09-15T19:40"},
            {"name": "Angela Merkel", "status": "running", "finished": ""},
            {"name": "Xi Jinping", "status": "done", "finished": "2026-09-15T19:50"},
        ],
    }


def test_the_snapshot_says_what_was_running_and_what_finished():
    snap = manifest.snapshot(
        queue_state(),
        written="2026-09-15T20:10",
        data_root="/run/media/ejb/AN3/DossierData",
        subjects=2444,
        jan_models=["Qwen3_5-4B"],
        available_mb=20000,
    )
    assert snap["written"] == "2026-09-15T20:10"
    assert snap["queue"]["name"] == "Standard pass"
    assert snap["queue"]["counts"]["queued"] == 140
    assert [r["name"] for r in snap["running"]] == ["Angela Merkel", "Olaf Scholz"]
    assert [d["name"] for d in snap["recently_finished"]] == [
        "Xi Jinping",
        "Donald Trump",
    ]
    assert snap["failures"] == [
        {"name": "Moldova", "error": "finished without all its claims"}
    ]
    assert snap["library_subjects"] == 2444
    assert snap["jan_models_loaded"] == ["Qwen3_5-4B"]
    assert "queue.json" in snap["how_to_resume"]


def test_it_is_written_to_every_place_that_will_take_it(tmp_path):
    drive = tmp_path / "drive" / "manifest.json"
    laptop = tmp_path / "laptop" / "manifest.json"
    written = manifest.write({"written": "x"}, [drive, laptop])
    assert written == [drive, laptop]
    assert json.loads(drive.read_text()) == {"written": "x"}
    assert json.loads(laptop.read_text()) == {"written": "x"}


def test_an_unplugged_drive_does_not_stop_the_laptop_copy(tmp_path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("a file where a directory should be")
    laptop = tmp_path / "laptop" / "manifest.json"
    written = manifest.write({"written": "x"}, [blocked / "manifest.json", laptop])
    assert written == [laptop]
    assert json.loads(laptop.read_text()) == {"written": "x"}
