"""The Browser backend: address bar, records, Firefox import, the command queue.

A fake Firefox profile is built per test with the real table names and
columns, so no real profile is ever read.
"""

import sqlite3
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agent
import firefox
import store
import web_app

FORGE = {"X-Forge": "1"}
NOW = int(time.time())


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return tmp_path


def make_profile(root, name="abcd.default-release", install=True):
    profile = root / name
    profile.mkdir(parents=True)
    places = sqlite3.connect(profile / "places.sqlite")
    places.executescript("""
        CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT, title TEXT,
          visit_count INTEGER, last_visit_date INTEGER, frecency INTEGER);
        CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER,
          parent INTEGER, title TEXT, dateAdded INTEGER);
        INSERT INTO moz_places VALUES (1, 'https://example.com/', 'Example', 5, 1700000000000000, 100);
        INSERT INTO moz_places VALUES (2, 'https://news.site/a', 'News', 2, 1710000000000000, 50);
        INSERT INTO moz_places VALUES (3, 'place:sort=8', 'Query', 0, NULL, 0);
        INSERT INTO moz_places VALUES (4, 'file:///etc/passwd', 'Local', 3, 1700000000000000, 1);
        INSERT INTO moz_bookmarks VALUES (3, 2, NULL, 1, 'toolbar', 0);
        INSERT INTO moz_bookmarks VALUES (10, 1, 1, 3, 'My example', 5);
        INSERT INTO moz_bookmarks VALUES (11, 1, 3, 3, 'A query', 6);
        """)
    places.commit()
    places.close()
    cookies = sqlite3.connect(profile / "cookies.sqlite")
    cookies.executescript(f"""
        CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, originAttributes TEXT, name TEXT,
          value TEXT, host TEXT, path TEXT, expiry INTEGER, lastAccessed INTEGER,
          creationTime INTEGER, isSecure INTEGER, isHttpOnly INTEGER, inBrowserElement INTEGER,
          sameSite INTEGER, schemeMap INTEGER, isPartitionedAttributeSet INTEGER, updateTime INTEGER);
        INSERT INTO moz_cookies VALUES (1, '', 'sid', 'v1', '.example.com', '/', {(NOW + 3600) * 1000}, 0, 0, 1, 1, 0, 1, 0, 0, 0);
        INSERT INTO moz_cookies VALUES (2, '', 'old', 'v2', '.example.com', '/', {NOW - 10}, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        INSERT INTO moz_cookies VALUES (3, '^userContextId=1', 'box', 'v3', '.example.com', '/', {NOW + 99}, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        """)
    cookies.commit()
    cookies.close()
    lines = ["[Profile0]", "Name=default-release", "IsRelative=1", f"Path={name}", ""]
    if install:
        lines += ["[Install4F96D1932A9F858E]", f"Default={name}", "Locked=1", ""]
    (root / "profiles.ini").write_text("\n".join(lines))
    return profile


@pytest.fixture
def client(data, monkeypatch):
    root = data / "firefox"
    make_profile(root)
    monkeypatch.setattr(firefox, "ROOTS", [root])
    web_app.commands = agent.Queue()
    return TestClient(web_app.app)


# --- the address bar ------------------------------------------------------------


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("https://a.org/x", "https://a.org/x"),
        ("example.com", "https://example.com"),
        ("example.com/path?q=1", "https://example.com/path?q=1"),
        ("localhost:8442", "http://localhost:8442"),
        ("192.168.1.1", "https://192.168.1.1"),
        ("how do tides work", "https://duckduckgo.com/?q=how+do+tides+work"),
        ("python", "https://duckduckgo.com/?q=python"),
        ("", "about:blank"),
        ("file:///home/x/a.md", "file:///home/x/a.md"),
        ("/etc/hosts", "file:///etc/hosts"),
        ("/tmp/a b#1.md", "file:///tmp/a%20b%231.md"),
    ],
)
def test_the_address_bar_tells_addresses_from_searches(typed, expected):
    assert store.resolve(typed) == expected


def test_a_path_in_the_home_folder_opens_as_a_file():
    home = Path.home().as_uri()
    assert store.resolve("~/notes/a.md") == f"{home}/notes/a.md"
    assert store.resolve("~") == home
    assert store.resolve("~bob") == "https://duckduckgo.com/?q=~bob"


def test_the_search_engine_is_a_preference():
    store.save_prefs({"engine": "google", "home": "javascript:alert(1)"})
    assert store.prefs()["engine"] == "google"
    assert store.prefs()["home"] == "about:blank"
    assert store.resolve("cats", store.prefs()["engine"]).startswith(
        "https://www.google.com/"
    )


# --- records ----------------------------------------------------------------------


def test_history_merges_visits_and_ranks_by_them():
    store.record_visit("https://a.org/", "A")
    store.record_visit("https://b.org/", "B", visits=5)
    store.record_visit("https://a.org/", "")
    rows = store.search_history("")
    assert [r["url"] for r in rows] == ["https://b.org/", "https://a.org/"]
    assert rows[1]["visits"] == 2 and rows[1]["title"] == "A"
    assert [r["url"] for r in store.search_history("b.org")] == ["https://b.org/"]


def test_the_session_keeps_web_and_local_file_tabs_only():
    store.save_session(
        [
            {"url": "https://a.org/", "title": "A"},
            {"url": "file:///x"},
            {"url": "javascript:alert(1)"},
            {"url": "file://host/x"},
            {"url": "about:blank"},
        ],
        1,
    )
    assert store.session() == {
        "tabs": [
            {"url": "https://a.org/", "title": "A"},
            {"url": "file:///x", "title": ""},
            {"url": "about:blank", "title": ""},
        ],
        "active": 1,
    }


def test_the_state_carries_the_search_templates_for_offline_use(client):
    state = client.get("/api/state").json()
    assert set(state["search"]) == set(state["engines"])
    assert all("{q}" in template for template in state["search"].values())
    # and the home folder, so ~/x still opens as a file with the server away
    assert state["home_dir"] == str(Path.home())


def test_a_saved_session_keeps_a_local_file_tab_but_never_records_it(client):
    tabs = [{"url": "file:///tmp/a.md", "title": "a.md"}]
    r = client.post("/api/session", json={"tabs": tabs, "active": 0}, headers=FORGE)
    assert r.json()["tabs"] == tabs
    client.post("/api/visit", json={"url": "file:///tmp/a.md"}, headers=FORGE)
    assert store.recent(10) == []
    r = client.post("/api/bookmarks", json={"url": "file:///tmp/a.md"}, headers=FORGE)
    assert r.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"tabs": "https://a.org/", "active": 0},
        {"tabs": 5, "active": "x"},
        {"tabs": None},
        {},
        {"tabs": [None, 3, "s", ["https://a.org/"]], "active": -4},
        {"tabs": [{"url": 7, "title": {"x": 1}}], "active": 10**12},
    ],
)
def test_odd_session_saves_are_quietly_empty_not_a_500(client, payload):
    r = client.post("/api/session", json=payload, headers=FORGE)
    assert r.status_code == 200
    assert r.json() == {"tabs": [], "active": 0}


def test_a_saved_session_keeps_only_url_and_title_and_the_open_tab(client):
    tabs = [
        {"url": "https://a.org/", "title": "A" * 1000, "junk": "x" * 10000},
        {"url": "javascript:alert(1)", "title": "dropped"},
        {"url": "https://b.org/", "title": 42},
        {"url": "https://" + "c" * 9000 + ".org/"},
        {"url": "about:blank"},
    ]
    body = client.post(
        "/api/session", json={"tabs": tabs, "active": 2}, headers=FORGE
    ).json()
    assert body["tabs"] == [
        {"url": "https://a.org/", "title": "A" * 300},
        {"url": "https://b.org/", "title": "42"},
        {"url": "about:blank", "title": ""},
    ]
    assert body["active"] == 1
    many = [{"url": f"https://t{i}.org/"} for i in range(150)]
    body = client.post(
        "/api/session", json={"tabs": many, "active": 140}, headers=FORGE
    ).json()
    assert len(body["tabs"]) == 100 and body["active"] == 99


def test_overlong_addresses_are_not_kept(client):
    huge = "https://a.org/?q=" + "x" * store.MAX_URL
    assert client.post("/api/visit", json={"url": huge}, headers=FORGE).json()["ok"]
    assert client.get("/api/history", headers=FORGE).json()["history"] == []
    r = client.post("/api/bookmarks", json={"url": huge}, headers=FORGE)
    assert r.status_code == 400 and "too long" in r.json()["detail"]


def test_the_history_limit_is_clamped():
    for i in range(520):
        store.record_visit(f"https://h{i}.org/", "", 1, NOW - i)
    assert len(store.recent(-1)) == 1  # SQLite reads -1 as no limit at all
    assert len(store.recent(0)) == 1
    assert len(store.recent(10**9)) == 500


@pytest.mark.parametrize("timeout", ["soon", [1], {"s": 1}])
def test_a_command_with_a_bad_timeout_is_a_400(client, timeout):
    r = client.post(
        "/api/agent/do", json={"op": "tabs", "timeout": timeout}, headers=FORGE
    )
    assert r.status_code == 400


# --- Firefox ----------------------------------------------------------------------


def test_the_install_default_profile_is_found(data):
    root = data / "ff2"
    make_profile(root, "other.default", install=False)
    wanted = make_profile(root / "x", "main.default-release")
    assert firefox.find_profile([root / "x"]) == wanted
    assert firefox.find_profile([root]) == root / "other.default"
    assert firefox.find_profile([data / "nowhere"]) is None


def test_only_web_bookmarks_and_history_come_across(data):
    profile = make_profile(data / "ff3")
    marks = firefox.read_bookmarks(profile)
    assert marks == [
        {
            "url": "https://example.com/",
            "title": "My example",
            "folder": "toolbar",
            "added": 5,
        }
    ]
    urls = [r["url"] for r in firefox.read_history(profile)]
    assert urls == ["https://news.site/a", "https://example.com/"]


def test_cookies_come_across_unexpired_and_in_seconds(data):
    profile = make_profile(data / "ff4")
    rows = firefox.read_cookies(profile)
    assert [r["name"] for r in rows] == ["sid"]
    assert rows[0]["expiry"] == NOW + 3600
    assert rows[0]["secure"] and rows[0]["http_only"] and rows[0]["same_site"] == 1


def test_the_firefox_profile_is_never_written(data):
    profile = make_profile(data / "ff5")
    before = {p.name: p.stat().st_mtime_ns for p in profile.iterdir()}
    firefox.read_bookmarks(profile)
    firefox.read_history(profile)
    firefox.read_cookies(profile)
    assert {p.name: p.stat().st_mtime_ns for p in profile.iterdir()} == before


def test_import_fills_bookmarks_and_history(client):
    counts = client.post("/api/firefox/import", json={}, headers=FORGE).json()
    assert counts == {"bookmarks": 1, "history": 2}
    state = client.get("/api/state").json()
    assert state["bookmarks"][0]["title"] == "My example"
    assert state["top"][0]["url"] == "https://example.com/"


# --- guard ----------------------------------------------------------------------------


def test_private_endpoints_need_the_forge_header(client):
    assert client.get("/api/firefox/cookies").status_code == 403
    assert client.post("/api/agent/do", json={"op": "tabs"}).status_code == 403
    assert (
        client.post("/api/bookmarks", json={"url": "https://a.org/"}).status_code == 403
    )
    cookies = client.get("/api/firefox/cookies", headers=FORGE).json()["cookies"]
    assert [c["name"] for c in cookies] == ["sid"]


def test_only_web_addresses_are_bookmarked(client):
    r = client.post("/api/bookmarks", json={"url": "file:///etc/passwd"}, headers=FORGE)
    assert r.status_code == 400
    r = client.post(
        "/api/bookmarks", json={"url": "https://a.org/", "title": "A"}, headers=FORGE
    )
    assert r.json()["bookmarks"][0]["url"] == "https://a.org/"


def test_restore_tabs_takes_only_a_real_yes_or_no():
    store.save_prefs({"restore_tabs": False})
    store.save_prefs({"restore_tabs": "no"})
    assert store.prefs()["restore_tabs"] is False
    store.save_prefs({"restore_tabs": 1})
    assert store.prefs()["restore_tabs"] is False
    store.save_prefs({"restore_tabs": True})
    assert store.prefs()["restore_tabs"] is True


@pytest.mark.parametrize(
    "url",
    [
        "https://a.org/x y",
        "https://a.org/\x00",
        "https://a.org/\x7f",
        "https://a.org/\u202eexe.txt",
        "https://a.org/\u2066x",
        "https://a.org/\n",
    ],
)
def test_addresses_with_spaces_or_control_characters_are_not_kept(client, url):
    assert not store.web(url)
    r = client.post("/api/bookmarks", json={"url": url}, headers=FORGE)
    assert r.status_code == 400
    client.post(
        "/api/session",
        json={"tabs": [{"url": url}, {"url": "https://a.org/"}], "active": 0},
        headers=FORGE,
    )
    assert [t["url"] for t in store.session()["tabs"]] == ["https://a.org/"]


def test_a_bookmark_title_and_folder_must_be_text(client):
    r = client.post(
        "/api/bookmarks",
        json={"url": "https://a.org/", "title": {"a": 1}, "folder": ["x"]},
        headers=FORGE,
    )
    mark = r.json()["bookmarks"][0]
    assert (mark["title"], mark["folder"]) == ("", "")
    r = client.post(
        "/api/bookmarks",
        json={"url": "https://b.org/", "title": "B", "folder": "Toolbar"},
        headers=FORGE,
    )
    assert {(m["title"], m["folder"]) for m in r.json()["bookmarks"]} >= {
        ("B", "Toolbar")
    }


def test_firefox_opens_the_page_as_a_new_tab(client, monkeypatch):
    ran = []
    monkeypatch.setattr(web_app.shutil, "which", lambda name: "/usr/bin/firefox")
    monkeypatch.setattr(web_app.subprocess, "Popen", lambda cmd, **kw: ran.append(cmd))
    client.post("/api/open-firefox", json={"url": "https://a.org/"}, headers=FORGE)
    client.post("/api/open-firefox", json={"url": "javascript:x"}, headers=FORGE)
    assert ran == [["firefox", "--new-tab", "https://a.org/"], ["firefox"]]


# --- the command queue ----------------------------------------------------------------


def test_a_command_waits_for_the_page_and_gets_its_answer(client):
    answers = {}

    def caller():
        answers["r"] = client.post(
            "/api/agent/do", json={"op": "open", "url": "https://a.org/"}, headers=FORGE
        ).json()

    thread = threading.Thread(target=caller)
    thread.start()
    command = client.get("/api/agent/next?wait=5", headers=FORGE).json()
    assert command["op"] == "open" and command["url"] == "https://a.org/"
    ok = client.post(
        f"/api/agent/result/{command['cid']}",
        json={"ok": True, "tab": 2},
        headers=FORGE,
    )
    assert ok.json() == {"ok": True}
    thread.join(5)
    assert answers["r"] == {"ok": True, "tab": 2}


def test_nothing_to_do_is_a_quiet_204(client):
    assert client.get("/api/agent/next?wait=0", headers=FORGE).status_code == 204


def test_an_unanswered_command_times_out_and_is_withdrawn():
    queue = agent.Queue()
    result = queue.submit({"op": "tabs"}, timeout=0.1)
    assert not result["ok"] and "did not answer" in result["error"]
    assert queue.next(timeout=0) is None
    assert queue.submit({"op": "rm -rf"}, timeout=0.1)["ok"] is False


def test_the_page_and_its_scripts_are_checked_again_before_reuse(client):
    # The hub's WebKit otherwise keeps an old app.js for hours after an update.
    for path in ("/", "/app.js", "/api/state"):
        assert client.get(path).headers["cache-control"] == "no-cache", path
