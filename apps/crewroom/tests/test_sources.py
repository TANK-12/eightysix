import os
import glob
import json
from pathlib import Path

import sources
from conftest import write_proc
from sources import crew, helpers, jan, sessions


def test_discovery_finds_every_source_module():
    names = {m.NAME for m in sources.discover()}
    assert {"sessions", "helpers", "crews", "jan"} <= names


def test_sessions_keep_only_live_processes(tree):
    result = sessions.collect(tree["ctx"])
    assert [s["name"] for s in result] == ["forge-builder"]
    s = result[0]
    assert s["model"] == "claude-opus-5"
    assert s["family"] == "opus"
    assert s["effort"] == "high"
    assert s["busy"] is True
    assert s["action"] == "editing web_app.py"
    assert s["place"] == "Forge"
    assert s["tokens"]["turns"] == 2


def test_a_busy_session_quiet_for_five_minutes_is_not_busy(tree):
    ctx = tree["ctx"]
    ctx.now = (
        max(
            os.path.getmtime(p)
            for p in glob.glob(str(tree["claude"] / "projects" / "*" / "*.jsonl"))
        )
        + 301
    )
    got = {s["id"]: s for s in sessions.collect(ctx)}["sess-a"]
    assert got["status"] == "busy" and got["busy"] is False


def test_model_survives_a_tail_full_of_tool_output(tree):
    sessions._known.clear()
    path = tree["claude"] / "projects" / "-home-ejb" / "sess-a.jsonl"
    huge = {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "x" * 200_000}]},
    }
    with open(path, "a") as fh:
        fh.write(json.dumps(huge) + "\n")
    s = sessions.collect(tree["ctx"])[0]
    assert s["model"] == "claude-opus-5" and s["effort"] == "high"

    # once seen, the model is remembered even if the file stops showing it
    path.write_text(json.dumps(huge) + "\n")
    assert sessions.collect(tree["ctx"])[0]["model"] == "claude-opus-5"


def test_helpers_take_model_and_effort_from_agent_type(tree):
    room = {"sessions": sessions.collect(tree["ctx"])}
    result = helpers.collect(tree["ctx"], room)
    assert len(result) == 1
    h = result[0]
    assert h["id"] == "abc123"
    assert h["type"] == "crew-worker" and h["crew"] is True
    assert h["parent_name"] == "forge-builder"
    assert h["family"] == "sonnet"
    assert h["effort"] == "medium"
    assert h["state"] == "working"
    assert h["action"] == "run the app tests"
    assert h["task"] == "Write the jan source"


def test_ultracode_workflow_helpers_are_found(tree):
    # ultracode keeps its helpers in subagents/workflows/wf_<id>/
    (log,) = Path(tree["claude"]).glob("projects/*/sess-a/subagents/agent-abc123.jsonl")
    flow = log.parent / "workflows" / "wf_3b1d"
    flow.mkdir(parents=True)
    for part in (".jsonl", ".meta.json"):
        (log.parent / f"agent-abc123{part}").rename(flow / f"agent-abc123{part}")
    room = {"sessions": sessions.collect(tree["ctx"])}
    found = helpers.collect(tree["ctx"], room)
    assert [h["task"] for h in found] == ["Write the jan source"]


def test_helpers_finish_then_leave(tree):
    ctx = tree["ctx"]
    room = {"sessions": sessions.collect(ctx)}
    ctx.now += helpers.ACTIVE_SECONDS + 10
    assert helpers.collect(ctx, room)[0]["state"] == "done"
    ctx.now += helpers.RECENT_SECONDS
    assert helpers.collect(ctx, room) == []


def test_crew_board_is_trimmed(tree):
    result = crew.collect(tree["ctx"])
    assert result[0]["name"] == "forge"
    assert result[0]["commander"] == "forge-builder"
    assert result[0]["tasks"][0]["status"] == "taken"
    assert result[0]["claims"][0]["owner"] == "forge-builder"
    assert len(result[0]["log"]) == crew.LOG_LINES


def test_jan_models_from_processes_with_cpu_between_polls(tree):
    ctx = tree["ctx"]
    jan._previous.clear()
    first = jan.collect(ctx)
    assert first["running"] is True and first["router_pid"] == 300
    assert [m["name"] for m in first["models"]] == ["Qwen3_5-9B-Q4_K_M"]
    model = first["models"][0]
    assert model["short"] == "Qwen3.5 9B"
    assert model["cpu"] is None
    assert model["rss_mb"] == 1000

    # 200 ticks at 100/s over 2 s is one full core, a quarter of four
    write_proc(
        tree["proc"],
        301,
        "llama-server",
        ["llama-server", "-m", "/m/Qwen3_5-9B-Q4_K_M/model.gguf"],
        utime=250,
        stime=50,
        rss=256000,
    )
    ctx.now += 2
    second = jan.collect(ctx)["models"][0]
    assert second["cpu"] == 100.0
    assert second["share"] == 25.0


def test_jan_alias_wins_and_names_shorten():
    assert jan.model_name(["x", "--alias", "coder", "-m", "a.gguf"]) == "coder"
    assert jan.model_name(["x", "--model=/m/Llama-3-8B.Q4.gguf"]) == "Llama-3-8B.Q4"
    assert jan.short_name("Qwen3_6-35B-A3B-IQ4_XS") == "Qwen3.6 35B A3B"


def test_collect_all_isolates_a_failing_source(tree, monkeypatch):
    def boom(_ctx):
        raise RuntimeError("broken board")

    monkeypatch.setattr(crew, "collect", boom)
    room = sources.collect_all(tree["ctx"])
    assert "crews" not in room
    assert room["errors"]["crews"] == "RuntimeError: broken board"
    assert room["sessions"][0]["name"] == "forge-builder"
    assert room["helpers"][0]["id"] == "abc123"


def test_sessions_carry_the_name_the_board_and_claude_app_use(tree, monkeypatch):
    import forge_session_names

    board = tree["claude"] / "crew" / "names" / "board.json"
    board.parent.mkdir(parents=True)
    board.write_text(
        json.dumps(
            {
                "members": {
                    "forge-builder": {"session": "sess-a", "persona": "Hotaru"},
                    "old": {"session": "sess-a", "persona": "Kana", "last_seen": -1},
                }
            }
        )
    )
    monkeypatch.setattr(forge_session_names, "claude_app_names", lambda *_: {})
    s = sessions.collect(tree["ctx"])[0]
    assert (s["name"], s["label"]) == ("forge-builder", "Hotaru")

    # the Claude app's tab name wins over the board's
    monkeypatch.setattr(
        forge_session_names, "claude_app_names", lambda *_: {"sess-a": "Sora"}
    )
    assert sessions.collect(tree["ctx"])[0]["label"] == "Sora"


def test_a_session_nobody_named_has_no_label(tree):
    assert sessions.collect(tree["ctx"])[0]["label"] == ""
