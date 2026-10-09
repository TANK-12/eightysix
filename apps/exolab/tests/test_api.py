"""The HTTP API and the page wiring, through FastAPI's test client."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from conftest import APP
from fastapi.testclient import TestClient

import web_app
from exolab import benches

JS = APP / "static" / "js"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(web_app.app)


def test_registry_lists_every_model(client) -> None:
    r = client.get("/api/registry").json()
    models = r["items"]["models"]
    assert {
        "exo_full",
        "exo_lite",
        "spider_mech",
        "biped_mech",
        "cyber_arm",
        "cyber_leg",
    } <= set(models)
    assert set(r["bench_kinds"]) == set(benches.KINDS)
    assert r["profiles"][0] == "baseline"
    assert "fields" in r["knobs"]


def test_ready_model_carries_suit_body_and_rest_pose(client) -> None:
    r = client.get("/api/model/exo_full").json()
    assert r["status"] == "ready"
    assert r["suit"]["total_kg"] > 5 and r["suit"]["joints"][0]["key"] == "J1"
    assert r["rest"]["in_rom"] is True
    for url in (
        r["character"]["url"],
        r["suit_asset"]["glb"],
        r["suit_asset"]["sidecar"],
    ):
        assert url and client.head(url).status_code == 200, url


def test_planned_model_has_no_suit(client) -> None:
    r = client.get("/api/model/spider_mech").json()
    assert r["status"] == "planned" and "suit" not in r and r["about"]


def test_inline_profile_reaches_the_part_table(client) -> None:
    base = client.get("/api/model/exo_lite").json()
    heavy = client.post(
        "/api/model",
        json={
            "model": "exo_lite",
            "profile": {"knobs": {"materials": {"al_7075_t6": {"weight": 2}}}},
        },
    ).json()
    assert (
        heavy["suit"]["total_kg"] > base["suit"]["total_kg"] and heavy["warnings"] == []
    )
    swap = {
        "overrides": {
            "mechanisms": {"girdle_tracking": {"joints.0.actuator": "harmonic_m"}}
        }
    }
    r = client.post("/api/model", json={"model": "exo_lite", "profile": swap}).json()
    assert r["suit"]["joints"][0]["actuator"] == "harmonic_m"
    assert base["suit"]["joints"][0]["actuator"] == "qdd_planetary"


def test_run_is_cached(client) -> None:
    body = {"model": "exo_lite", "test": "shoulder_hold"}
    a = client.post("/api/run", json=body)
    b = client.post("/api/run", json=body)
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert a.json()["profile"] == "baseline" and a.json()["test_name"]


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/run", {"model": "nope", "test": "shoulder_hold"}),
        ("/api/run", {"model": "exo_lite", "test": "nope"}),
        ("/api/pose", {"model": "nope"}),
        ("/api/model", {"model": "nope"}),
        ("/api/derive", {"model": "nope"}),
    ],
)
def test_unknown_ids_are_404(client, path, body) -> None:
    assert client.post(path, json=body).status_code == 404


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/run", {"model": "spider_mech", "test": "shoulder_rom"}),
        ("/api/pose", {"model": "cyber_arm"}),
        ("/api/derive", {"model": "biped_mech"}),
        (
            "/api/run",
            {"model": "exo_lite", "test": "shoulder_hold", "profile": "../etc"},
        ),
    ],
)
def test_planned_models_and_bad_names_are_400(client, path, body) -> None:
    r = client.post(path, json=body)
    assert r.status_code == 400, r.text


def test_bad_override_comes_back_as_a_warning(client) -> None:
    bad = {"overrides": {"materials": {"al_7075_t6": {"nope": 1}}}}
    r = client.post(
        "/api/run", json={"model": "exo_lite", "test": "shoulder_hold", "profile": bad}
    )
    assert r.status_code == 200
    assert any("no such field" in w for w in r.json()["warnings"])


def test_pose_gives_loads_for_one_pose(client) -> None:
    r = client.post(
        "/api/pose",
        json={"model": "exo_full", "plane": 90, "elev": 90, "payload_kg": 5},
    ).json()
    assert r["level"] in benches.LEVELS and r["in_rom"] is True and r["warnings"] == []
    light = client.post(
        "/api/pose", json={"model": "exo_full", "plane": 90, "elev": 90}
    ).json()
    assert r["hand_sag_mm"] > light["hand_sag_mm"]


def test_profiles_save_copy_and_guard(client) -> None:
    name = "api round trip"
    body = {"knobs": {"actuators": {"harmonic_m": {"power": 2}}}, "notes": "test"}
    r = client.put(f"/api/profiles/{name}", json=body)
    assert r.status_code == 200 and name in r.json()["profiles"]
    assert client.get(f"/api/profiles/{name}").json()["knobs"] == {
        "actuators": {"harmonic_m": {"power": 2.0}}
    }
    assert client.put("/api/profiles/baseline", json={}).status_code == 400
    assert (
        client.put("/api/profiles/api bad", json={"overrides": {"x": {}}}).status_code
        == 400
    )
    assert (
        client.post(f"/api/profiles/{name}/copy", json={"to": "api copy"}).status_code
        == 200
    )
    assert (
        client.post(f"/api/profiles/{name}/copy", json={"to": "api copy"}).status_code
        == 409
    )
    assert (
        client.post(f"/api/profiles/{name}/copy", json={"to": "../x"}).status_code
        == 400
    )
    run = client.post(
        "/api/run", json={"model": "exo_full", "test": "shoulder_hold", "profile": name}
    )
    assert run.json()["profile"] == name


def test_derive_get_and_post_agree(client) -> None:
    g = client.get("/api/derive/exo_full").json()
    p = client.post("/api/derive", json={"model": "exo_full"}).json()
    assert g["strength"] == p["strength"] and p["warnings"] == []


def test_report_lands_in_the_report_folder(client) -> None:
    r = client.post(
        "/api/report", json={"model": "exo_lite", "test": "shoulder_hold"}
    ).json()
    path = Path(r["path"])
    assert path.is_file() and path.is_relative_to(os.environ["EXOLAB_REPORT_DIR"])
    assert re.search(r"date: \d{4}-\d{2}-\d{2}", path.read_text())


def test_page_and_its_files_are_served(client) -> None:
    for url in [
        "/",
        "/app.css",
        "/game.html",
        "/shared/forge.css",
        *(f"/js/{f.name}" for f in JS.glob("*.js")),
    ]:
        assert client.get(url).status_code == 200, url


def test_page_modules_import_only_what_exists() -> None:
    """Every name a page module imports from another is exported there; a
    missing one stops the whole page from loading."""
    imp = re.compile(r'^import\s*\{([^}]*)\}\s*from\s*"(\./[^"]+)"', re.M)
    exp = re.compile(
        r"^export\s+(?:async\s+)?(?:function\*?|const|let|class)\s+([\w$]+)", re.M
    )
    lists = re.compile(r"^export\s*\{([^}]*)\}", re.M)
    for f in sorted(JS.glob("*.js")):
        for names, rel in imp.findall(f.read_text()):
            target = (f.parent / rel).resolve()
            assert target.is_file(), f"{f.name} imports missing {rel}"
            src = target.read_text()
            have = set(exp.findall(src))
            for group in lists.findall(src):
                have |= {n.split(" as ")[-1].strip() for n in group.split(",")}
            for n in names.split(","):
                n = n.split(" as ")[0].strip()
                assert (
                    not n or n in have
                ), f"{f.name} imports {n} from {rel}, which does not export it"


def test_import_map_covers_every_bare_import(client) -> None:
    html = client.get("/").text
    found = re.search(r'<script type="importmap">(.*?)</script>', html, re.S)
    assert found
    imports = json.loads(found.group(1))["imports"]
    assert "three" in imports
    bare = set()
    for f in JS.glob("*.js"):
        bare |= set(re.findall(r'^import[^"]*"([^./][^"]*)"', f.read_text(), re.M))
    assert "three" in bare
    for spec in sorted(bare):
        if spec in imports:
            url = imports[spec]
        else:
            prefix = max(
                (p for p in imports if p.endswith("/") and spec.startswith(p)), key=len
            )
            url = imports[prefix] + spec[len(prefix) :]
        assert client.get(url).status_code == 200, f"{spec} -> {url}"
