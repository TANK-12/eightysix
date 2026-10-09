"""Checks for u1_sequencer (plain asserts: python3 test_u1_sequencer.py)."""

import json
import os
import tempfile
import time
from pathlib import Path

import u1_sequencer as seq

TMP = Path(tempfile.mkdtemp(prefix="u1seq-"))
seq.LOG = TMP / "log"
seq.STATE = TMP / "state.json"


def run(state, percent, statuses, fail=False, found=None):
    queued = []

    def status_of(tid):
        return statuses.get(tid, "running")

    def queue_fn(text):
        if fail:
            return None
        queued.append(text)
        return 100 + len(state["groups"]) + (1 if state.get("summary") else 0)

    def find(title):
        return (found or {}).get(title)

    return seq.step(state, percent, status_of, queue_fn, find), queued


def fresh():
    return {"groups": {}, "summary": None}


def test_low_usage_fills_three_slots_one_per_step():
    state = fresh()
    for _ in range(5):
        run(state, 13.0, {})
    assert list(state["groups"]) == ["G1", "G2", "G12"]
    assert "group G1: browser" in seq.group_request("G1", "browser", "xhigh")


def test_mid_usage_keeps_one_and_high_or_unknown_usage_none():
    state = fresh()
    run(state, 75.0, {})
    run(state, 75.0, {})
    assert list(state["groups"]) == ["G1"]
    for percent in (93.0, None):
        state = fresh()
        result, queued = run(state, percent, {})
        assert (result, queued, state["groups"]) == ("wait", [], {})


def test_only_ended_statuses_free_a_slot():
    state = fresh()
    for _ in range(3):
        run(state, 10.0, {})
    ids = {g: i["task"] for g, i in state["groups"].items()}
    for busy in ("handing_over", "unknown", "queued", "idle", "something_new"):
        run(state, 10.0, {ids["G1"]: busy})
        assert len(state["groups"]) == 3, busy
    for n, ended in enumerate(("done", "blocked", "parked")):
        run(state, 10.0, {ids["G1"]: ended, ids["G2"]: "done", ids["G12"]: "done"})
        assert len(state["groups"]) == 4 + n


def test_unknown_for_15_minutes_counts_as_missing():
    state = fresh()
    run(state, 10.0, {})
    tid = state["groups"]["G1"]["task"]
    state["groups"]["G1"]["queued_at"] = time.time() - 16 * 60
    for _ in range(3):
        run(state, 10.0, {tid: "unknown"})
    assert state["groups"]["G1"]["status"] == "missing"
    assert len(state["groups"]) == 4


def test_already_queued_group_is_adopted_not_queued_again():
    state = fresh()
    result, queued = run(state, 10.0, {}, found={"U1 every-app sweep, group G1:": 77})
    assert queued == [] and state["groups"]["G1"]["task"] == 77
    # "group G1:" must not match the G12 title
    assert not "U1 every-app sweep, group G12: x".startswith(
        seq.GROUP_TITLE.format("G1")
    )


def test_summary_once_after_every_group_ended():
    state = fresh()
    state["groups"] = {
        g: {"task": i, "status": "running"} for i, (g, _, _) in enumerate(seq.GROUPS)
    }
    done = {i: "done" for i in range(len(seq.GROUPS))}
    result, queued = run(state, 10.0, {**done, 3: "handing_over"})
    assert (result, queued) == ("wait", [])
    result, queued = run(state, 95.0, done)
    assert (result, queued) == ("wait", [])
    result, queued = run(state, 50.0, {**done, 4: "parked"})
    assert result == "done" and len(queued) == 1 and "the summary" in queued[0]
    result, queued = run(state, 50.0, done)
    assert (result, queued) == ("done", [])


def test_queue_failure_stops_without_recording():
    state = fresh()
    result, _ = run(state, 10.0, {}, fail=True)
    assert result == "error" and state["groups"] == {}


def test_front_matter_and_status_ignore_the_body():
    folder = TMP / "tasks" / "inbox"
    folder.mkdir(parents=True)
    (folder / "0099-u1-x.md").write_text(
        "---\nid: 99\ntitle: U1 every-app sweep, group G3: files\nstatus: handing_over\n---\n"
        "\n## State\nstatus: done\n"
    )
    (folder / "0098-broken.md").write_text("no front matter\nstatus: done\n")
    seq.TASKS = TMP / "tasks"
    assert seq.task_status(99) == "handing_over"
    assert seq.task_status(98) == "unknown" and seq.task_status(None) == "unknown"
    assert seq.find_task("U1 every-app sweep, group G3:") == 99
    assert seq.find_task("U1 every-app sweep, group G4:") is None


def test_meter_takes_the_freshest_lowest_account():
    seq.RELAY_STATE = TMP / "relay-state.json"
    meters = {
        "default": {"five": 80.0, "week": 10.0, "age": 0},
        "hey": {"five": 20.0, "week": 95.0, "age": 0},
        "second": {"five": 40.0, "week": 10.0, "age": 30},
        "old": {"five": 1.0, "week": 1.0, "age": 9999},
    }
    seq.RELAY_STATE.write_text(json.dumps({"meters": meters}))
    assert seq.five_hour_percent() == 40.0
    old = time.time() - 3600
    os.utime(seq.RELAY_STATE, (old, old))
    assert seq.five_hour_percent() is None
    seq.RELAY_STATE.write_text("{broken")
    assert seq.five_hour_percent() is None
    assert seq.slots(None) == 0 and seq.slots(69.9) == 3 and seq.slots(70) == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
