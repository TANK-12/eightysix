import json

import runs


def _assistant(ctx: int, out: int, parent: str | None, *blocks: dict) -> dict:
    return {
        "type": "assistant",
        "parent_tool_use_id": parent,
        "message": {
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": ctx - 10,
                "cache_creation_input_tokens": 0,
                "output_tokens": out,
            },
            "content": list(blocks),
        },
    }


def _write(run_id: str, events: list[dict]) -> dict:
    home = runs.run_dir(run_id)
    home.mkdir(parents=True, exist_ok=True)
    (home / "output.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return {"id": run_id, "started": 0}


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool(name: str) -> dict:
    return {"type": "tool_use", "name": name, "input": {}}


def test_summary_ignores_subagent_events_for_context(data_dir):
    run = _write(
        "mixed",
        [
            _assistant(45_000, 100, None, _text("launching a critic"), _tool("Agent")),
            _assistant(120_000, 200, "toolu_01abc", _text("critic reading")),
            _assistant(170_000, 300, "toolu_01abc", _text("critic says broken")),
        ],
    )
    info = runs.summary(run)
    assert info["context_tokens"] == 45_000
    assert info["last_text"] == "launching a critic"
    assert "Agent" in info["last_action"]
    assert info["output_tokens"] == 600  # spend counts the subagent too


def test_summary_takes_the_latest_main_event(data_dir):
    run = _write(
        "later",
        [
            _assistant(40_000, 1, None, _text("one")),
            _assistant(170_000, 1, "toolu_x", _text("sub")),
            _assistant(48_000, 1, None, _text("two")),
        ],
    )
    info = runs.summary(run)
    assert info["context_tokens"] == 48_000
    assert info["last_text"] == "two"


def test_summary_reads_the_whole_file_when_a_subagent_fills_the_tail(
    data_dir, monkeypatch
):
    monkeypatch.setattr(runs, "TAIL_BYTES", 2_000)
    pad = "x" * 500
    events = [_assistant(52_000, 1, None, _text("main"))]
    events += [_assistant(170_000, 1, "toolu_y", _text(pad)) for _ in range(20)]
    info = runs.summary(_write("flooded", events))
    assert info["context_tokens"] == 52_000
