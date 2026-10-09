"""Messages that must never be lost, and requests that must never crash the
backend (critic report claude-behaviour-breaker.md, 2026-10-07).

Claude Code is tests/fake_claude.py, as in test_claude_panel.py.
"""

import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import runner
import web_app

FAKE = Path(__file__).with_name("fake_claude.py")
FORGE = {"X-Forge": "1"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CLAUDE_BIN", f"{sys.executable} {FAKE}")
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(tmp_path / "args.jsonl"))
    monkeypatch.setattr(web_app, "conversations", runner.Registry(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def client(home):
    return TestClient(web_app.app, raise_server_exceptions=False)


def count(conv, kind):
    return sum(e.get("type") == kind for e in conv.events)


def wait_for(conv, kind, n=1, timeout=10.0, step=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if count(conv, kind) >= n:
            return True
        time.sleep(step)
    return False


def wait_until(check, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return False


def new_conv(client):
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    conv = web_app.conversations.get(cid)
    assert conv is not None
    return cid, conv


# --- #1 / #13: a message sent as a restart-after-turn happens --------------------


@pytest.mark.parametrize("attempt", range(4))
def test_a_message_sent_as_the_settings_restart_runs_is_answered(client, attempt):
    cid, conv = new_conv(client)
    client.post(f"/api/conversations/{cid}/send", json={"text": "busy"}, headers=FORGE)
    assert wait_for(conv, "system") and conv.busy
    client.post(
        f"/api/conversations/{cid}/settings", json={"effort": "low"}, headers=FORGE
    )
    # send the moment the turn ends, while the restart is ending the process
    assert wait_for(conv, "result", step=0.001)
    time.sleep(0.01 * attempt)
    r = client.post(
        f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE
    )
    assert r.status_code == 200
    assert wait_for(conv, "result", n=2), [e["type"] for e in conv.events][-6:]
    conv.stop(quiet=True)


def test_stop_then_an_instant_send_is_answered(client):
    cid, conv = new_conv(client)
    client.post(f"/api/conversations/{cid}/send", json={"text": "slow"}, headers=FORGE)
    assert wait_for(conv, "system")
    stopper = threading.Thread(target=conv.stop)
    stopper.start()
    time.sleep(0.005)
    r = client.post(
        f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE
    )
    stopper.join()
    assert r.status_code == 200
    assert wait_for(conv, "result"), [e["type"] for e in conv.events][-6:]
    conv.stop(quiet=True)


# --- #2: a backend restart must not leave the page waiting forever ---------------


def test_the_page_is_told_to_reload_after_a_backend_restart(client, home, monkeypatch):
    cid, conv = new_conv(client)
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result")
    first = client.get(f"/api/conversations/{cid}/events?after=-1", headers=FORGE)
    body = first.json()
    seen, boot = body["events"][-1]["seq"], body["boot"]
    conv.stop(quiet=True)

    # the backend restarts: stream events were never stored, so fewer events
    monkeypatch.setattr(web_app, "conversations", runner.Registry(home / "data"))
    after = client.get(
        f"/api/conversations/{cid}/events?after={seen}&boot={boot}&wait=1",
        headers=FORGE,
    ).json()
    assert after["reset"] is True and after["boot"] != boot
    assert after["events"][0]["seq"] == 0
    assert [e["type"] for e in after["events"]].count("forge_user") == 1

    # an old page that sends no boot id is caught by its seq being past the end
    stale = client.get(
        f"/api/conversations/{cid}/events?after={seen}", headers=FORGE
    ).json()
    assert stale["reset"] is True and stale["events"][0]["seq"] == 0

    # a page in step is not reset
    last = after["events"][-1]["seq"]
    fine = client.get(
        f"/api/conversations/{cid}/events?after={last}&boot={after['boot']}",
        headers=FORGE,
    ).json()
    assert fine["reset"] is False and fine["events"] == []


# --- #3: a write into a dead pipe restarts once, and nothing half-sent stays -----


class BrokenPipe:
    def write(self, _):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")

    def close(self):
        pass


def test_a_broken_pipe_restarts_the_process_and_sends_once(client):
    cid, conv = new_conv(client)
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result")
    assert conv.proc is not None
    conv.proc.stdin = BrokenPipe()  # type: ignore[assignment]
    r = client.post(
        f"/api/conversations/{cid}/send", json={"text": "again"}, headers=FORGE
    )
    assert r.status_code == 200, r.text
    assert wait_for(conv, "result", n=2)
    texts = [e["text"] for e in conv.events if e["type"] == "forge_user"]
    assert texts == ["hi", "again"]
    conv.stop(quiet=True)


def test_a_send_that_cannot_be_written_records_nothing(client, monkeypatch):
    cid, conv = new_conv(client)
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result")
    assert wait_until(lambda: not conv.busy)
    assert conv.proc is not None
    conv.proc.stdin = BrokenPipe()  # type: ignore[assignment]

    def no_start():
        raise RuntimeError("Claude Code would not start")

    monkeypatch.setattr(conv, "_start", no_start)
    before = len(conv.events)
    r = client.post(
        f"/api/conversations/{cid}/send", json={"text": "lost?"}, headers=FORGE
    )
    assert r.status_code == 503
    assert [e for e in conv.events[before:] if e["type"] == "forge_user"] == []
    assert "working" not in conv.meta and not conv.busy
    conv.stop(quiet=True)


# --- #4: streaming arrives in batches, not one round trip per word ---------------


def test_a_long_poll_collects_a_burst_of_events(home):
    conv = runner.Registry(home / "data").create()

    def stream():
        for i in range(30):
            time.sleep(0.01)
            conv._record({"type": "stream_event", "n": i})

    threading.Thread(target=stream, daemon=True).start()
    calls, got, started = 0, [], time.time()
    seq = -1
    while len(got) < 30 and time.time() - started < 5:
        found = conv.events_after(seq, wait=5)
        calls += 1
        got += found
        seq = found[-1]["seq"]
    assert len(got) == 30
    assert calls <= 8, calls  # about 0.3 s of words in ~90 ms batches


def test_events_already_waiting_return_at_once(home):
    conv = runner.Registry(home / "data").create()
    conv._record({"type": "forge_user", "text": "x"})
    started = time.time()
    assert len(conv.events_after(-1, wait=5)) == 1
    assert time.time() - started < 0.05


# --- #5: a settings change survives a message sent mid-turn ----------------------


def test_a_mid_turn_setting_still_restarts_after_a_mid_turn_message(client, home):
    """The setting survives a message sent in the same turn. When that message
    was folded into the turn, nothing tells a folded message from a slow new
    turn, so the restart waits for the next real end of a turn rather than
    risk ending a turn that is starting: the setting then applies one message
    later, and no message is ever lost."""
    cid, conv = new_conv(client)
    client.post(
        f"/api/conversations/{cid}/send", json={"text": "busy one"}, headers=FORGE
    )
    assert wait_for(conv, "system") and conv.busy
    client.post(
        f"/api/conversations/{cid}/settings", json={"effort": "low"}, headers=FORGE
    )
    client.post(
        f"/api/conversations/{cid}/send", json={"text": "and two"}, headers=FORGE
    )
    assert wait_for(conv, "result")
    assert wait_until(lambda: not conv.busy, timeout=6)
    assert conv._close_after_turn  # still pending, not forgotten
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result", n=2)
    assert wait_until(lambda: not conv.running(), timeout=6)
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result", n=3)
    starts = [json.loads(x) for x in (home / "args.jsonl").read_text().splitlines()]
    assert starts[-1][starts[-1].index("--effort") + 1] == "low"
    conv.stop(quiet=True)


# --- #7, #8, #9: bad input is refused or ignored, never a 500 --------------------


BAD_SETTINGS = [
    {"model": [1]},
    {"effort": {}},
    {"mode": ["x"]},
    {"limits": {"max_helpers": "1e999"}},
    {"limits": {"max_helpers": "Infinity"}},
    {"limits": {"max_helpers": "-inf"}},
    {"limits": {"max_helpers": "nan"}},
    {"limits": {"spawn_depth": 1e308 * 10}},
    {"limits": {"helper_model": ["opus"]}},
    {"limits": [1, 2]},
    {"ultracode": "yes"},
    {"cwd": ["/"]},
    {"title": {"a": 1}},
    {"name": ["a"]},
    {"name": 5},
    {"folder": ["x"]},
    {"archived": "false"},
    {"archived": [1]},
]


def test_bad_settings_never_crash_and_change_nothing(client):
    cid, conv = new_conv(client)
    before = json.dumps(conv.meta, sort_keys=True)
    for payload in BAD_SETTINGS:
        r = client.post(
            f"/api/conversations/{cid}/settings",
            content=json.dumps(payload, allow_nan=True),
            headers={**FORGE, "Content-Type": "application/json"},
        )
        assert r.status_code in (200, 400, 422), (payload, r.status_code, r.text)
    after = json.loads(json.dumps(conv.meta, sort_keys=True))
    after.pop("updated", None)
    was = json.loads(before)
    was.pop("updated", None)
    assert after == was
    listed = client.get("/api/conversations", headers=FORGE).json()
    rows = listed if isinstance(listed, list) else listed.get("conversations", [])
    assert not any(c.get("archived") for c in rows if c.get("id") == cid)


def test_real_bools_and_strings_still_work(client):
    cid, conv = new_conv(client)
    r = client.post(
        f"/api/conversations/{cid}/settings",
        json={"name": "  Rei  ", "archived": True, "limits": {"max_helpers": "3"}},
        headers=FORGE,
    )
    assert r.status_code == 200
    assert conv.meta["name"] == "Rei" and conv.meta["limits"] == {"max_helpers": 3}
    assert conv.meta.get("archived")
    client.post(
        f"/api/conversations/{cid}/settings", json={"archived": False}, headers=FORGE
    )
    assert not conv.meta.get("archived")


@pytest.mark.parametrize("files", [5, "abc", [1, 2], {"a": 1}, [None]])
def test_bad_file_lists_are_refused(client, files):
    cid, conv = new_conv(client)
    r = client.post(
        f"/api/conversations/{cid}/send",
        json={"text": "hi", "files": files},
        headers=FORGE,
    )
    assert r.status_code == 400, (files, r.status_code)
    assert count(conv, "forge_user") == 0


def test_a_non_string_text_is_refused(client):
    cid, conv = new_conv(client)
    r = client.post(
        f"/api/conversations/{cid}/send", json={"text": ["hi"]}, headers=FORGE
    )
    assert r.status_code == 400


# --- #12: meta is written while other threads change it --------------------------


def test_meta_saves_and_reads_while_other_threads_change_it(home):
    conv = runner.Registry(home / "data").create()
    conv.meta["big"] = {str(i): i for i in range(300)}
    stop = threading.Event()
    errors: list[BaseException] = []

    def churn():
        i = 0
        while not stop.is_set():
            conv.meta[f"k{i % 50}"] = i
            conv.meta.pop(f"k{(i + 25) % 50}", None)
            conv.meta["big"][str(i % 300 + 300)] = i
            conv.meta["big"].pop(str((i + 150) % 300 + 300), None)
            i += 1

    def save():
        try:
            for _ in range(150):
                conv.save_meta()
                json.dumps(conv.snapshot())
        except BaseException as e:  # noqa: BLE001 - the test reports any
            errors.append(e)

    t = threading.Thread(target=churn, daemon=True)
    t.start()
    savers = [threading.Thread(target=save) for _ in range(2)]
    for s in savers:
        s.start()
    for s in savers:
        s.join()
    stop.set()
    t.join()
    assert errors == []
    stored = json.loads(
        (home / "data" / "conversations" / f"{conv.meta['id']}.json").read_text()
    )
    assert stored["id"] == conv.meta["id"]


# --- look #2: the first paint does not wait on `claude --version` ----------------


def test_options_answer_at_once_while_the_version_is_worked_out(client, monkeypatch):
    slow = [
        sys.executable,
        "-c",
        "import time; time.sleep(2); print('9.9 (Claude Code)')",
    ]
    monkeypatch.setattr(runner, "claude_command", lambda: slow)
    monkeypatch.setattr(web_app, "claude_version", web_app.ClaudeVersion())
    started = time.time()
    first = client.get("/api/options", headers=FORGE).json()
    assert time.time() - started < 1.5 and first["version"] == ""
    assert wait_until(lambda: web_app.claude_version.get() != "", timeout=6)
    assert (
        client.get("/api/options", headers=FORGE).json()["version"]
        == "9.9 (Claude Code)"
    )


# --- found on the live check: total_cost_usd is the session's running total ------


def test_cost_is_the_sessions_running_total_not_a_sum(home):
    conv = runner.Registry(home / "data").create()
    conv.send("one", [])
    assert wait_for(conv, "result")
    conv.send("two", [])
    assert wait_for(conv, "result", n=2)
    # the fake reports 0.001 then 0.002, as the real CLI reports its total
    assert conv.meta["cost_usd"] == 0.002
    conv.stop(quiet=True)


def test_a_cost_summed_before_the_fix_is_kept_but_not_counted(home):
    conv = runner.Registry(home / "data").create()
    conv.meta["cost_usd"] = 0.5
    conv._note_cost({"total_cost_usd": 0.25, "session_id": "s1"})
    conv._note_cost({"total_cost_usd": 0.3, "session_id": "s1"})
    assert conv.meta["session_costs"] == {"earlier": 0.5, "s1": 0.3}
    assert conv.meta["cost_usd"] == 0.3
    conv._note_cost({"total_cost_usd": "nan?", "session_id": "s1"})
    conv._note_cost({"total_cost_usd": float("inf"), "session_id": "s1"})
    assert conv.meta["cost_usd"] == 0.3


def test_an_overcounted_conversation_is_recounted_from_its_log(home):
    """Emerson's Kaito chat showed $2276.72: "earlier" (2201.83) was running
    totals added up. Its log holds every result, so on load the honest
    figure is the largest total per session, and "earlier" stays in meta."""
    data = home / "data"
    folder = data / "conversations"
    folder.mkdir(parents=True)
    meta = {
        "id": "abc123",
        "cost_usd": 2277.22,
        "session_costs": {"earlier": 2201.83, "s2": 1.5},
    }
    (folder / "abc123.json").write_text(json.dumps(meta))
    results = [("s1", 0.4), ("s1", 0.9), ("s2", 1.0), ("s2", 1.75), ("", 9.0)]
    lines = [{"type": "forge_user", "text": "hi"}]
    lines += [
        {"type": "result", "session_id": sid, "total_cost_usd": total}
        for sid, total in results
    ]
    lines.append({"type": "result", "session_id": "s3", "total_cost_usd": "bad"})
    (folder / "abc123.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    conv = runner.Conversation(json.loads((folder / "abc123.json").read_text()), data)
    assert conv.meta["session_costs"] == {"earlier": 2201.83, "s2": 1.75, "s1": 0.9}
    assert conv.meta["cost_usd"] == 2.65
    # a new turn on s2 counts on from its running total, not added to it
    conv._note_cost({"total_cost_usd": 2.0, "session_id": "s2"})
    assert conv.meta["cost_usd"] == 2.9


def test_a_conversation_without_an_earlier_figure_is_left_as_it_was(home):
    conv = runner.Registry(home / "data").create()
    conv.meta["session_costs"] = {"s1": 0.2}
    conv.events.append({"type": "result", "session_id": "s9", "total_cost_usd": 5})
    conv._recount_cost()
    assert conv.meta["session_costs"] == {"s1": 0.2}
    assert conv.meta["cost_usd"] == 0.2


# --- look #12: a crashed turn is one that needs him -----------------------------


def test_a_crash_marks_the_last_turn_failed(home):
    conv = runner.Registry(home / "data").create()
    conv.send("crash now", [])
    assert wait_for(conv, "forge_exit")
    assert wait_until(lambda: (conv.meta.get("last_turn") or {}).get("crashed"))
    assert conv.meta["last_turn"]["ok"] is False and "working" not in conv.meta


# --- second breaker pass (2026-10-07) --------------------------------------------


def test_a_late_message_is_not_lost_to_a_pending_restart(client, home):
    """A setting changed mid-turn, then a message whose turn is slow to start:
    the 1 s quiet after the first turn must not end the process under it."""
    cid, conv = new_conv(client)
    client.post(
        f"/api/conversations/{cid}/send", json={"text": "wait a bit"}, headers=FORGE
    )
    client.post(
        f"/api/conversations/{cid}/settings", json={"effort": "high"}, headers=FORGE
    )
    client.post(
        f"/api/conversations/{cid}/send",
        json={"text": "wait late message"},
        headers=FORGE,
    )
    assert wait_for(conv, "result", n=2, timeout=10), [e["type"] for e in conv.events]
    replies = [e for e in conv.events if e["type"] == "assistant"]
    assert any("late message" in json.dumps(r) for r in replies)
    # and the restart still happens once the turns are over
    assert wait_until(lambda: not conv.running() and not conv.busy, timeout=8)


def test_a_lone_surrogate_never_breaks_the_lists(client):
    cid, conv = new_conv(client)
    r = client.post(
        f"/api/conversations/{cid}/send",
        content='{"text": "emoji split \\ud83d"}',
        headers={**FORGE, "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    client.post(
        f"/api/conversations/{cid}/settings",
        content='{"title": "\\ud800 title", "name": "x\\udfff"}',
        headers={**FORGE, "Content-Type": "application/json"},
    )
    assert wait_for(conv, "result")
    # Claude Code's own output may carry one too
    conv._record(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "cut \ud83d"}]},
        }
    )
    assert (
        client.get(
            f"/api/conversations/{cid}/events?after=-1", headers=FORGE
        ).status_code
        == 200
    )
    assert client.get("/api/conversations", headers=FORGE).status_code == 200
    users = [e["text"] for e in conv.events if e["type"] == "forge_user"]
    assert users == ["emoji split \ufffd"]
    conv.stop(quiet=True)


def test_the_reply_never_comes_before_the_users_bubble(client):
    cid, conv = new_conv(client)
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result")
    assert wait_until(lambda: not conv.busy)
    client.post(
        f"/api/conversations/{cid}/send", json={"text": "  /compact  "}, headers=FORGE
    )
    assert wait_for(conv, "result", n=2)
    kinds = [(e["type"], e.get("subtype") or e.get("text")) for e in conv.events]
    user = kinds.index(("forge_user", "/compact"))  # stripped
    boundary = kinds.index(("system", "compact_boundary"))
    assert user < boundary
    conv.stop(quiet=True)


def test_a_crash_leaves_no_pending_close_for_the_next_process(client):
    cid, conv = new_conv(client)
    client.post(f"/api/conversations/{cid}/send", json={"text": "slow"}, headers=FORGE)
    assert wait_for(conv, "system")
    conv.close()  # busy: marked for after the turn
    assert conv._close_after_turn
    assert conv.proc is not None
    conv.proc.kill()  # it dies instead of ending the turn
    assert wait_for(conv, "forge_exit")
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result")
    time.sleep(0.5)
    assert conv.running()  # not ended after its first turn
    conv.stop(quiet=True)
