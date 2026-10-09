"""Bad bodies and odd query values answer 4xx, never 500 (U1 sweep)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import web_app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(web_app.app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "path, body",
    [
        ("/api/priority", '{"nice": 1e999, "background": [], "protected": []}'),
        ("/api/priority", '{"nice": NaN, "background": [], "protected": []}'),
        ("/api/fps", '{"max_fps": NaN}'),
        ("/api/fps", '{"battery_fps": -1e999}'),
        ("/api/autoswitch", '{"enabled": Infinity, "battery": "a", "ac": "b"}'),
        ("/api/autostart/x.desktop", '{"enabled": NaN}'),
    ],
)
def test_infinite_or_nan_bodies_are_a_422_not_a_500(client, path, body):
    r = client.post(path, content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422
    # the bad value is not echoed back (it cannot be written as JSON)
    assert "inf" not in r.text.lower() and "nan" not in r.text.lower()
    assert r.json()["detail"][0]["loc"][0] == "body"


def test_process_list_limit_is_kept_between_1_and_100(client, monkeypatch):
    seen = []
    monkeypatch.setattr(
        web_app.status, "top_processes", lambda limit: seen.append(limit) or []
    )
    for limit in (-1, 0, 5, 100000):
        assert client.get(f"/api/processes?limit={limit}").status_code == 200
    assert seen == [1, 1, 5, 100]
