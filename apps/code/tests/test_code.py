"""The wrapper: settings seeding, URL building, the guard, and the real editor."""

from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import web_app  # noqa: E402

H = {"X-Forge": "1"}


def test_defaults_extension(tmp_path):
    p = web_app.write_defaults_extension(tmp_path)
    data = json.loads(p.read_text())
    defaults = data["contributes"]["configurationDefaults"]
    assert defaults["workbench.colorTheme"] == "Default Dark Modern"
    assert defaults["security.workspace.trust.enabled"] is False


def test_editor_url_folder_and_file():
    u = web_app.editor_url("http://127.0.0.1:5000", "tok en", "/home/x/proj")
    q = parse_qs(urlsplit(u).query)
    assert q["tkn"] == ["tok en"] and q["folder"] == ["/home/x/proj"]
    assert "payload" not in q
    u = web_app.editor_url("http://127.0.0.1:5000", "t", "/home/x", "/home/x/a b.py")
    payload = json.loads(parse_qs(urlsplit(u).query)["payload"][0])
    assert payload == [["openFile", "vscode-remote://127.0.0.1:5000/home/x/a%20b.py"]]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    web_app.DATA_DIR = tmp_path_factory.mktemp("code-data")
    with TestClient(web_app.app) as c:
        for _ in range(150):
            if c.get("/api/session", headers=H).json()["ready"]:
                break
            time.sleep(0.1)
        yield c


def test_api_needs_header(client):
    assert client.get("/api/session").status_code == 403
    assert client.get("/api/url").status_code == 403


def test_real_editor_needs_token(client):
    s = client.get("/api/session", headers=H).json()
    assert s["ready"], s
    # A right token is answered with a cookie and a redirect; keep the cookie.
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    ok = opener.open(f"{s['base']}/?tkn={s['token']}")
    assert ok.status == 200 and b"workbench" in ok.read()
    for bad in ("", "?tkn=wrong"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.build_opener().open(f"{s['base']}/{bad}")
        assert e.value.code in (401, 403)


def test_stop_ends_node(tmp_path):
    ed = web_app.Editor()
    old = web_app.DATA_DIR
    web_app.DATA_DIR = tmp_path
    try:
        ed.start()
        for _ in range(150):
            if ed.ready():
                break
            time.sleep(0.1)
        assert ed.ready()
        pid = ed.proc.pid if ed.proc else 0
        ed.stop()
        time.sleep(0.3)
        assert (
            not Path(f"/proc/{pid}").exists()
            or "zombie" in Path(f"/proc/{pid}/status").read_text()
        )
        assert all(str(tmp_path) not in c for c in cmdlines())
    finally:
        web_app.DATA_DIR = old


def cmdlines() -> list[str]:
    out = []
    for p in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            out.append(p.read_bytes().replace(b"\0", b" ").decode(errors="replace"))
        except OSError:
            pass
    return out


def test_url_route(client, tmp_path):
    (tmp_path / "sub").mkdir()
    f = tmp_path / "sub" / "main.py"
    f.write_text("print('hi')\n")
    r = client.get("/api/url", params={"path": str(f)}, headers=H).json()
    assert r["folder"] == str(tmp_path / "sub") and r["file"] == str(f)
    r = client.get(
        "/api/url", params={"path": str(f), "root": str(tmp_path)}, headers=H
    ).json()
    assert r["folder"] == str(tmp_path)
    r = client.get(
        "/api/url", params={"path": str(f), "root": "/usr"}, headers=H
    ).json()
    assert r["folder"] == str(tmp_path / "sub")
    assert (
        client.get("/api/url", params={"path": "/nope/x"}, headers=H).status_code == 404
    )


def test_token_file_private(client):
    assert (web_app.DATA_DIR / "connection-token").stat().st_mode & 0o077 == 0


def test_static_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "Code" in r.text


def test_token_is_kept_across_starts(tmp_path):
    first = web_app.keep_token(tmp_path)
    assert len(first) >= 24
    assert web_app.keep_token(tmp_path) == first
    assert (tmp_path / "connection-token").stat().st_mode & 0o077 == 0
    (tmp_path / "connection-token").write_text("short")
    assert web_app.keep_token(tmp_path) not in ("short", first)


def test_port_is_kept_while_free(tmp_path):
    first = web_app.keep_port(tmp_path)
    assert web_app.keep_port(tmp_path) == first
    import socket

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", first))
        taken.listen()
        other = web_app.keep_port(tmp_path)
    assert other != first
    assert (tmp_path / "editor-port").read_text() == str(other)


def test_missing_browser_entries_are_hidden(tmp_path):
    ext = tmp_path / "extensions"
    for name, browser, present in (
        ("gone", "./dist/browser/main", False),
        ("there", "./dist/browser/main", True),
        ("web-only", "./dist/browser/main", False),
    ):
        (ext / name / "dist" / "browser").mkdir(parents=True)
        data = {"name": name, "browser": browser}
        if name != "web-only":
            data["main"] = "./dist/main"
        if present:
            (ext / name / "dist" / "browser" / "main.js").write_text("")
        (ext / name / "package.json").write_text(json.dumps(data))
    assert web_app.hide_missing_browser_entries(tmp_path) == ["gone"]
    assert "browser" not in json.loads((ext / "gone" / "package.json").read_text())
    assert "browser" in json.loads((ext / "there" / "package.json").read_text())
    # An extension with no server half keeps its entry, missing or not.
    assert "browser" in json.loads((ext / "web-only" / "package.json").read_text())
    assert web_app.hide_missing_browser_entries(tmp_path) == []


def test_server_turns_off_restricted_mode(tmp_path):
    cmd = web_app.server_command(tmp_path, 9999, tmp_path / "t", tmp_path)
    assert "--disable-workspace-trust" in cmd
    assert cmd[cmd.index("--port") + 1] == "9999"


def test_chat_panel_starts_closed():
    assert (
        web_app.DEFAULT_SETTINGS["workbench.secondarySideBar.defaultVisibility"]
        == "hidden"
    )


def test_url_refuses_paths_the_os_cannot_look_up(client):
    # A NUL byte in path or root used to be a 500 with a stack trace.
    for params in ({"path": "/tmp/a\0b"}, {"path": "/tmp", "root": "/x\0"}):
        r = client.get("/api/url", params=params, headers=H)
        if "root" in params:
            assert r.status_code == 200  # root only matters for a file
        else:
            assert r.status_code == 400 and "can't be opened" in r.json()["detail"]
    f = "/etc/hostname"
    r = client.get("/api/url", params={"path": f, "root": "/x\0"}, headers=H)
    assert r.status_code == 400
    r = client.get("/api/url", params={"path": "/tmp/" + "b" * 5000}, headers=H)
    assert r.status_code in (400, 404)
