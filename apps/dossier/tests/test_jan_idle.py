"""Releasing Jan's models when nothing is using them.

Two idle models held about 9.8 GB while research was paused. Unloading them
through Jan's router freed 13.6 GB, and the router loads a model again on the
next request, so releasing idle ones costs only a reload.
"""

import httpx

import janidle
import llm


def test_the_router_is_found_from_its_command_line_and_environment():
    cmd = [
        "/x/llama-server",
        "--models-preset",
        "/x/router.preset.ini",
        "--models-max",
        "2",
        "--host",
        "127.0.0.1",
        "--port",
        "53041",
        "--no-ui",
    ]
    env = {"LLAMA_API_KEY": "k", "HOME": "/h"}
    assert janidle.parse_router(cmd, env) == ("http://127.0.0.1:53041", "k")


def test_a_model_server_is_not_mistaken_for_the_router():
    cmd = ["/x/llama-server", "--alias", "Qwen3_5-4B", "--port", "55593"]
    assert janidle.parse_router(cmd, {}) is None


def test_a_model_server_is_named_by_its_alias():
    cmd = ["/x/llama-server", "--host", "127.0.0.1", "--alias", "Qwen3_5-4B"]
    assert janidle.parse_model(cmd) == "Qwen3_5-4B"
    assert janidle.parse_model(["/x/llama-server", "--models-preset", "p"]) is None
    assert janidle.parse_model(["/usr/bin/python3", "--alias", "x"]) is None


def test_a_model_left_alone_long_enough_is_released():
    t = janidle.IdleTracker(idle_seconds=300)
    assert t.observe(0, {"4B": 100}, busy=False) == []
    assert t.observe(200, {"4B": 100}, busy=False) == []
    assert t.observe(300, {"4B": 100}, busy=False) == ["4B"]


def test_a_model_someone_else_is_using_is_kept():
    t = janidle.IdleTracker(idle_seconds=300)
    t.observe(0, {"4B": 100}, busy=False)
    t.observe(250, {"4B": 180}, busy=False)
    assert t.observe(500, {"4B": 180}, busy=False) == []
    assert t.observe(550, {"4B": 180}, busy=False) == ["4B"]


def test_nothing_is_released_while_dossier_has_a_request_running():
    t = janidle.IdleTracker(idle_seconds=300)
    t.observe(0, {"4B": 1}, busy=False)
    assert t.observe(900, {"4B": 1}, busy=True) == []
    assert t.observe(1199, {"4B": 1}, busy=False) == []
    assert t.observe(1200, {"4B": 1}, busy=False) == ["4B"]


def test_a_model_loaded_again_starts_a_fresh_wait():
    t = janidle.IdleTracker(idle_seconds=300)
    t.observe(0, {"4B": 5}, busy=False)
    assert t.observe(300, {"4B": 5}, busy=False) == ["4B"]
    assert t.observe(310, {}, busy=False) == []
    assert t.observe(320, {"4B": 0}, busy=False) == []
    assert t.observe(619, {"4B": 0}, busy=False) == []
    assert t.observe(620, {"4B": 0}, busy=False) == ["4B"]


def test_each_model_waits_on_its_own_clock():
    t = janidle.IdleTracker(idle_seconds=300)
    t.observe(0, {"2B": 1, "4B": 1}, busy=False)
    assert t.observe(200, {"2B": 1, "4B": 9}, busy=False) == []
    assert t.observe(300, {"2B": 1, "4B": 9}, busy=False) == ["2B"]


def test_dossier_counts_its_own_requests_in_flight(monkeypatch):
    seen = []

    def handler(request):
        seen.append(llm.in_flight())
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    real = httpx.Client
    monkeypatch.setattr(
        llm.httpx,
        "Client",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(llm, "resolve", lambda tier: "test-model")
    assert llm.chat("reason", [{"role": "user", "content": "x"}]) == "ok"
    assert seen == [1]
    assert llm.in_flight() == 0


def test_a_model_whose_slot_is_processing_counts_as_busy(monkeypatch):
    class R:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self._body

    monkeypatch.setattr(
        janidle.httpx,
        "get",
        lambda url, timeout: R(
            [{"id": 0, "is_processing": False}, {"id": 1, "is_processing": True}]
        ),
    )
    assert janidle.slots_busy(37223)
    monkeypatch.setattr(
        janidle.httpx,
        "get",
        lambda url, timeout: R([{"id": 0, "is_processing": False}]),
    )
    assert not janidle.slots_busy(37223)


def test_a_model_server_that_cannot_be_asked_is_left_alone(monkeypatch):
    def boom(url, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(janidle.httpx, "get", boom)
    assert janidle.slots_busy(37223)


def test_model_ports_come_from_each_servers_command_line(monkeypatch):
    argv = ["llama-server", "--alias", "Qwen3_5-4B-IQ4_XS", "--port", "37223"]
    monkeypatch.setattr(janidle, "_servers", lambda: iter([(1, argv)]))
    assert janidle.model_ports() == {"Qwen3_5-4B-IQ4_XS": 37223}
