import json

import transcripts
from conftest import assistant, tool


def test_describe_tool_uses_plain_words_and_base_names():
    assert transcripts.describe_tool("Edit", {"file_path": "/a/b/web_app.py"}) == (
        "editing web_app.py"
    )
    assert transcripts.describe_tool("Bash", {"description": "Run the tests"}) == (
        "run the tests"
    )
    assert transcripts.describe_tool("Bash", {"command": "rm -rf x"}) == (
        "running a command"
    )
    assert transcripts.describe_tool("Skill", {"skill": "verify"}) == (
        "following the verify skill"
    )
    assert transcripts.describe_tool("mcp__browser__open_page", {}) == (
        "using open page"
    )
    assert transcripts.describe_tool("Frobnicate", {}) == "using Frobnicate"


def test_long_descriptions_are_shortened():
    text = transcripts.describe_tool("Bash", {"description": "x" * 200})
    assert len(text) <= 60 and text.endswith("…")


def test_read_tail_drops_the_cut_first_line(tmp_path):
    path = tmp_path / "t.jsonl"
    lines = [json.dumps({"type": "user", "n": i, "pad": "p" * 50}) for i in range(100)]
    path.write_text("\n".join(lines) + "\n")
    entries = transcripts.read_tail(str(path), limit=500)
    assert entries, "should parse something"
    assert entries[-1]["n"] == 99
    # every parsed entry is whole; the partial first line was skipped
    assert all("pad" in e for e in entries)


def test_summarize_dedupes_usage_and_keeps_model_effort():
    entries = [
        assistant("claude-opus-5", [{"type": "thinking"}], mid="m1"),
        assistant("claude-opus-5", [tool("Read", file_path="/p/a.py")], mid="m1"),
        assistant(
            "claude-opus-5",
            [tool("Edit", file_path="/p/b.py")],
            mid="m2",
            effort="xhigh",
            usage={
                "input_tokens": 0,
                "cache_read_input_tokens": 3000,
                "cache_creation_input_tokens": 0,
                "output_tokens": 400,
            },
        ),
        {"type": "assistant", "message": {"model": "<synthetic>", "content": []}},
    ]
    s = transcripts.summarize(entries)
    assert s["model"] == "claude-opus-5"
    assert s["effort"] == "xhigh"
    assert s["tokens"]["turns"] == 2
    assert s["tokens"]["avg_context"] == (1100 + 3000) // 2
    assert s["tokens"]["avg_output"] == 300
    assert [a["text"] for a in s["actions"]] == ["reading a.py", "editing b.py"]
    assert transcripts.current_action(s, busy=True) == "editing b.py"
    assert transcripts.current_action(s, busy=False) == "taking a break"


def test_current_action_follows_the_last_block_kind():
    s = transcripts.summarize([assistant("m", [{"type": "text", "text": "hi"}])])
    assert transcripts.current_action(s, busy=True) == "writing a reply"


def test_model_family():
    assert transcripts.model_family("claude-sonnet-5") == "sonnet"
    assert transcripts.model_family("claude-haiku-4-5-20251001") == "haiku"
    assert transcripts.model_family(None) is None
