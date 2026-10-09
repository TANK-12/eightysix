"""The Claude panel: the browser MCP server, the runner, and the HTTP API.

Claude Code itself is replaced by tests/fake_claude.py, which speaks the same
stream-json, so nothing here spends anything.
"""

import base64
import io
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import browser_mcp
import runner
import web_app

FAKE = Path(__file__).with_name("fake_claude.py")
FORGE = {"X-Forge": "1"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    args_log = tmp_path / "args.jsonl"
    monkeypatch.setenv("FORGE_CLAUDE_BIN", f"{sys.executable} {FAKE}")
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(args_log))
    registry = runner.Registry(tmp_path / "data")
    monkeypatch.setattr(web_app, "conversations", registry)
    return tmp_path


@pytest.fixture
def client(home):
    return TestClient(web_app.app)


def wait_for(conv, kind, timeout=10, count=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sum(e.get("type") == kind for e in conv.events) >= count:
            return True
        time.sleep(0.05)
    return False


# --- the browser MCP server ---------------------------------------------------------


def rpc(message, opener=None) -> dict:
    """A request that must be answered (notifications are tested apart)."""
    reply = (
        browser_mcp.handle(message, opener) if opener else browser_mcp.handle(message)
    )
    assert reply is not None
    return reply


def test_the_mcp_handshake_and_tool_list():
    init = rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["capabilities"] == {"tools": {}}
    assert (
        browser_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        is None
    )
    tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "open",
        "search",
        "read",
        "tabs",
        "back",
        "forward",
        "reload",
        "switch",
        "close",
    }
    assert all(t["inputSchema"]["additionalProperties"] is False for t in tools)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_a_tool_call_is_one_browser_command():
    sent = []

    def opener(request, timeout):
        sent.append((request.full_url, json.loads(request.data), request.headers))
        return FakeResponse(
            json.dumps({"ok": True, "tab": {"title": "Example"}}).encode()
        )

    reply = rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "open", "arguments": {"url": "https://example.com"}},
        },
        opener,
    )
    url, body, headers = sent[0]
    assert (
        url.endswith("/api/agent/do")
        and body["op"] == "open"
        and body["url"] == "https://example.com"
    )
    assert headers.get("X-forge") == "1"
    assert reply["result"]["isError"] is False
    assert (
        json.loads(reply["result"]["content"][0]["text"])["tab"]["title"] == "Example"
    )


def test_a_browser_failure_is_a_tool_error_not_a_crash(monkeypatch):
    import urllib.error

    monkeypatch.setattr(browser_mcp, "BROWSER_WAIT", 0)

    def opener(request, timeout):
        raise urllib.error.URLError("refused")

    reply = rpc(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "tabs", "arguments": {}},
        },
        opener,
    )
    assert reply["result"]["isError"] is True
    assert "did not open" in reply["result"]["content"][0]["text"]
    unknown = rpc(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "rm"}}
    )
    assert unknown["error"]["code"] == -32602


# --- the runner -------------------------------------------------------------------------


def test_the_command_line_carries_the_settings(tmp_path):
    meta = {"mode": "acceptEdits", "model": "opus", "effort": "xhigh"}
    meta["session_id"] = "abc"
    args = runner.command(meta, tmp_path / "mcp.json", tmp_path / "att")
    assert args[args.index("--effort") + 1] == "xhigh"
    assert args[args.index("--permission-mode") + 1] == "acceptEdits"
    assert args[args.index("--model") + 1] == "opus"
    assert args[args.index("--resume") + 1] == "abc"
    assert args[args.index("--permission-prompts") + 1] == "none"
    assert "mcp__forge-browser" in args[args.index("--allowedTools") + 1]
    safe = runner.command(
        {"mode": "sudo", "model": "gpt", "effort": "turbo"},
        tmp_path / "m",
        tmp_path / "a",
    )
    assert "--effort" not in safe
    assert safe[safe.index("--permission-mode") + 1] == "dontAsk"
    assert "--model" not in safe and "--resume" not in safe


def test_the_mcp_config_points_at_the_browser_server(tmp_path):
    config = json.loads(runner.mcp_config(tmp_path).read_text())
    server = config["mcpServers"]["forge-browser"]
    assert server["args"][0].endswith("browser_mcp.py")


def test_images_go_inline_and_every_file_is_listed(tmp_path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG fake")
    doc = tmp_path / "notes.pdf"
    doc.write_bytes(b"%PDF")
    message = runner.user_message("look", [png, doc])
    blocks = message["message"]["content"]
    assert (
        blocks[0]["type"] == "image"
        and blocks[0]["source"]["media_type"] == "image/png"
    )
    assert str(doc) in blocks[-1]["text"] and str(png) in blocks[-1]["text"]


def test_file_names_cannot_escape_the_attachment_folder(home):
    conv = runner.Registry(home / "d").create()
    path = conv.save_attachment("../../etc/passwd", b"x")
    assert path.parent == conv.attachments and path.name == "passwd"
    again = conv.save_attachment("passwd", b"y")
    assert again.name == "passwd (1)"


def test_a_conversation_streams_remembers_and_resumes(home):
    registry = runner.Registry(home / "data")
    conv = registry.create(cwd=str(home), model="sonnet")
    conv.send("hello", [])
    assert wait_for(conv, "result")
    kinds = [e["type"] for e in conv.events]
    assert kinds[:2] == ["forge_persona", "forge_user"]
    assert "stream_event" in kinds and "assistant" in kinds
    session = conv.meta["session_id"]
    assert session and conv.meta["title"] == "hello" and conv.meta["cost_usd"] == 0.001
    assert conv.busy is False

    # Stopping ends the process; the next message resumes the same session.
    conv.stop()
    conv.send("again", [])
    assert wait_for(conv, "result", count=2)
    assert sum(e["type"] == "result" for e in conv.events) == 2
    runs = [json.loads(l) for l in (home / "args.jsonl").read_text().splitlines()]
    assert (
        "--resume" not in runs[0] and runs[1][runs[1].index("--resume") + 1] == session
    )

    # History survives a restart of the backend, without the live deltas.
    reloaded = runner.Registry(home / "data").get(conv.meta["id"])
    assert reloaded is not None
    stored = [e["type"] for e in reloaded.events]
    assert "assistant" in stored and "stream_event" not in stored
    conv.stop(quiet=True)


def test_closing_an_idle_tab_ends_its_process_quietly(home):
    conv = runner.Registry(home / "data").create()
    conv.send("hello", [])
    assert wait_for(conv, "result")
    assert conv.running()
    assert conv.close() is True
    assert not conv.running()
    assert conv.events[-1]["type"] != "forge_stopped"
    conv.send("again", [])  # reopening resumes it
    assert wait_for(conv, "result", count=2)
    conv.stop(quiet=True)


def test_closing_a_busy_tab_waits_for_the_turn_to_end(home):
    conv = runner.Registry(home / "data").create()
    conv.send("hello", [])
    assert conv.busy
    assert conv.close() is False
    assert wait_for(conv, "result")
    deadline = time.time() + 5
    while conv.running() and time.time() < deadline:
        time.sleep(0.05)
    assert not conv.running()


def test_the_close_endpoint(client, home):
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    r = client.post(f"/api/conversations/{cid}/close", headers=FORGE)
    assert r.status_code == 200 and r.json() == {"closed": False}


def test_stop_ends_a_turn_that_hangs(home):
    conv = runner.Registry(home / "data").create()
    conv.send("slow please", [])
    assert wait_for(conv, "system")
    assert conv.busy
    started = time.time()
    assert conv.stop() is True
    assert time.time() - started < 5 and not conv.busy
    assert conv.events[-1]["type"] == "forge_stopped"


def test_a_setting_changed_mid_turn_applies_to_the_next_message(client, home):
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    conv = web_app.conversations.get(cid)
    assert conv is not None
    client.post(f"/api/conversations/{cid}/send", json={"text": "busy"}, headers=FORGE)
    assert wait_for(conv, "system") and conv.busy
    client.post(
        f"/api/conversations/{cid}/settings", json={"effort": "low"}, headers=FORGE
    )
    assert wait_for(conv, "result")
    deadline = time.time() + 5
    while conv.running() and time.time() < deadline:
        time.sleep(0.05)
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result", count=2)
    starts = [
        json.loads(line) for line in (home / "args.jsonl").read_text().splitlines()
    ]
    assert len(starts) == 2
    assert "--effort" not in starts[0]
    assert starts[1][starts[1].index("--effort") + 1] == "low"
    conv.stop(quiet=True)


def test_a_message_sent_while_claude_works_joins_the_turn(client, home):
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    conv = web_app.conversations.get(cid)
    assert conv is not None
    assert client.post(
        f"/api/conversations/{cid}/send", json={"text": "busy one"}, headers=FORGE
    ).json() == {"ok": True}
    assert wait_for(conv, "system") and conv.busy
    sent = client.post(
        f"/api/conversations/{cid}/send", json={"text": "and two"}, headers=FORGE
    )
    assert sent.status_code == 200
    assert wait_for(conv, "result")
    users = [e for e in conv.events if e["type"] == "forge_user"]
    assert [u.get("during_turn", False) for u in users] == [False, True]
    replies = [e for e in conv.events if e["type"] == "assistant"]
    assert "busy one + and two" in replies[-1]["message"]["content"][0]["text"]
    deadline = time.time() + 3
    while conv.busy and time.time() < deadline:
        time.sleep(0.05)
    assert sum(e["type"] == "result" for e in conv.events) == 1 and not conv.busy
    conv.stop(quiet=True)


def test_a_message_landing_as_the_turn_ends_keeps_the_panel_busy(client, home):
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    conv = web_app.conversations.get(cid)
    assert conv is not None
    client.post(
        f"/api/conversations/{cid}/send", json={"text": "wait one"}, headers=FORGE
    )
    assert wait_for(conv, "system")
    client.post(
        f"/api/conversations/{cid}/send", json={"text": "wait two"}, headers=FORGE
    )
    assert wait_for(conv, "result")
    assert conv.busy  # the second turn is still coming: Stop stays up
    assert wait_for(conv, "result", count=2)
    deadline = time.time() + 3
    while conv.busy and time.time() < deadline:
        time.sleep(0.05)
    assert not conv.busy
    conv.stop(quiet=True)


def test_a_crash_is_reported_with_its_error_output(home):
    conv = runner.Registry(home / "data").create()
    conv.send("crash now", [])
    assert wait_for(conv, "forge_exit")
    exit_event = next(e for e in conv.events if e["type"] == "forge_exit")
    assert exit_event["code"] == 3 and "something broke" in exit_event["stderr"]
    assert not conv.busy


# --- the HTTP API -------------------------------------------------------------------------


def test_every_route_needs_the_forge_header(client):
    assert client.get("/api/conversations").status_code == 403
    assert client.post("/api/conversations", json={}).status_code == 403
    assert (
        client.post("/api/open-link", json={"url": "https://a.org"}).status_code == 403
    )


def test_send_with_an_attachment_and_read_the_events(client):
    conv = client.post(
        "/api/conversations", json={"mode": "plan"}, headers=FORGE
    ).json()
    cid = conv["id"]
    data = base64.b64encode(b"hello file").decode()
    up = client.post(
        f"/api/conversations/{cid}/files",
        json={"name": "a.txt", "data": data},
        headers=FORGE,
    ).json()
    assert up["name"] == "a.txt" and up["bytes"] == 10
    assert (
        client.post(
            f"/api/conversations/{cid}/send",
            json={"text": "read it", "files": ["a.txt"]},
            headers=FORGE,
        ).status_code
        == 200
    )
    seq, seen = -1, []
    deadline = time.time() + 10
    while time.time() < deadline and not any(e["type"] == "result" for e in seen):
        body = client.get(
            f"/api/conversations/{cid}/events?after={seq}&wait=2", headers=FORGE
        ).json()
        seen += body["events"]
        if body["events"]:
            seq = body["events"][-1]["seq"]
    reply = next(e for e in seen if e["type"] == "assistant")["message"]["content"][0][
        "text"
    ]
    assert "read it" in reply and up["path"] in reply
    listed = client.get("/api/conversations", headers=FORGE).json()["conversations"]
    assert listed[0]["id"] == cid and listed[0]["mode"] == "plan"
    web_app.conversations.stop_all()


def test_bad_uploads_and_empty_messages_are_refused(client):
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    assert (
        client.post(
            f"/api/conversations/{cid}/files",
            json={"name": "a", "data": "!!!"},
            headers=FORGE,
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/conversations/{cid}/send", json={"text": "  "}, headers=FORGE
        ).status_code
        == 400
    )
    assert (
        client.get("/api/conversations/../../x/events", headers=FORGE).status_code
        == 404
    )
    assert (
        client.get("/api/conversations/zzzzzzzzzzzz/events", headers=FORGE).status_code
        == 404
    )


def test_settings_apply_from_the_next_message(client):
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    meta = client.post(
        f"/api/conversations/{cid}/settings",
        json={"mode": "acceptEdits", "model": "opus", "effort": "high"},
        headers=FORGE,
    ).json()
    assert meta["mode"] == "acceptEdits" and meta["model"] == "opus"
    assert meta["effort"] == "high"
    kept = client.post(
        f"/api/conversations/{cid}/settings", json={"effort": "turbo"}, headers=FORGE
    ).json()
    assert kept["effort"] == "high"
    fresh = client.post("/api/conversations", json={"effort": "max"}, headers=FORGE)
    assert fresh.json()["effort"] == "max"
    assert (
        client.post(
            f"/api/conversations/{cid}/settings",
            json={"cwd": "/no/such/dir"},
            headers=FORGE,
        ).status_code
        == 400
    )


def test_folders_file_rename_collapse_and_delete(client):
    def call(path, body):
        return client.post(path, json=body, headers=FORGE)

    a = call("/api/conversations", {}).json()["id"]
    b = call("/api/conversations", {}).json()["id"]
    assert call("/api/folders", {"name": "  Mechs   work "}).json()["folders"] == [
        {"name": "Mechs work", "collapsed": False}
    ]
    assert call("/api/folders", {"name": "mechs WORK"}).status_code == 400
    assert call("/api/folders", {"name": ""}).status_code == 400
    call("/api/folders", {"name": "Empty"})

    assert (
        call(f"/api/conversations/{a}/settings", {"folder": "Mechs work"}).json()[
            "folder"
        ]
        == "Mechs work"
    )
    assert (
        call(f"/api/conversations/{b}/settings", {"folder": "Nope"}).status_code == 400
    )

    rows = call(
        "/api/folders/update",
        {"name": "Mechs work", "new_name": "Mechs", "collapsed": True},
    ).json()
    assert rows["folders"][0] == {"name": "Mechs", "collapsed": True}
    listed = {
        c["id"]: c.get("folder", "")
        for c in client.get("/api/conversations", headers=FORGE).json()["conversations"]
    }
    assert listed[a] == "Mechs" and listed[b] == ""

    # Deleting a folder keeps its conversations, out of any folder.
    rows = call("/api/folders/delete", {"name": "Mechs"}).json()["folders"]
    assert [f["name"] for f in rows] == ["Empty"]
    listed = {
        c["id"]: c.get("folder", "")
        for c in client.get("/api/conversations", headers=FORGE).json()["conversations"]
    }
    assert listed[a] == "" and a in listed
    assert call("/api/folders/delete", {"name": "Mechs"}).status_code == 400
    assert client.get("/api/folders", headers=FORGE).json()["folders"] == [
        {"name": "Empty", "collapsed": False}
    ]


def test_links_and_pages_go_through_the_browser(client, monkeypatch):
    calls = []

    def fake_browser(command, timeout=60):
        calls.append(command)
        if command["op"] == "read":
            return {
                "ok": True,
                "page": {
                    "title": "Tides",
                    "url": "https://tides.example/",
                    "text": "High water at noon",
                    "links": [{"text": "More", "href": "https://x/"}],
                },
            }
        return {"ok": True}

    monkeypatch.setattr(web_app, "browser", fake_browser)
    assert (
        client.post(
            "/api/open-link", json={"url": "file:///etc/passwd"}, headers=FORGE
        ).status_code
        == 400
    )
    client.post("/api/open-link", json={"url": "https://a.org/"}, headers=FORGE)
    assert calls[0] == {"op": "open", "url": "https://a.org/", "new_tab": True}
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    page = client.post(
        f"/api/conversations/{cid}/attach-page", json={}, headers=FORGE
    ).json()
    text = Path(page["path"]).read_text()
    assert (
        page["name"].startswith("page - Tides")
        and "High water at noon" in text
        and "https://x/" in text
    )


# --- accounts (profiles) -----------------------------------------------------------


def wait_until(check, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


def sign_in_fake(profiles, name, email="second@example.com"):
    """What a completed `claude auth login` leaves behind in the fake."""
    (profiles.config_dir(name) / ".fake-login").write_text(email)
    profiles.forget_status(name)


def test_profiles_are_directories_and_the_default_is_claude_codes_own(tmp_path):
    profiles = runner.Profiles(tmp_path / "data")
    assert profiles.names() == ["default"] and profiles.active() == "default"
    assert profiles.config_dir("default") is None
    assert "CLAUDE_CONFIG_DIR" not in profiles.env("default")
    assert profiles.add(" Work ") == "work"
    assert profiles.names() == ["default", "work"]
    assert profiles.env("work")["CLAUDE_CONFIG_DIR"] == str(
        tmp_path / "data/profiles/work"
    )
    for bad in ("", "Default!", "a/b", "..", "x" * 33):
        with pytest.raises(ValueError):
            profiles.add(bad)
    with pytest.raises(ValueError):
        profiles.add("work")
    profiles.set_active("work")
    assert profiles.active() == "work"
    with pytest.raises(ValueError):
        profiles.remove("default")
    profiles.remove("work")
    assert profiles.names() == ["default"] and profiles.active() == "default"
    assert not (tmp_path / "data/profiles/work").exists()


def test_every_accepted_name_round_trips_and_every_rejected_one_leaves_nothing(
    tmp_path,
):
    """A sweep over generated names: accepted names come back from names(),
    get a directory and a CLAUDE_CONFIG_DIR inside the data folder; rejected
    ones create nothing."""
    import random
    import string

    rng = random.Random(8)
    alphabet = string.ascii_letters + string.digits + "-_./ !"
    profiles = runner.Profiles(tmp_path / "data")
    accepted, rejected = 0, 0
    for _ in range(2000):
        raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 36)))
        try:
            name = profiles.add(raw)
        except ValueError:
            rejected += 1
            continue
        accepted += 1
        assert name == raw.strip().lower()
        assert name in profiles.names()
        config = Path(profiles.env(name)["CLAUDE_CONFIG_DIR"])
        assert config.is_dir() and config.parent == tmp_path / "data/profiles"
    on_disk = {p.name for p in (tmp_path / "data/profiles").iterdir()}
    assert on_disk == set(profiles.names()) - {"default"}
    assert accepted > 50 and rejected > 50, (accepted, rejected)


def test_login_is_relayed_over_pipes_and_status_follows(home):
    profiles = runner.Profiles(home / "data")
    assert profiles.status("default") == {
        "logged_in": True,
        "email": "default@example.com",
        "org": "default@example.com's Organization",
        "plan": "pro",
    }
    profiles.add("second")
    assert profiles.status("second")["logged_in"] is False
    login = profiles.login("second")
    assert wait_until(lambda: login.state == "waiting")
    assert login.url == "https://claude.com/cai/oauth/authorize?code=fake&state=fake"
    assert profiles.login("second") is login  # one at a time per profile
    login.code("wrong")
    assert wait_until(lambda: login.state == "failed")
    assert "Login failed" in login.error
    with pytest.raises(RuntimeError):
        login.code("again")
    login = profiles.login("second")
    assert wait_until(lambda: login.state == "waiting")
    login.code("good-code#state")
    assert wait_until(lambda: login.state == "done")
    state = profiles.login_state("second")
    assert state is not None and state["state"] == "done"
    assert profiles.status("second")["email"] == "second@example.com"
    described = profiles.describe()
    assert [p["name"] for p in described["profiles"]] == ["default", "second"]
    assert described["profiles"][1]["logged_in"] is True
    cancelled = profiles.login("second")
    cancelled.cancel()
    assert wait_until(lambda: not cancelled.running())


def test_a_conversation_runs_on_its_profile_and_stays_there(home):
    registry = runner.Registry(home / "data")
    profiles = registry.profiles
    profiles.add("second")
    sign_in_fake(profiles, "second")
    profiles.set_active("second")
    conv = registry.create(cwd=str(home))
    assert conv.meta["profile"] == "second"
    conv.send("hello", [])
    assert wait_for(conv, "result")
    runs = [json.loads(l) for l in (home / "args.jsonl").read_text().splitlines()]
    assert runs[-1][-1] == "CLAUDE_CONFIG_DIR=" + str(home / "data/profiles/second")
    usage = json.loads((home / "data/profiles.json").read_text())["usage"]["second"]
    assert usage["five_hour"]["used"] == 0.42 and usage["seven_day"]["used"] == 0.07

    # A new default only affects new conversations: this one stays on "second".
    profiles.set_active("default")
    conv.stop(quiet=True)
    conv.send("more", [])
    assert wait_for(conv, "result", count=2)
    runs = [json.loads(l) for l in (home / "args.jsonl").read_text().splitlines()]
    assert runs[-1][-1].endswith("/profiles/second")
    assert registry.create().meta["profile"] == "default"
    conv.stop(quiet=True)

    # A profile that is not signed in refuses to start, with a plain message.
    profiles.add("third")
    other = registry.create(profile="third")
    with pytest.raises(RuntimeError, match="not signed in"):
        other.send("hi", [])
    assert not (home / "data/conversations" / f"{other.meta['id']}.jsonl").exists()


def test_the_account_routes(client, home, monkeypatch):
    monkeypatch.setenv("HOME", str(home))
    listed = client.get("/api/profiles", headers=FORGE).json()
    assert listed["active"] == "default"
    assert listed["profiles"][0]["email"] == "default@example.com"
    assert (
        client.post("/api/profiles", json={"name": "a b"}, headers=FORGE).status_code
        == 400
    )
    added = client.post("/api/profiles", json={"name": "second"}, headers=FORGE).json()
    assert added["name"] == "second" and added["profiles"][1]["logged_in"] is False

    started = client.post("/api/profiles/second/login", headers=FORGE).json()
    assert started["state"] == "waiting" and started["url"].startswith("https://")
    assert (
        client.post(
            "/api/profiles/second/login/code", json={"code": ""}, headers=FORGE
        ).status_code
        == 400
    )
    failed = client.post(
        "/api/profiles/second/login/code", json={"code": "nope"}, headers=FORGE
    ).json()
    assert failed["state"] == "failed" and "Login failed" in failed["error"]
    client.post("/api/profiles/second/login", headers=FORGE)
    done = client.post(
        "/api/profiles/second/login/code",
        json={"code": "good-code#state"},
        headers=FORGE,
    ).json()
    assert done["state"] == "done"
    assert (
        client.get("/api/profiles/second/login", headers=FORGE).json()["state"]
        == "done"
    )
    second = client.get("/api/profiles", headers=FORGE).json()["profiles"][1]
    assert second["logged_in"] is True and second["email"] == "second@example.com"

    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    switched = client.post("/api/profiles/second/activate", headers=FORGE).json()
    assert switched["active"] == "second" and "moved" not in switched
    events = client.get(f"/api/conversations/{cid}/events", headers=FORGE).json()
    assert events["meta"]["profile"] == "default" and not events["events"]
    assert (
        client.post("/api/conversations", json={}, headers=FORGE).json()["profile"]
        == "second"
    )
    kept = client.post(
        f"/api/conversations/{cid}/settings", json={"profile": "second"}, headers=FORGE
    ).json()
    assert kept["profile"] == "default"
    picked = client.post(
        "/api/conversations", json={"profile": "default"}, headers=FORGE
    ).json()
    assert picked["profile"] == "default"
    assert client.post("/api/profiles/nope/activate", headers=FORGE).status_code == 404
    assert client.delete("/api/profiles/default", headers=FORGE).status_code == 400
    removed = client.delete("/api/profiles/second", headers=FORGE).json()
    assert [p["name"] for p in removed["profiles"]] == ["default"] and removed[
        "active"
    ] == "default"
    assert client.post("/api/profiles/second/login", headers=FORGE).status_code == 404


# --- the / and . command menu ------------------------------------------------------


def write_skill(folder, name, description):
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"
    )


def test_skills_and_commands_on_disk_are_found_with_descriptions(tmp_path):
    main = tmp_path / "main"
    write_skill(main / "skills/verify", "verify", "Test-first verification loop.")
    (main / "skills/folded").mkdir(parents=True)
    (main / "skills/folded/SKILL.md").write_text(
        "---\nname: folded\ndescription: >\n  Two lines\n  of text.\n---\n"
    )
    write_skill(main / "skills/synced/bucket/docx", "docx", '"Word files."')
    (main / "commands").mkdir()
    (main / "commands/ship.md").write_text("---\ndescription: Ship it\n---\nBody")
    plugin = tmp_path / "cache/feature-dev/abc"
    write_skill(plugin / "skills/explore", "explore", "Explore the code.")
    (plugin / "commands").mkdir()
    (plugin / "commands/feature-dev.md").write_text("No header here")
    nested = tmp_path / "cache/mp/1.0"
    write_skill(nested / "skills/engineering/tdd", "tdd", "Red, green, refactor.")
    write_skill(nested / "skills/in-progress/draft", "draft", "Not exposed.")
    (nested / ".claude-plugin").mkdir()
    (nested / ".claude-plugin/plugin.json").write_text(
        json.dumps({"skills": ["./skills/engineering/tdd", "./skills/gone"]})
    )
    (main / "plugins").mkdir()
    (main / "plugins/installed_plugins.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "feature-dev@official": [{"installPath": str(plugin)}],
                    "mp@official": [{"installPath": str(nested)}],
                }
            }
        )
    )
    assert runner.scan_commands(main) == {
        "verify": "Test-first verification loop.",
        "folded": "Two lines of text.",
        "anthropic-skills:docx": "Word files.",
        "ship": "Ship it",
        "feature-dev:explore": "Explore the code.",
        "feature-dev:feature-dev": "",
        "mp:tdd": "Red, green, refactor.",
    }
    assert runner.scan_commands(tmp_path / "nothing-here") == {}


def test_commands_come_from_the_newest_init_event_and_the_disk(client, home):
    assert client.get("/api/commands", headers=FORGE).json() == {"commands": []}
    write_skill(runner.MAIN_CONFIG / "skills/verify", "verify", "Check it.")
    write_skill(runner.MAIN_CONFIG / "skills/lean", "lean", "Save tokens.")
    listed = client.get("/api/commands", headers=FORGE).json()["commands"]
    assert {c["name"] for c in listed} == {"verify", "lean"}
    registry = web_app.conversations
    registry.create(cwd=str(home))  # never started: no init event, skipped
    conv = registry.create(cwd=str(home))
    conv.send("hello", [])
    assert wait_for(conv, "result")
    conv.stop(quiet=True)
    expected = [
        {"name": "verify", "description": "Check it."},
        {"name": "clear", "description": ""},
        {"name": "mattpocock-skills:tdd", "description": ""},
        {"name": "lean", "description": "Save tokens."},
    ]
    assert client.get("/api/commands", headers=FORGE).json()["commands"] == expected
    # After a restart the list is read back from the stored events.
    assert runner.Registry(home / "data").commands() == expected


# --- personas -------------------------------------------------------------------


def test_each_message_carries_a_persona_tag_picked_by_mood(home):
    conv = runner.Registry(home / "data").create()
    conv.send("still bloody not working, fix it", [])
    assert wait_for(conv, "result")
    conv.send("so tldr what have you done", [])
    assert wait_for(conv, "result", count=2)
    tags = (home / "tags.txt").read_text().splitlines()
    assert tags == [
        "[persona: Shizu | mood: fix]",
        "[persona: Arch-chan | mood: status]",
    ]
    shown = [e for e in conv.events if e["type"] == "forge_user"]
    assert shown[0]["text"] == "still bloody not working, fix it"  # tag never shown
    runs = [json.loads(l) for l in (home / "args.jsonl").read_text().splitlines()]
    prompt = runs[0][runs[0].index("--append-system-prompt") + 1]
    assert "Tetsu" in prompt and "No explicit sexual content" in prompt
    conv.stop(quiet=True)


def test_personas_can_be_switched_off_and_pinned(home):
    conv = runner.Registry(home / "data").create()
    conv.personas.save_prefs({"pinned": "kira"})
    persona, mood = conv.personas.for_message("hey how are you")
    assert persona["id"] == "kira" and mood == "downtime"
    conv.personas.save_prefs({"enabled": False, "pinned": "auto"})
    conv.send("hello", [])
    assert wait_for(conv, "result")
    assert not (home / "tags.txt").exists()
    assert not any(e["type"] == "forge_persona" for e in conv.events)
    conv.stop(quiet=True)


def test_claude_is_found_without_local_bin_on_path(monkeypatch, tmp_path):
    fake = tmp_path / ".local/bin/claude"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.delenv("FORGE_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(runner.Path, "home", staticmethod(lambda: tmp_path))
    assert runner.claude_command() == [str(fake)]


def test_a_closed_browser_is_waited_for_while_forge_opens_it():
    import io
    import urllib.error

    tries = []

    def opener(request, timeout):
        tries.append(1)
        if len(tries) < 3:
            raise urllib.error.URLError("connection refused")
        return io.BytesIO(b'{"ok": true, "title": "Example"}')

    got = browser_mcp.call_browser("read", {}, opener, wait=10, sleep=lambda s: None)
    assert got == {"ok": True, "title": "Example"} and len(tries) == 3


def test_a_browser_that_never_opens_gives_up_with_a_plain_reason():
    import urllib.error

    def opener(request, timeout):
        raise urllib.error.URLError("connection refused")

    clock = iter(range(0, 1000, 5))
    got = browser_mcp.call_browser(
        "read", {}, opener, wait=20, sleep=lambda s: None, now=lambda: next(clock)
    )
    assert got["ok"] is False and "did not open" in got["error"]


def test_every_account_gets_the_users_own_mcp_servers_too(tmp_path):
    user = tmp_path / "claude.json"
    user.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "acchan": {"command": "/usr/bin/acchan-mcp"},
                    "forge-browser": {"command": "not-this-one"},
                }
            }
        )
    )
    path = runner.mcp_config(tmp_path / "data", user_config=user)
    servers = json.loads(path.read_text())["mcpServers"]
    assert servers["acchan"] == {"command": "/usr/bin/acchan-mcp"}
    assert servers["forge-browser"]["args"][0].endswith("browser_mcp.py")
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    assert set(
        json.loads(runner.mcp_config(tmp_path / "d2", user_config=broken).read_text())[
            "mcpServers"
        ]
    ) == {"forge-browser"}


def test_two_profiles_on_the_same_account_are_flagged(tmp_path, monkeypatch):
    profiles = runner.Profiles(tmp_path / "data")
    profiles.add("second")
    profiles.add("third")
    who = {
        "default": {"logged_in": True, "email": "Me@x.com", "org": "o"},
        "second": {"logged_in": True, "email": "me@x.com", "org": "o"},
        "third": {"logged_in": True, "email": "other@x.com", "org": "o2"},
    }
    monkeypatch.setattr(profiles, "status", lambda name, refresh=False: who[name])
    monkeypatch.setattr(profiles, "poll_usage", lambda name, wait=False: False)
    got = {p["name"]: p for p in profiles.describe()["profiles"]}
    assert got["second"]["same_as"] == "default"
    assert "same_as" not in got["default"] and "same_as" not in got["third"]


def test_sonnet_5_5_is_offered_by_full_id():
    assert runner.MODELS["claude-sonnet-5-5"] == "Sonnet 5.5"
    assert "sonnet" in runner.MODELS


# --- ultracode and the agent limits (2026-10-07) ------------------------------------


def test_ultracode_goes_in_as_session_settings(tmp_path):
    plain = runner.command({"model": "opus"}, tmp_path / "m", tmp_path / "a")
    assert "--settings" not in plain
    ultra = runner.command(
        {"model": "opus", "ultracode": True}, tmp_path / "m", tmp_path / "a"
    )
    settings = json.loads(ultra[ultra.index("--settings") + 1])
    # ultracode alone is refused while dynamic workflows are off (checked live)
    assert settings == {"ultracode": True, "enableWorkflows": True}


def test_every_agent_limit_is_described_completely():
    assert set(runner.AGENT_LIMITS) >= {"max_helpers", "spawn_depth", "helper_model"}
    envs = set()
    for key, spec in runner.AGENT_LIMITS.items():
        assert spec["env"].startswith("CLAUDE_CODE_") and spec["env"] not in envs
        envs.add(spec["env"])
        assert spec["label"] and spec["kind"] in ("int", "choice")
        if spec["kind"] == "int":
            assert 0 <= spec["min"] < spec["max"]
        else:
            assert spec["choices"] and "" not in spec["choices"]
            assert set(spec["choices"]) <= set(runner.MODELS)


def test_limit_values_are_cleaned_across_every_kind():
    ints = [k for k, s in runner.AGENT_LIMITS.items() if s["kind"] == "int"]
    choices = [k for k, s in runner.AGENT_LIMITS.items() if s["kind"] == "choice"]
    for key in ints:
        lo, hi = runner.AGENT_LIMITS[key]["min"], runner.AGENT_LIMITS[key]["max"]
        for raw, want in [
            (lo, lo),
            (hi, hi),
            (str(lo + 1), lo + 1),
            (hi + 100, hi),
            (lo - 5, lo),
            (2.7, min(hi, max(lo, 2))),
            ("", None),
            (None, None),
            ("lots", "skip"),
            (True, "skip"),
            ([3], "skip"),
        ]:
            got = runner.clean_limits({key: raw})
            if want == "skip":
                assert key not in got, (key, raw)
            else:
                assert got == {key: want}, (key, raw, got)
    for key in choices:
        for value in runner.AGENT_LIMITS[key]["choices"]:
            assert runner.clean_limits({key: value}) == {key: value}
        assert runner.clean_limits({key: "gpt-9"}) == {}
        assert runner.clean_limits({key: ""}) == {key: None}
    assert runner.clean_limits({"no_such_limit": 3}) == {}
    assert runner.clean_limits("junk") == {}  # type: ignore[arg-type]


def test_limits_become_env_and_empty_means_claude_codes_default():
    inherited = {spec["env"]: "99" for spec in runner.AGENT_LIMITS.values()}
    inherited["PATH"] = "/bin"
    env = runner.apply_limits(
        dict(inherited), {"limits": {"max_helpers": 4, "helper_model": "haiku"}}
    )
    assert env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] == "4"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "haiku"
    assert "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH" not in env
    assert env["PATH"] == "/bin"
    bare = runner.apply_limits(dict(inherited), {})
    assert not any(spec["env"] in bare for spec in runner.AGENT_LIMITS.values())


def test_ultracode_and_limits_through_the_api(client, home):
    options = client.get("/api/options", headers=FORGE).json()
    assert options["agent_limits"] == runner.AGENT_LIMITS
    assert options["ultracode"]["unsupported_models"] == ["haiku"]
    cid = client.post("/api/conversations", json={}, headers=FORGE).json()["id"]
    conv = web_app.conversations.get(cid)
    assert conv is not None
    meta = client.post(
        f"/api/conversations/{cid}/settings",
        json={"ultracode": True, "limits": {"max_helpers": "3", "spawn_depth": 2}},
        headers=FORGE,
    ).json()
    assert meta["ultracode"] is True
    assert meta["limits"] == {"max_helpers": 3, "spawn_depth": 2}
    # one key at a time merges; "" clears just that one
    meta = client.post(
        f"/api/conversations/{cid}/settings",
        json={"limits": {"spawn_depth": "", "helper_model": "sonnet"}},
        headers=FORGE,
    ).json()
    assert meta["limits"] == {"max_helpers": 3, "helper_model": "sonnet"}
    client.post(f"/api/conversations/{cid}/send", json={"text": "hi"}, headers=FORGE)
    assert wait_for(conv, "result")
    lines = (home / "args.jsonl").read_text().splitlines()
    start = [json.loads(x) for x in lines if "-p" in json.loads(x)][0]
    assert json.loads(start[start.index("--settings") + 1])["ultracode"] is True
    assert "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=3" in start
    assert "CLAUDE_CODE_SUBAGENT_MODEL=sonnet" in start
    assert not any(a.startswith("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH") for a in start)
    # Claude Code's own answer about whether ultracode took effect
    assert conv.meta["ultracode_state"] == {
        "active": True,
        "available": True,
        "model": "claude-fake",
    }
    assert not any(e.get("type") == "control_response" for e in conv.events)
    # turning it off ends the process so the next message starts without it
    client.post(
        f"/api/conversations/{cid}/settings", json={"ultracode": False}, headers=FORGE
    )
    deadline = time.time() + 5
    while conv.running() and time.time() < deadline:
        time.sleep(0.05)
    assert not conv.running()
    assert "ultracode_state" not in conv.meta
    conv.stop(quiet=True)
