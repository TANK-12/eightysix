import json

import conversation
from conftest import assistant


def write_lines(path, entries):
    path.write_bytes(b"".join(json.dumps(e).encode() + b"\n" for e in entries))


def page_all(path, chunk):
    """Every entry, oldest first, collected by paging backwards."""
    got = []
    before = None
    while True:
        page = conversation.read_page(str(path), before, chunk)
        got = page["entries"] + got
        if not page["more"]:
            return got
        assert before is None or page["before"] < before, "a page made no progress"
        before = page["before"]


def test_backwards_pages_hold_every_line_once_at_any_chunk_size(tmp_path):
    path = tmp_path / "t.jsonl"
    write_lines(
        path, [{"type": "user", "n": i, "pad": "x" * (i * 7 % 50)} for i in range(60)]
    )
    # Chunks smaller than one line, near a line, and spanning many lines; the
    # sweep lands the chunk start on, just before and just after line starts.
    for chunk in range(8, 400, 7):
        assert [e["n"] for e in page_all(path, chunk)] == list(range(60)), chunk


def test_line_starting_exactly_at_the_boundary_stays_on_the_newer_page(tmp_path):
    a = json.dumps({"type": "user", "n": 0}).encode() + b"\n"
    b = json.dumps({"type": "user", "n": 1}).encode() + b"\n"
    path = tmp_path / "t.jsonl"
    path.write_bytes(a + b)
    for chunk in (len(b), len(b) + 1, len(b) + 2):
        page = conversation.read_page(str(path), None, chunk)
        assert [e["n"] for e in page["entries"]] == [1], chunk
        assert page["before"] == len(a) and page["more"] is True
    older = conversation.read_page(str(path), len(a), len(b))
    assert [e["n"] for e in older["entries"]] == [0]
    assert older["more"] is False and older["before"] == 0


def test_a_line_still_being_written_is_left_out(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(b'{"type": "user", "n": 0}\n{"type": "user", "n": 1')
    page = conversation.read_page(str(path))
    assert [e["n"] for e in page["entries"]] == [0]
    assert page["more"] is False


def test_a_huge_line_is_only_a_size(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "MAX_LINE_BYTES", 100)
    small = json.dumps({"type": "user", "n": 0}).encode() + b"\n"
    big = json.dumps({"type": "user", "pad": "x" * 400}).encode() + b"\n"
    path = tmp_path / "t.jsonl"
    path.write_bytes(small + big)
    page = conversation.read_page(str(path), None, 64)
    assert page["entries"] == [{"type": "_big", "bytes": len(big)}]
    assert page["before"] == len(small)


def test_items_in_plain_words():
    tool_use = {
        "type": "tool_use",
        "id": "tu1",
        "name": "Bash",
        "input": {"description": "Run the tests", "command": "pytest   -q"},
    }
    picture = {"type": "image", "source": {"type": "base64", "data": "A" * 4000}}
    entries = [
        {"type": "user", "timestamp": "t1", "message": {"content": "build it"}},
        {
            "type": "user",
            "isMeta": True,
            "message": {"content": [{"type": "text", "text": "skill body"}]},
        },
        assistant(
            "claude-opus-5",
            [
                {"type": "thinking", "thinking": ""},
                {"type": "text", "text": "On it."},
                tool_use,
            ],
        ),
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu1", "content": "3 passed"}
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu2",
                        "is_error": True,
                        "content": [{"type": "text", "text": "x" * 50000}, picture],
                    }
                ]
            },
        },
        dict(
            assistant("claude-sonnet-5", [{"type": "text", "text": "helper"}]),
            isSidechain=True,
        ),
        {"type": "attachment"},
        {"type": "_big", "bytes": 9000000},
    ]
    shown = [item for entry in entries for item in conversation.items(entry)]
    assert [i["kind"] for i in shown] == [
        "prompt",
        "reply",
        "tool",
        "result",
        "result",
        "big",
    ]
    assert shown[0]["text"] == "build it" and shown[0]["at"] == "t1"
    assert shown[2]["text"] == "run the tests" and shown[2]["detail"] == "pytest -q"
    assert shown[3]["text"] == "3 passed" and shown[3]["bytes"] == 8
    assert shown[4]["text"] is None and shown[4]["error"] is True
    assert shown[4]["images"] == 1 and shown[4]["bytes"] == 50000 + 3000
    assert shown[5] == {"kind": "big", "bytes": 9000000}
