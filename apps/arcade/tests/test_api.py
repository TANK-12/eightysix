"""The Arcade backend: status, the Jan proxy's input checks, the Hearsay save."""

import pytest
from fastapi.testclient import TestClient

import web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "SAVE_PATH", tmp_path / "data" / "hearsay_save.json")
    monkeypatch.setattr(web_app, "JAN_BASE", "http://127.0.0.1:9/v1")
    return TestClient(web_app.app)


def test_the_page_and_status_answer_with_jan_off(client):
    assert client.get("/").status_code == 200
    body = client.get("/api/status").json()
    assert body["backend"] is True and body["jan"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"messages": []},
        {"messages": "hello"},
        {"messages": [{"role": "user"}]},
        {"messages": [{"role": "robot", "content": "hi"}]},
        {"messages": [{"role": "user", "content": 5}]},
        {"messages": [{"role": "user", "content": "hi"}] * 41},
        {"messages": [{"role": "user", "content": "hi"}], "temperature": "warm"},
        {"messages": [{"role": "user", "content": "hi"}], "temperature": True},
        {"messages": [{"role": "user", "content": "hi"}], "temperature": 9},
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": "lots"},
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 0},
    ],
)
def test_bad_chat_input_is_a_plain_400(client, payload):
    r = client.post("/api/jan/chat", json=payload)
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


def test_a_huge_conversation_is_refused_before_jan(client):
    big = [{"role": "user", "content": "ä" * 61_000}]
    assert client.post("/api/jan/chat", json={"messages": big}).status_code == 413


def test_good_chat_input_with_jan_off_is_a_503_not_a_crash(client):
    msgs = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "héllo ✨"},
    ]
    r = client.post("/api/jan/chat", json={"messages": msgs, "max_tokens": 50})
    assert r.status_code == 503
    assert "Jan unreachable" in r.json()["detail"]


def test_save_round_trip_keeps_unicode(client):
    case = {"culprit": "rooke", "notes": [{"text": "Ilse — “unsure” ✨"}], "turns": 3}
    assert client.post("/api/hearsay/save", json=case).json()["saved"] is True
    assert client.get("/api/hearsay/save").json()["save"] == case
    assert client.delete("/api/hearsay/save").json()["cleared"] is True
    assert client.get("/api/hearsay/save").json()["save"] is None


def test_a_huge_save_is_refused_and_the_old_one_kept(client):
    client.post("/api/hearsay/save", json={"turns": 1})
    r = client.post("/api/hearsay/save", json={"junk": "x" * 1_100_000})
    assert r.status_code == 413
    assert client.get("/api/hearsay/save").json()["save"] == {"turns": 1}
    leftovers = list(web_app.SAVE_PATH.parent.glob("*.tmp"))
    assert leftovers == []


def test_saves_at_the_same_moment_all_land_whole(client):
    from concurrent.futures import ThreadPoolExecutor

    def one(n):
        return client.post("/api/hearsay/save", json={"turns": n, "pad": "x" * 20_000})

    with ThreadPoolExecutor(8) as pool:
        codes = [r.status_code for r in pool.map(one, range(24))]
    assert codes == [200] * 24
    assert client.get("/api/hearsay/save").json()["save"]["turns"] in range(24)
    assert list(web_app.SAVE_PATH.parent.glob("*.tmp")) == []


def test_a_lone_surrogate_is_refused_not_saved(client):
    body = '{"notes": "\\ud800 broken"}'  # JSON's escape for a lone surrogate
    r = client.post(
        "/api/hearsay/save", content=body, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400
    assert client.get("/api/hearsay/save").status_code == 200


def test_a_broken_save_file_loads_as_no_save(client):
    web_app.SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    web_app.SAVE_PATH.write_text("{not json")
    assert client.get("/api/hearsay/save").json() == {"save": None}


def test_a_save_must_be_an_object(client):
    assert client.post("/api/hearsay/save", json=[1, 2]).status_code == 422
