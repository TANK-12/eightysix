"""The page's API: bad input gets a calm 4xx and never reaches the tuner or
the llama-server command line. No test here starts a real tuning run."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tune  # noqa: E402
import web_app  # noqa: E402
from test_tune import jan  # noqa: E402,F401  (the fake Jan folder fixture)


class FakeTuner:
    made: list[dict] = []

    def __init__(self, model, **kw):
        FakeTuner.made.append({"model": model.id, **kw})
        self.model = model

    def run(self):
        pass


@pytest.fixture
def client(jan, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tune, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app.tune, "Tuner", FakeTuner)
    web_app._run.update(tuner=None, thread=None)
    FakeTuner.made = []
    return TestClient(web_app.app)


def test_a_good_run_reaches_the_tuner_with_checked_knobs(client):
    r = client.post(
        "/api/run",
        json={"model": "test-4b", "repeats": 1, "knobs": {"batch_size": [512]}},
    )
    assert r.status_code == 200, r.text
    assert FakeTuner.made[-1]["knobs"] == {"batch_size": [512]}


@pytest.mark.parametrize(
    "body",
    [
        {"model": "test-4b", "repeats": 0},
        {"model": "test-4b", "repeats": 10**9},
        {"model": "test-4b", "interval": -5},
        {"model": "test-4b", "repeats": "lots"},
        {"model": ""},
        {"model": "x" * 500},
        {"model": "test-4b", "knobs": "batch_size"},
        {"model": "test-4b", "knobs": {"batch_size": 512}},
        {},
    ],
)
def test_wrong_types_and_out_of_range_values_get_422(client, body):
    r = client.post("/api/run", json=body)
    assert r.status_code == 422
    assert not FakeTuner.made


@pytest.mark.parametrize(
    "knobs",
    [
        {"no_such_knob": [1]},
        {"batch_size": ["--rm -rf /"]},
        {"batch_size": [3]},
        {"n_gpu_layers": [True]},
        {"batch_size": [{"a": 1}]},
    ],
)
def test_knob_values_outside_the_models_own_list_get_400(client, knobs):
    r = client.post("/api/run", json={"model": "test-4b", "knobs": knobs})
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)
    assert not FakeTuner.made


def test_unknown_and_path_like_model_ids_get_404(client):
    for model in ("nope", "../../etc/passwd", ".hidden", "ünï📦"):
        assert client.post("/api/run", json={"model": model}).status_code == 404
        assert client.post(f"/api/apply/{model}").status_code in (400, 404, 405)
    assert client.get("/api/knobs", params={"model": "../x"}).status_code == 404


def test_status_never_reads_outside_the_results_folder(client, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "secret.json").write_text('{"status": "leaked"}')
    r = client.get("/api/status", params={"model": "../secret"})
    assert r.status_code == 200
    assert "leaked" not in r.text


def test_a_second_run_while_one_is_going_gets_409(client, monkeypatch):
    class Alive:
        def is_alive(self):
            return True

    web_app._run.update(tuner=FakeTuner(tune.find_model("test-4b")), thread=Alive())
    r = client.post("/api/run", json={"model": "test-4b"})
    assert r.status_code == 409
    web_app._run.update(tuner=None, thread=None)


def test_a_knob_named_with_no_values_means_all_its_values(client):
    r = client.post("/api/run", json={"model": "test-4b", "knobs": {"batch_size": []}})
    assert r.status_code == 200, r.text
    assert FakeTuner.made[-1]["knobs"] == {"batch_size": []}
