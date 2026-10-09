"""U1 sweep (2026-10-08): the API refuses requests that used to delete data,
brick a project or answer with a 500.

Every test points the projects folder at a temp dir, so nothing touches the
real ~/PulseForgeData.
"""

import json

import pytest
from fastapi.testclient import TestClient

import web_app
from pulseforge import config
from pulseforge import project as projmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(projmod, "PROJECTS_DIR", tmp_path / "projects")
    # settings tests must never write Emerson's real settings.json
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(web_app.state, "settings", config.load_settings())
    return TestClient(web_app.app)


def raw(client, method, url, text):
    return client.request(
        method, url, content=text, headers={"Content-Type": "application/json"}
    )


def test_a_dot_dot_slug_never_deletes_the_data_folder(client, tmp_path):
    keep = tmp_path / "keep.txt"
    keep.write_text("mine")
    client.post("/api/projects", json={"name": "Real one"})
    for path in ("/api/projects/%2E%2E", "/api/projects/%2E", "/api/projects/.."):
        r = client.delete(path)
        assert r.status_code in (400, 404, 405), (path, r.status_code)
    assert keep.read_text() == "mine"
    assert (tmp_path / "projects" / "real-one" / "project.json").exists()


def test_delete_only_removes_a_folder_inside_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(projmod, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    (tmp_path / "other").mkdir()
    for slug in ("..", ".", "", "../other"):
        projmod.delete(slug)
    assert (tmp_path / "projects").is_dir() and (tmp_path / "other").is_dir()


@pytest.mark.parametrize("name", ["..", ".", "...."])
def test_a_dots_only_name_gets_a_folder_of_its_own(client, tmp_path, name):
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200
    slug = r.json()["slug"]
    assert slug.startswith("project-")
    assert (tmp_path / "projects" / slug / "project.json").exists()
    assert not (tmp_path / "project.json").exists()


@pytest.mark.parametrize(
    "url,text",
    [
        ("/api/batch", '{"folder": NaN}'),
        ("/api/projects", '{"name": Infinity}'),
        ("/api/settings", '{"values": {"x": -Infinity}}'),
    ],
)
def test_nan_and_infinity_are_a_calm_400(client, url, text):
    r = raw(client, "POST", url, text)
    assert r.status_code == 400
    assert "not a number" in r.json()["detail"]


def test_nan_in_a_patch_does_not_brick_the_project(client, tmp_path):
    slug = client.post("/api/projects", json={"name": "Keep"}).json()["slug"]
    for text in ('{"song_gap": NaN}', '{"params": {"speed": Infinity}}'):
        assert raw(client, "PUT", f"/api/projects/{slug}", text).status_code == 400
    assert client.get(f"/api/projects/{slug}").status_code == 200
    saved = (tmp_path / "projects" / slug / "project.json").read_text()
    json.loads(saved, parse_constant=lambda c: pytest.fail(f"{c} was saved"))


def test_bad_json_still_gets_the_usual_422(client):
    assert raw(client, "POST", "/api/projects", '{"name": ').status_code == 422
    assert raw(client, "POST", "/api/projects", '{"name": 5}').status_code == 422


def test_an_over_long_name_is_refused_and_a_long_one_works(client):
    assert client.post("/api/projects", json={"name": "a" * 5000}).status_code == 422
    r = client.post("/api/projects", json={"name": "b" * 300})
    assert r.status_code == 200
    assert len(r.json()["slug"]) <= projmod.SLUG_MAX
    assert r.json()["name"] == "b" * 300


def test_a_copy_never_lands_on_top_of_another_project(client):
    a = client.post("/api/projects", json={"name": "Alpha"}).json()["slug"]
    b = client.post("/api/projects", json={"name": "Beta"}).json()["slug"]
    client.put(f"/api/projects/{b}", json={"title_text": "Beta's own title"})
    r = client.post(f"/api/projects/{a}/duplicate", json={"name": "Beta"})
    assert r.status_code == 200
    assert r.json()["slug"] not in (a, b)
    beta = client.get(f"/api/projects/{b}").json()["data"]
    assert beta["title_text"] == "Beta's own title"
    # the default "<name> copy" twice gives two copies, not one overwritten
    first = client.post(f"/api/projects/{a}/duplicate", json={}).json()["slug"]
    second = client.post(f"/api/projects/{a}/duplicate", json={}).json()["slug"]
    assert first != second


def test_uploads_and_other_bodies_pass_the_guard(client):
    slug = client.post("/api/projects", json={"name": "Up"}).json()["slug"]
    r = client.post(
        f"/api/projects/{slug}/asset",
        files={"file": ("x.txt", b"not an image", "text/plain")},
    )
    assert r.status_code < 500
    r = client.put(f"/api/projects/{slug}", json={"title_text": "日本語 🎵"})
    assert r.status_code == 200 and r.json()["data"]["title_text"] == "日本語 🎵"


@pytest.mark.parametrize(
    "url,method,text",
    [
        ("/api/settings", "POST", '{"values": {"x": 1e999}}'),
        ("/api/projects/{slug}", "PUT", '{"song_gap": 1e999}'),
        ("/api/projects/{slug}", "PUT", '{"params": {"speed": -1e400}}'),
    ],
)
def test_a_number_too_big_for_a_float_is_a_calm_400(client, url, method, text):
    slug = client.post("/api/projects", json={"name": "Big"}).json()["slug"]
    r = raw(client, method, url.format(slug=slug), text)
    assert r.status_code == 400 and "not a number" in r.json()["detail"]
    assert client.get(f"/api/projects/{slug}").status_code == 200
    assert client.get("/api/state").status_code == 200


def test_the_guard_reads_any_spelling_of_the_json_content_type(client):
    slug = client.post("/api/projects", json={"name": "Case"}).json()["slug"]
    r = client.put(
        f"/api/projects/{slug}",
        content='{"params": {"speed": Infinity}}',
        headers={"Content-Type": "Application/JSON"},
    )
    assert r.status_code == 400
    assert client.get(f"/api/projects/{slug}").status_code == 200


def _pfproj(tmp_path, manifest_text):
    import zipfile

    from pulseforge import projectfile

    f = tmp_path / f"in{projectfile.SUFFIX}"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr(projectfile.MANIFEST, manifest_text)
    return f


def _import(client, f):
    with open(f, "rb") as fh:
        return client.post(
            "/api/projects/import", files={"file": (f.name, fh, "application/zip")}
        )


def test_an_import_never_overwrites_a_project_of_the_same_name(client, tmp_path):
    a = client.post("/api/projects", json={"name": "Alpha"}).json()["slug"]
    client.put(f"/api/projects/{a}", json={"title_text": "Alpha own title"})
    f = _pfproj(
        tmp_path,
        json.dumps({"slug": "alpha", "data": {"name": "Alpha", "title_text": "x"}}),
    )
    r = _import(client, f)
    assert r.status_code == 200 and r.json()["slug"] != a
    assert (
        client.get(f"/api/projects/{a}").json()["data"]["title_text"]
        == "Alpha own title"
    )


@pytest.mark.parametrize(
    "manifest",
    [
        '{"slug": "g", "data": {"name": "Gamma", "song_gap": NaN}}',
        '{"slug": "g", "data": {"name": "Gamma", "song_gap": 1e999}}',
        '{"slug": "g", "data": [1, 2]}',
        "[1, 2]",
        "not json",
    ],
)
def test_a_damaged_project_file_is_a_400_and_makes_nothing(client, tmp_path, manifest):
    before = projmod.list_projects()
    assert _import(client, _pfproj(tmp_path, manifest)).status_code == 400
    assert projmod.list_projects() == before


def test_two_names_with_one_slug_stay_two_projects(client):
    a = client.post("/api/projects", json={"name": "Song!"}).json()
    b = client.post("/api/projects", json={"name": "Song?"}).json()
    assert a["slug"] != b["slug"]
    assert client.get(f"/api/projects/{a['slug']}").json()["data"]["name"] == "Song!"
    # the very same name still reopens its project
    assert (
        client.post("/api/projects", json={"name": "Song!"}).json()["slug"] == a["slug"]
    )
    # names with no ascii letters made in the same second
    x = client.post("/api/projects", json={"name": "夜の雨"}).json()["slug"]
    y = client.post("/api/projects", json={"name": "朝"}).json()["slug"]
    assert x != y


def test_a_rename_has_the_same_length_cap_as_create(client):
    slug = client.post("/api/projects", json={"name": "Short"}).json()["slug"]
    assert (
        client.put(f"/api/projects/{slug}", json={"name": "n" * 5000}).status_code
        == 422
    )
    assert (
        client.put(f"/api/projects/{slug}", json={"name": "n" * 300}).status_code == 200
    )


def test_a_settings_file_holding_infinity_still_loads(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    f.write_text('{"crf": 20, "x": -Infinity, "y": NaN}')
    monkeypatch.setattr(config, "SETTINGS_PATH", f)
    got = config.load_settings()
    assert got["crf"] == 20 and "x" not in got and "y" not in got
