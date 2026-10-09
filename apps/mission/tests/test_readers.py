from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path

from conftest import DEAD_PID, SIDS
from mc import crews, graph, overview, relay_view, sessions


def by_id(data):
    return {s["id"]: s for s in data["sessions"]}


def test_groups_order_and_details(laptop):
    data = overview.collect(laptop["src"], laptop["now"])
    rows = by_id(data)
    assert rows[SIDS["busy"]]["group"] == "working"
    assert rows[SIDS["wait"]]["group"] == "needs_you"
    assert rows[SIDS["idle"]]["group"] == "idle"
    # busy in its file but silent for 15 minutes: not working (the Board's rule)
    assert rows[SIDS["stale"]]["group"] == "idle"
    assert rows[SIDS["ended"]]["group"] == "ended"
    order = [s["group"] for s in data["sessions"]]
    assert order == sorted(order, key=sessions.GROUPS.index)
    busy = rows[SIDS["busy"]]
    assert busy["model"] == "claude-opus-5-5" and busy["effort"] == "high"
    assert busy["context"] == 130_000 and busy["window"] == 200_000
    assert busy["place"] == "Forge"
    assert [a["text"] for a in busy["feed"]][-1] == "editing app.py"
    assert data["counts"]["working"] == 1 and data["counts"]["needs_you"] == 1
    assert data["errors"] == {}


def test_ended_session_summarised_from_transcript(laptop):
    ended = by_id(overview.collect(laptop["src"], laptop["now"]))[SIDS["ended"]]
    assert ended["model"] == "claude-sonnet-4-5" and ended["family"] == "sonnet"
    assert ended["pid"] == DEAD_PID and ended["action"] == "ended"


def test_helper_matched_to_crew_task(laptop):
    busy = by_id(overview.collect(laptop["src"], laptop["now"]))[SIDS["busy"]]
    assert [h["id"] for h in busy["helpers"]] == [
        "abc123"
    ]  # listed once, not per reader
    helper = busy["helpers"][0]
    assert helper["crew_member"] == "helper-1" and helper["persona"] == "Izumi"
    assert helper["crew_status"] == "taken" and helper["model"] == "claude-opus-5-5"
    assert busy["crews"][0]["crew"] == "wave" and busy["crews"][0]["commander"]
    assert busy["label"] == "Kaito"


def test_claude_tab_and_relay_links(laptop):
    rows = by_id(overview.collect(laptop["src"], laptop["now"]))
    assert (
        rows[SIDS["idle"]]["label"] == "Hina"
        and rows[SIDS["idle"]]["claude_tab"] == "conv-9"
    )
    assert rows[SIDS["busy"]]["relay"] == {
        "task": "4",
        "title": "live job",
        "kind": "work",
        "account": "hey",
    }


def test_needs_you_lists_waits_recent_notes_and_blocked_tasks(laptop):
    needs = overview.collect(laptop["src"], laptop["now"])["needs_you"]
    kinds = {
        (n["kind"], n.get("session") or n.get("note") or n.get("task")) for n in needs
    }
    assert ("session", SIDS["wait"]) in kinds
    assert ("note", 1) in kinds
    assert ("note", 2) not in kinds  # three days old: on the crew list only
    assert ("relay", 2) in kinds


def test_crews_shape(laptop):
    data = overview.collect(laptop["src"], laptop["now"])
    wave = next(c for c in data["crews"] if c["name"] == "wave")
    assert wave["active"] and wave["notes"][0]["id"] == 3  # newest first
    assert (
        next(m for m in wave["members"] if m["name"] == "helper-1")["persona"]
        == "Izumi"
    )
    assert (
        wave["tasks"][0]["status"] == "taken"
        and wave["claims"][0]["owner"] == "helper-1"
    )
    assert [n["for_emerson"] for n in wave["notes"]] == [False, True, True]


def test_relay_snapshot(laptop):
    relay = overview.collect(laptop["src"], laptop["now"])["relay"]
    assert relay["present"] and relay["paused"] and relay["boss_up"]
    assert (
        relay["meters"]["hey"]["five"] == 81.0
        and relay["meters"]["default"]["five"] is None
    )
    assert relay["counts"] == {"queued": 1, "blocked": 1, "done": 1, "running": 1}
    assert relay["tasks"][-1]["status"] == "done"  # open ones first
    assert (
        relay["running"][0]["alive"] is False
        and relay["running"][0]["context"] == 50_000
    )


def test_relay_reviewing_task_counts_as_open(laptop):
    # Relay 112's "reviewing" status (a finished task's review run) is still open work.
    (laptop["relay"] / "tasks" / "inbox" / "0005-job.md").write_text(
        f"---\nid: 5\ntitle: in review\nstatus: reviewing\ncreated: {laptop['now'] - 5}\n---\n\n# in review\n"
    )
    tasks = overview.collect(laptop["src"], laptop["now"])["relay"]["tasks"]
    order = [t["status"] for t in tasks]
    assert order.index("reviewing") < order.index("done")


def test_relay_missing_folder(laptop, monkeypatch, tmp_path):
    monkeypatch.setenv("RELAY_DATA_DIR", str(tmp_path / "nowhere"))
    data = overview.collect(laptop["src"], laptop["now"])
    assert data["relay"] == {"present": False}
    assert relay_view.needs_you(data["relay"]) == []


def test_signature_ignores_ticks_and_sees_changes(laptop):
    a = overview.collect(laptop["src"], laptop["now"])
    b = overview.collect(laptop["src"], laptop["now"] + 1)
    assert a["sig"] == b["sig"]
    transcript = laptop["project"] / f"{SIDS['busy']}.jsonl"
    with open(transcript, "a") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "model": "claude-opus-5-5",
                        "content": [{"type": "tool_use", "name": "Grep", "input": {}}],
                    },
                }
            )
            + "\n"
        )
    c = overview.collect(laptop["src"], laptop["now"] + 2)
    assert c["sig"] != a["sig"]


def test_session_vanishing_mid_read_does_not_break(laptop):
    os.remove(laptop["project"] / f"{SIDS['idle']}.jsonl")
    for f in (laptop["proc"] / "4000003").iterdir():
        f.unlink()
    data = overview.collect(laptop["src"], laptop["now"])
    assert SIDS["busy"] in by_id(data) and data["errors"] == {}


def test_crew_board_unreadable_is_skipped(laptop):
    (laptop["crew_home"] / "wave" / "board.json").write_text("{broken")
    data = overview.collect(laptop["src"], laptop["now"])
    assert [c["name"] for c in data["crews"]] == ["forge"]


def test_same_task_matching():
    assert sessions._same_task("H1 Mission Control", "H1 Mission Control app")
    assert sessions._same_task("h2 claude tweaks", "H2 Claude app tweaks and polish")
    assert not sessions._same_task("H1 thing", "H2 thing")
    assert not sessions._same_task("", "H1")
    assert not sessions._same_task("fix the bug", "fix tests")


def test_context_window():
    assert sessions.context_window("claude-opus-5-5[1m]") == 1_000_000
    assert sessions.context_window(None) == 200_000
    # Opus 5.5 holds 1M under a plain id: past 200k it cannot be the small window
    assert sessions.context_window("claude-opus-5-5", 337_571) == 1_000_000
    assert sessions.context_window("claude-opus-5-5", 150_000) == 200_000


def test_old_notes_leave_needs_you():
    board = {"members": {}, "notes": []}

    class Crew:
        @staticmethod
        def open_for(_b, n, reader):
            return n["to"] == reader

    shaped = crews.shape(
        {"name": "c", "members": []},
        {
            **board,
            "notes": [{"id": 1, "t": 0, "from": "x", "to": "Emerson", "text": "?"}],
        },
        Crew,
        now=10 * 86400,
    )
    assert (
        shaped["notes"][0]["for_emerson"]
        and crews.notes_for_emerson([shaped], now=10 * 86400) == []
    )


def _solo_rows(counts):
    return [
        {
            "id": f"s{k}",
            "name": f"ejb-{k}",
            "group": "working",
            "helpers": [
                {"id": f"h{k}-{j}", "state": "working", "task": "t"} for j in range(n)
            ],
            "label": "",
            "action": "x",
            "family": None,
            "place": "~",
        }
        for k, n in enumerate(counts)
    ]


def _lane_ids(g):
    """Every node id, lane by lane, and the lanes' own sanity."""
    nodes = {n["id"] for n in g["nodes"]}
    seen = []
    for lane in g["lanes"]:
        ids = ([lane["lead"]] if lane["lead"] else []) + lane["ring"]
        assert ids, lane  # no empty lanes
        assert set(ids) <= nodes
        seen += ids
    assert len(seen) == len(set(seen)) == len(nodes)  # each card in one lane
    return seen


def test_graph_solo_sessions_bring_their_helpers():
    for counts in ([1], [6], [15], [40], [1, 6, 15], [0, 0, 0, 0, 0, 0], [40, 15]):
        g = graph.build(_solo_rows(counts), [], {}, None)
        _lane_ids(g)
        assert len(g["nodes"]) == len(counts) + sum(counts)
        assert [len(lane["ring"]) for lane in g["lanes"]] == counts
        assert all(lane["kind"] == "solo" and lane["lead"] for lane in g["lanes"])


def _wave():
    """Kaito leads crew overhaul (with a helper); four Relay sessions also sit
    on the shared forge board; one terminal session works alone."""
    rows = _solo_rows([0, 0, 0, 0, 0, 0])
    rows[0]["helpers"] = [
        {"id": "hx", "state": "working", "task": "t", "crew_member": "helper-1"}
    ]
    rows[1]["action"] = "Bash: wait for the critic"
    crew_list = [
        {
            "name": "forge",
            "active": True,
            "commander": None,
            "goal": "",
            "members": [{"name": f"ejb-{k}"} for k in range(5)],
        },
        {
            "name": "overhaul",
            "active": True,
            "commander": "ejb-0",
            "goal": "the wave",
            "members": [{"name": "ejb-0"}, {"name": "helper-1"}],
        },
    ]
    relay = {
        "present": True,
        "counts": {"queued": 2},
        "running": [
            {"id": "r1", "session": "s1", "task": "71", "alive": True},
            {"id": "r2", "session": "s2", "task": "72", "alive": True},
            {"id": "r3", "session": "s0", "task": "63", "alive": True},
            {
                "id": "r4",
                "session": None,
                "task": "74",
                "alive": True,
                "last_action": "Read: notes.md",
            },
        ],
    }
    return rows, crew_list, relay


def test_graph_puts_every_agent_in_one_lane_in_order():
    rows, crew_list, relay = _wave()
    jan = {"models": [{"id": "m", "name": "qwen", "cpu": 40}]}
    g = graph.build(rows, crew_list, relay, jan)
    _lane_ids(g)
    assert [lane["id"] for lane in g["lanes"]] == [
        "crew:overhaul",
        "relay",
        "crew:forge",
        "solo:s5",
        "jan",
    ]
    lanes = {lane["id"]: lane for lane in g["lanes"]}
    nodes = {n["id"]: n for n in g["nodes"]}
    # the commander leads its crew; its Relay run is a badge, not a twin card
    assert lanes["crew:overhaul"]["lead"] == "s:s0"
    assert nodes["s:s0"]["relay_task"] == "63"
    assert lanes["crew:overhaul"]["ring"] == ["h:hx"]
    # Relay keeps the sessions it runs; the shared board gets who is left
    assert lanes["relay"]["ring"] == ["s:s1", "s:s2", "r:r4"]
    assert lanes["relay"]["lead"] is None
    assert "2 queued" in lanes["relay"]["subtitle"]
    assert lanes["crew:forge"]["ring"] == ["s:s3", "s:s4"]
    assert lanes["crew:forge"]["kind"] == "board"
    # plain words: no tool name in front of an action
    assert nodes["s:s1"]["sub"] == "wait for the critic"
    assert nodes["r:r4"]["sub"] == "notes.md"


def test_graph_run_card_reads_as_words():
    """A Relay run with no session yet: its task title, not "task 9", and
    its last command without shell variables or the home folder."""
    home = str(Path.home())
    relay = {
        "present": True,
        "counts": {"queued": 0},
        "tasks": [{"id": 9, "title": "Fix the map"}],
        "running": [
            {
                "id": "r9",
                "session": "",
                "task": "9",
                "alive": False,
                "last_action": f"Bash: F={home}/a/b.md N=2 grep -c x {home}/c",
            },
            {"id": "r8", "session": "", "task": "8", "alive": True, "last_action": "x"},
        ],
    }
    nodes = {n["id"]: n for n in graph.build([], [], relay, None)["nodes"]}
    assert nodes["r:r9"]["label"] == "Fix the map"
    assert nodes["r:r9"]["sub"] == "grep -c x ~/c"
    assert nodes["r:r9"]["state"] == "ended"
    assert nodes["r:r8"]["label"] == "task 8"
    assert graph.plain('Bash: F="/x/a b" N=2 cat x') == "cat x"
    assert graph.plain("Error: build failed") == "Error: build failed"
    assert graph.plain(f"Bash: F={home}/a/0063-forge-ov") == "F=~/a/0063-forge-ov"
    assert graph.plain("mcp__acchan__read_file: notes.md") == "notes.md"


def test_graph_never_repeats_an_agent_sweep():
    rng = random.Random(7)
    for trial in range(400):
        rows, crew_list = [], []
        for k in range(rng.randint(0, 9)):
            helpers = [
                {
                    "id": f"h{k}-{j}",
                    "state": rng.choice(["working", "done"]),
                    "task": "t",
                    "crew_member": rng.choice([None, f"helper-{j}"]),
                }
                for j in range(rng.randint(0, 40))
            ]
            rows.append(
                {
                    "id": f"s{k}",
                    "name": f"ejb-{k}",
                    "group": rng.choice(["working", "idle", "needs_you", "ended"]),
                    "helpers": helpers,
                    "label": "",
                    "action": "x",
                    "family": None,
                    "place": "~",
                }
            )
        for k in range(rng.randint(0, 3)):
            # members include other crews' commanders (ejb-N), as forge does
            others = [
                {"name": f"ejb-{j}", "persona": ""} for j in range(rng.randint(0, 9))
            ]
            extra = [{"name": f"m{j}", "persona": ""} for j in range(rng.randint(0, 6))]
            crew_list.append(
                {
                    "name": f"c{k}",
                    "active": True,
                    "commander": rng.choice([f"ejb-{k}", None, "gone"]),
                    "goal": "",
                    "members": [{"name": f"ejb-{k}"}] + others + extra,
                }
            )
        rng.shuffle(crew_list)
        relay = {
            "present": True,
            "running": [
                {
                    "id": f"r{j}",
                    "session": rng.choice([None, f"s{rng.randint(0, 9)}"]),
                    "task": str(j),
                    "alive": True,
                }
                for j in range(rng.randint(0, 5))
            ],
            "counts": {"queued": 2},
        }
        jan = {
            "models": [
                {"id": f"j{j}", "name": "m", "cpu": rng.random() * 100}
                for j in range(rng.randint(0, 3))
            ]
        }
        g = graph.build(rows, crew_list, relay, jan)
        _lane_ids(g)
        live = {r["id"] for r in rows if r["group"] != "ended"}
        shown = {n["ref"] for n in g["nodes"] if n["kind"] == "session"}
        assert shown == live, trial  # every live session, once
        names = {r["name"]: r["id"] for r in rows if r["group"] != "ended"}
        for c in crew_list:
            if c["commander"] in names:  # a live leader tops a crew lane
                assert any(
                    lane["lead"] == "s:" + names[c["commander"]]
                    for lane in g["lanes"]
                    if lane["kind"] == "crew"
                ), trial


def test_shared_board_sends_only_current_members():
    class Crew:
        @staticmethod
        def open_for(*_):
            return False

    now = 10 * 86400
    members = [{"name": f"old-{i}", "role": "solo", "last_seen": 0} for i in range(50)]
    members += [
        {"name": "fresh", "role": "solo", "last_seen": now - 60},
        {"name": "running", "role": "solo", "last_seen": 0},
    ]
    summary = {"name": "forge", "commander": None, "members": members, "tasks": []}
    shaped = crews.shape(
        summary, {"members": {}, "notes": []}, Crew, now=now, live={"running"}
    )
    assert [m["name"] for m in shaped["members"]] == ["fresh", "running"]
    assert shaped["members_hidden"] == 50


def test_membership_one_chip_per_crew():
    """A session that joined the forge board under three names and leads
    overhaul gets one forge chip and one overhaul lead chip."""
    boards = [
        {
            "crew": "forge",
            "members": {n: {"session": "S1", "role": "helper"} for n in "abc"},
        },
        {
            "crew": "overhaul",
            "commander": "b2",
            "members": {
                "b1": {"session": "S1", "role": "helper"},
                "b2": {"session": "S1", "role": "commander"},
            },
        },
    ]
    chips = sessions.membership(boards)["S1"]
    assert [(c["crew"], c["commander"]) for c in chips] == [
        ("forge", False),
        ("overhaul", True),
    ]
    # by session id and by name together: still one chip per crew
    both = sessions.one_per_crew(chips + sessions.membership(boards)["b2"])
    assert [(c["crew"], c["commander"]) for c in both] == [
        ("forge", False),
        ("overhaul", True),
    ]
