"""The fifth critic's findings (docs/2026-10-08-critic-5.md), one test or
more each, written to fail on the code before the fix."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web_app
from conftest import prof
from exolab import registry


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(web_app.app)


def _put(client: TestClient, name: str, p: dict) -> tuple[int, str]:
    r = client.put(f"/api/profiles/{name}", json=p)
    return r.status_code, r.text


SWAP_J1 = {"mechanisms": {"girdle_tracking": {"joints.0.actuator": "free_bearing"}}}


# ----- C5-M1: the knobs every model's parts read, not only the open one's -----


def test_model_lists_part_knobs_of_every_model(client) -> None:
    p = prof(knobs={"parts": {"exo_full/J1": {"power": 2}}}, overrides=SWAP_J1)
    got = client.post("/api/model", json={"model": "exo_lite", "profile": p}).json()
    every = got["part_knobs_of"]
    assert set(every) == set(registry.Registry().ids("models"))
    # Both suits share the girdle tracker, so the swap made on the light
    # suit leaves the full suit's J1 a bearing too: weight only.
    assert every["exo_full"]["J1"] == ["weight"]
    assert every["exo_lite"] == got["part_knobs"]


# ----- C5-M2: every test's own rules are checked on save -----


@pytest.mark.parametrize(
    "overrides, says",
    [
        ({"tests": {"close_fit": {"params.fps": 20}}}, "frames"),
        (
            {"tests": {"close_fit": {"params.warn_mm": 8, "params.reach_mm": 5}}},
            "under reach_mm",
        ),
        (
            {
                "tests": {
                    "shoulder_motions": {
                        f"params.motions.{i}": "throw" for i in range(6)
                    }
                },
                "motions": {"side_raise": {"keys.1.t": 0.01}},
            },
            "apart",
        ),
    ],
)
def test_close_fit_rules_are_refused_on_save(client, overrides, says) -> None:
    code, text = _put(client, "fit-rules", prof(overrides=overrides))
    assert code == 400 and says in text, text


def test_a_close_fit_edit_inside_its_rules_saves(client) -> None:
    edits = {"tests": {"close_fit": {"params.fps": 12, "params.warn_mm": 4}}}
    code, text = _put(client, "fit-ok", prof(overrides=edits))
    assert code == 200, text


# ----- C5-L1: a range wider than the usual one reads at most 100% -----


def test_wider_range_reads_at_most_all(client) -> None:
    rom = {"plane_deg.0": -180, "plane_deg.8": 180}
    rom.update({f"max_elevation_deg.{i}": 180 for i in range(9)})
    r = client.post(
        "/api/run",
        json={
            "model": "exo_full",
            "test": "shoulder_rom",
            "profile": prof(overrides={"human": {"rom": rom}}),
        },
    )
    assert r.status_code == 200, r.text
    card = next(c for c in r.json()["cards"] if c["title"] == "Range tested")
    assert card["value"] == "100%" and card["level"] == "pass"
    assert "more than the usual" in card["text"]


# ----- C5-L4: a motorless drive's part knobs never offer power -----


def test_part_knobs_of_any_motorless_kind_drop_power() -> None:
    reg = registry.Registry()
    reg.knobs["motorless"] = [*reg.knobs["motorless"], "cable"]
    cable = {
        "overrides": {"models": {"exo_full": {"shoulder.mechanism": "soft_cable"}}}
    }
    got = reg.knobs_of_parts("exo_full", cable)
    assert got["J1"] and "power" not in got["J1"]
    _clean, errors = reg.check_knobs(
        {"parts": {"exo_full/J1": {k: 2 for k in got["J1"]}}}, cable["overrides"]
    )
    assert errors == []
