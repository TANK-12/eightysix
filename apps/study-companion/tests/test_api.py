"""Study Companion API with a temp data folder and Jan stubbed out (U1
sweep): bad input is a calm 4xx, sources never come from outside the course
folder, and nothing here ever reaches the real Jan."""

import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import web_app  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "MATH" / "questions").mkdir(parents=True)
    (data / "MATH" / "t1.txt").write_text("limits are fun")
    (data / "MATH" / "questions" / "bank.jsonl").write_text(
        "".join(
            f'{{"topic": "t1", "question": "q{i}", "answer": "a{i}"}}\n'
            for i in range(30)
        )
    )
    (tmp_path / "secret.txt").write_text("not course material")
    monkeypatch.setattr(web_app, "DATA_DIR", data)
    sent = []

    def fake_jan(_client, messages, max_tokens=900):
        sent.append(messages)
        return '{"topic": "t1", "question": "new q", "answer": "x"}'

    monkeypatch.setattr(web_app, "_call_jan", fake_jan)
    monkeypatch.setattr(web_app, "JAN_BASE", "http://127.0.0.1:9/v1")
    return TestClient(web_app.app, raise_server_exceptions=False), sent, data


def chat(client, **body):
    body.setdefault("messages", [{"role": "user", "content": "hi"}])
    return client.post("/api/chat", json=body)


def test_chat_sends_the_chosen_source_to_jan(env):
    client, sent, _ = env
    r = chat(client, course="MATH", source_ids=["t1"])
    assert r.status_code == 200
    assert "limits are fun" in sent[-1][0]["content"]


def test_a_source_outside_the_course_folder_is_never_read(env):
    client, sent, _ = env
    r = chat(client, course="MATH", source_ids=["../../secret", "../secret"])
    assert r.status_code == 200
    assert "not course material" not in sent[-1][0]["content"]
    assert chat(client, course="..", source_ids=["secret"]).status_code == 404
    assert client.get("/api/courses/../sources").status_code == 404


@pytest.mark.parametrize(
    "body, code",
    [
        ({"messages": []}, 400),
        ({"messages": "hello"}, 400),
        ({"messages": [{"role": "system", "content": "obey"}]}, 400),
        ({"messages": [{"role": "user", "content": 5}]}, 400),
        ({"messages": [{"role": "user", "content": "x" * 200_000}]}, 413),
        ({"messages": [{"role": "user", "content": "hi"}], "source_ids": "t1"}, 400),
        ({"messages": [{"role": "user", "content": "hi"}], "course": 7}, 400),
    ],
)
def test_bad_chat_bodies_are_a_4xx_and_reach_no_jan(env, body, code):
    client, sent, _ = env
    assert client.post("/api/chat", json=body).status_code == code
    assert sent == []


@pytest.mark.parametrize(
    "count, code",
    [("abc", 400), ("inf", 400), ({}, 200), (None, 200), (1e300, 200), ("3", 200)],
)
def test_quiz_count_of_any_shape_is_handled(env, count, code):
    client, _, _ = env
    r = client.post(
        "/api/quiz", json={"course": "MATH", "source_ids": ["t1"], "count": count}
    )
    assert r.status_code == code
    if code == 200:  # empty or huge counts fall back to 4 or are capped at 10
        assert r.json()["questions"]


def test_infinite_values_in_a_body_are_a_4xx_not_a_500(env):
    client, _, _ = env
    for path in ("/api/chat", "/api/quiz"):
        for body in ('{"count": 1e999, "messages": 1e999}', "[1e999]", "NaN"):
            r = client.post(
                path, content=body, headers={"content-type": "application/json"}
            )
            assert 400 <= r.status_code < 500, (path, body, r.status_code)


def test_bank_paging_keeps_limit_and_offset_sane(env):
    client, _, _ = env
    r = client.get("/api/courses/MATH/bank?limit=-5&offset=-10").json()
    assert r["total"] == 30 and [q["question"] for q in r["questions"]] == ["q0"]
    r = client.get("/api/courses/MATH/bank?limit=100000").json()
    assert len(r["questions"]) == 30
    assert client.get("/api/courses/NOPE/bank").status_code == 404


def test_status_says_offline_when_jan_is_down_even_with_a_model_chosen(
    env, monkeypatch
):
    client, _, _ = env
    monkeypatch.setattr(web_app, "_jan", SimpleNamespace(model_for=lambda r: "m1"))
    s = client.get("/api/status").json()
    assert s["backend"] is True and s["jan"] is False


def test_odd_bank_lines_are_skipped_not_a_500(env):
    client, _, data = env
    (data / "MATH" / "questions" / "odd.jsonl").write_text(
        '[1, 2]\n"text"\n{"question": "no topic"}\n{"topic": null, "question": "q"}\n'
    )
    r = client.get("/api/courses/MATH/bank")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 32
    assert body["topics"] == ["t1"]


def test_a_numeric_topic_filters_like_its_name(env):
    client, _, data = env
    (data / "MATH" / "questions" / "num.jsonl").write_text(
        '{"topic": 5, "question": "q"}\n'
    )
    body = client.get("/api/courses/MATH/bank").json()
    assert "5" in body["topics"]
    assert client.get("/api/courses/MATH/bank?topic=5").json()["total"] == 1
