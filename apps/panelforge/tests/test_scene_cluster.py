"""scene clustering: identities from synthetic features."""

import numpy as np

from panelforge.scene import cluster


def _blobs(rng, centers, per, spread):
    feats, truth = [], []
    for t, c in enumerate(centers):
        for _ in range(per):
            feats.append(c + rng.normal(0, spread, size=c.shape))
            truth.append(f"char{t}")
    return np.array(feats), truth


def test_separated_identities_are_recovered_across_seeds():
    """Sweep: 40 random worlds of 2-7 characters, embeddings like CCIP."""
    worst = 1.0
    for seed in range(40):
        rng = np.random.default_rng(seed)
        k = int(rng.integers(2, 8))
        centers = [rng.normal(0, 1, 64) for _ in range(k)]
        feats, truth = _blobs(rng, centers, int(rng.integers(2, 6)), 0.15)
        dist = cluster.cosine_matrix(feats)
        labels = cluster.average_linkage(dist, threshold=0.5)
        worst = min(worst, cluster.purity(labels, truth))
        assert len(set(labels)) == k, (seed, len(set(labels)), k)
    assert worst == 1.0


def test_cannot_link_keeps_same_panel_people_apart():
    # Twins: identical features, but drawn together in one panel.
    feats = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.01]])
    dist = cluster.cosine_matrix(feats)
    assert len(set(cluster.average_linkage(dist, 0.5))) == 1
    labels = cluster.average_linkage(dist, 0.5, cannot_link=[[0, 1]])
    assert labels[0] != labels[1]
    assert labels[2] in (labels[0], labels[1])


def test_blend_normalises_thresholds_and_skips_missing_features():
    a = np.array([[0.0, 0.1], [0.1, 0.0]])  # threshold 0.2 -> 0.5
    b = np.array([[0.0, np.nan], [np.nan, 0.0]])
    out = cluster.blend([(a, 0.2, 1.0), (b, 1.0, 3.0)])
    assert abs(out[0, 1] - 0.5) < 1e-9
    c = np.array([[0.0, 2.0], [2.0, 0.0]])  # threshold 1 -> 2
    out = cluster.blend([(a, 0.2, 1.0), (c, 1.0, 1.0)])
    assert abs(out[0, 1] - 1.25) < 1e-9


def test_colour_histograms_group_by_hair_colour():
    rng = np.random.default_rng(3)
    hists, truth = [], []
    for t, peak in enumerate((2, 9, 15)):
        for _ in range(4):
            h = rng.random(18) * 0.05
            h[peak] += 1.0
            hists.append(h / h.sum())
            truth.append(t)
    d = cluster.chi2_matrix(np.array(hists))
    labels = cluster.average_linkage(d, threshold=0.3)
    assert cluster.purity(labels, [str(t) for t in truth]) == 1.0
    assert len(set(labels)) == 3


def test_recurring_splits_cast_from_extras():
    labels = [0, 0, 0, 1, 2, 2, 3, 3]
    panels = ["p1", "p2", "p3", "p2", "p4", "p9", "p5", "p5"]
    scenes = ["s1", "s1", "s1", "s1", "s1", "s2", "s1", "s1"]
    assert cluster.recurring(labels, panels, scenes) == {0, 2}


def test_nearest_centroid_respects_threshold():
    d = np.array([[0.3, 0.9], [1.5, 1.2], [0.8, 0.2]])
    assert cluster.nearest_centroid(d, 1.0) == [0, None, 1]


def test_quantile_linkage_joins_one_character_drawn_three_ways():
    """Front, profile and shadow of one person: two views match well, the
    third only matches one of them. Average linkage splits them; the quantile
    keeps them together."""
    import numpy as np

    from panelforge.scene import cluster

    d = np.array(
        [
            [0.0, 0.4, 0.5, 3.0],
            [0.4, 0.0, 1.9, 3.1],
            [0.5, 1.9, 0.0, 3.2],
            [3.0, 3.1, 3.2, 0.0],
        ]
    )
    assert len(set(cluster.average_linkage(d, 1.0))) == 3
    labels = cluster.quantile_linkage(d, 1.0, (), 0.15)
    assert labels[0] == labels[1] == labels[2] and labels[3] != labels[0]


def test_quantile_linkage_keeps_cannot_link_apart():
    import numpy as np

    from panelforge.scene import cluster

    d = np.full((3, 3), 0.1)
    np.fill_diagonal(d, 0.0)
    labels = cluster.quantile_linkage(d, 1.0, [[0, 1]], 0.2)
    assert labels[0] != labels[1]  # two people in one panel are two people


def test_only_person_like_boxes_become_cast():
    from panelforge.scene import cast

    person = {"score": 0.8, "area_frac": 0.3, "face": [1, 2, 3, 4], "text_overlap": 0.0}
    assert cast.is_person(person)
    assert not cast.is_person({**person, "score": 0.2})  # unsure detection
    assert not cast.is_person({**person, "area_frac": 0.001})  # a detail
    assert not cast.is_person({**person, "text_overlap": 0.9})  # a caption box
    assert not cast.is_person({**person, "face": None, "score": 0.4})  # faceless
    assert cast.is_person({**person, "face": None, "score": 0.9, "area_frac": 0.2})


def test_rejected_appearances_get_no_cast_entry(tmp_path):
    import numpy as np

    from panelforge.scene import cast

    app = [
        {
            "panel_id": "p1",
            "index": 0,
            "ccip": None,
            "hair": np.zeros(22),
            "body": np.zeros(22),
            "score": 0.9,
            "area_frac": 0.3,
            "face": [0, 0, 5, 5],
            "text_overlap": 0.0,
            "cutout": "missing.png",
        },
        {
            "panel_id": "p2",
            "index": 0,
            "ccip": None,
            "hair": np.zeros(22),
            "body": np.zeros(22),
            "score": 0.9,
            "area_frac": 0.3,
            "face": [0, 0, 5, 5],
            "text_overlap": 0.95,
            "cutout": "missing.png",
        },  # a caption box
    ]
    labels, cast_labels = cast.group(app, {"p1": "s1", "p2": "s1"})
    assert labels[1] == cast.REJECTED
    doc, label_to_id = cast.build(app, labels, cast_labels, None, tmp_path, tmp_path)
    ids = [e["id"] for e in doc["cast"]] + [e["id"] for e in doc["extras"]]
    assert len(ids) == 1 and cast.REJECTED not in label_to_id


def _person(pid, index, ccip, face, hair=None):
    import numpy as np

    return {
        "panel_id": pid,
        "index": index,
        "ccip": np.array(ccip, np.float32),
        "ccip_face": None,
        "hair": np.array(hair if hair is not None else [1.0] + [0.0] * 21),
        "body": np.zeros(22),
        "score": 0.9,
        "area_frac": 0.3,
        "face": [0, 0, 5, 5] if face else None,
        "text_overlap": 0.0,
        "cutout": "missing.png",
    }


def test_faceless_appearances_never_found_a_character(monkeypatch):
    """Identities come from faces. A faceless crop joins the character it
    is close to, and one that matches nobody stays unplaced: no cast, no
    extra, instead of becoming a "character" made of hands and guns."""
    import numpy as np

    from panelforge.scene import cast, detectors

    # 4 faced pictures of A, 3 faced of B, then three faceless crops: one
    # like A, one like B but drawn in a panel where B already stands, one junk
    vec = {
        "A": [1.0, 0.0, 0.0],
        "B": [0.0, 1.0, 0.0],
        "junk": [0.0, 0.0, 1.0],
    }
    app = [
        _person("p1", 0, vec["A"], True),
        _person("p2", 0, vec["A"], True),
        _person("p3", 0, vec["A"], True),
        _person("p4", 0, vec["A"], True),
        _person("p5", 0, vec["B"], True),
        _person("p6", 0, vec["B"], True),
        _person("p7", 0, vec["B"], True),
        _person("p8", 0, vec["A"], False),  # back view of A
        _person("p7", 1, vec["B"], False),  # looks like B, but B is in p7
        _person("p9", 0, vec["junk"], False),  # a gloved hand
    ]

    def fake_diff(feats):
        f = np.asarray(feats, np.float64)
        f = f / np.linalg.norm(f, axis=1, keepdims=True)
        return 1.0 - f @ f.T

    monkeypatch.setattr(detectors, "ccip_diff", fake_diff)
    scene_of = {f"p{i}": "s1" for i in range(1, 10)}
    labels, cast_labels = cast.group(app, scene_of)
    assert labels[7] == labels[0], labels  # the back view of A joined A
    assert labels[8] == cast.UNPLACED, labels  # cannot be B: B is in that panel
    assert labels[9] == cast.UNPLACED, labels  # the hand founded nothing
    assert len({l for l in labels if l >= 0}) == 2  # exactly A and B
    assert cast.UNPLACED not in cast_labels


def test_a_chapter_with_no_faces_is_clustered_on_bodies(monkeypatch):
    import numpy as np

    from panelforge.scene import cast, detectors

    monkeypatch.setattr(
        detectors,
        "ccip_diff",
        lambda f: 1.0 - (np.asarray(f, np.float64) @ np.asarray(f, np.float64).T),
    )
    app = [
        _person("p1", 0, [1.0, 0.0], False),
        _person("p2", 0, [1.0, 0.0], False),
        _person("p3", 0, [1.0, 0.0], False),
    ]
    labels, cast_labels = cast.group(app, {"p1": "s1", "p2": "s1", "p3": "s2"})
    assert labels == [0, 0, 0]
    # three panels in one chapter is not "often enough" to be cast
    assert cast_labels == set()
    more = app + [_person(f"p{i}", 0, [1.0, 0.0], False) for i in range(4, 8)]
    labels, cast_labels = cast.group(more, {})
    # seven panels but not one face: never cast (armour, a gun, machinery)
    assert len(set(labels)) == 1 and cast_labels == set()
    faced = app + [_person(f"p{i}", 0, [1.0, 0.0], True) for i in range(4, 8)]
    labels, cast_labels = cast.group(faced, {})
    assert cast_labels == {0}  # seven panels, four with a face: cast
    # two chapters with faces in each: cast as well
    two = [{**a, "face": [0, 0, 5, 5]} for a in app] + [
        {**_person(f"p{i}", 0, [1.0, 0.0], True), "chapter": "0002"}
        for i in range(1, 4)
    ]
    labels, cast_labels = cast.group(two, {})
    assert cast_labels == {0}


def _fake_chapter(tmp_path, n_people=4):
    """A chapter dir with cutout files and a scene.json of `n_people` crops,
    one per panel, all placed in cast c01 by the automatic grouping."""
    import numpy as np
    import cv2

    from panelforge import store

    series = tmp_path / "series" / "s"
    cdir = series / "chapters" / "0001"
    (cdir / "work").mkdir(parents=True)
    panels = {}
    app = []
    for i in range(n_people):
        pid = f"p{i + 1:04d}"
        cut = f"work/cut_{i}.png"
        cv2.imwrite(str(cdir / cut), np.full((8, 8, 4), 255, np.uint8))
        panels[pid] = {
            "characters": [
                {
                    "cast_id": "c01",
                    "extra_id": None,
                    "placement": "cast",
                    "box": [0, 0, 8, 8],
                    "face": [1, 1, 2, 2],
                    "cutout": cut,
                    "area_frac": 0.3,
                    "score": 0.9,
                }
            ]
        }
        app.append(
            {
                "panel_id": pid,
                "index": 0,
                "cutout": cut,
                "face": [1, 1, 2, 2],
                "area_frac": 0.3,
            }
        )
    store.write(cdir / "scene.json", {"schema": 1, "panels": panels, "speakers": {}})
    doc = {
        "schema": 1,
        "cast": [
            {
                "id": "c01",
                "name": "Rook",
                "auto_name": "character 1",
                "color": "#fff",
                "samples": [],
                "embedding": None,
                "voice": {"kokoro": "am_adam"},
                "rig": None,
                "model3d": None,
                "appearances": [
                    {"panel_id": a["panel_id"], "index": 0, "chapter": "0001"}
                    for a in app
                ],
                "panels": [a["panel_id"] for a in app],
            }
        ],
        "narrator": {"voice": None},
        "extras": [],
        "backgrounds": [],
        "props": [],
        "assignments": {},
    }
    store.write(series / "cast.json", doc)
    return series, cdir, doc, app


def test_assignments_split_drop_and_survive_a_rerun(tmp_path):
    """Emerson moves two crops out of c01 into a new character and drops a
    third as not a person. The ledger keeps that when the grouping runs
    again and puts everything back into one cluster."""
    from panelforge.scene import cast

    series, cdir, doc, app = _fake_chapter(tmp_path)
    doc["assignments"] = {
        "0001/p0003:0": "c02",
        "0001/p0004:0": "c02",
        "0001/p0002:0": "none",
    }
    cast.apply_assignments(doc, "0001", app, cdir, series)
    ids = {c["id"]: c for c in doc["cast"]}
    assert [a["panel_id"] for a in ids["c01"]["appearances"]] == ["p0001"]
    assert sorted(a["panel_id"] for a in ids["c02"]["appearances"]) == [
        "p0003",
        "p0004",
    ]
    assert ids["c02"]["samples"] and (series / ids["c02"]["samples"][0]).exists()
    assert ids["c01"]["voice"] == {"kokoro": "am_adam"}  # untouched

    # the automatic grouping runs again: one cluster of all four, label 0
    labels = [0, 0, 0, 0]
    for a in app:
        a.update({"ccip": None, "hair": None, "body": None, "score": 0.9})
    rebuilt, _ = cast.build(app, labels, {0}, doc, series, cdir)
    ids = {c["id"]: c for c in rebuilt["cast"]}
    assert set(ids) == {"c01", "c02"}, ids.keys()
    assert [a["panel_id"] for a in ids["c01"]["appearances"]] == ["p0001"]
    assert sorted(a["panel_id"] for a in ids["c02"]["appearances"]) == [
        "p0003",
        "p0004",
    ]
    assert ids["c01"]["name"] == "Rook" and ids["c01"]["voice"]["kokoro"] == "am_adam"
    assert rebuilt["assignments"] == doc["assignments"]

    # and scene.json ids follow the document
    from panelforge import store

    sc = store.read(cdir / "scene.json")
    cast.sync_scene_ids(sc, rebuilt, "0001")
    got = {
        pid: (sp["characters"][0]["cast_id"], sp["characters"][0]["placement"])
        for pid, sp in sc["panels"].items()
    }
    assert got == {
        "p0001": ("c01", "cast"),
        "p0002": (None, "rejected"),
        "p0003": ("c02", "cast"),
        "p0004": ("c02", "cast"),
    }, got


def test_cast_api_assign_and_unsorted(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import jobs, paths

    importlib.reload(paths)
    importlib.reload(jobs)
    from fastapi.testclient import TestClient

    import web_app

    series, cdir, doc, app = _fake_chapter(tmp_path)
    c = TestClient(web_app.app)
    r = c.put(
        "/api/series/s/cast",
        json={
            "assign": {
                "0001/p0003:0": "new",
                "0001/p0004:0": "new",
                "0001/p0002:0": "none",
            }
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    ids = {x["id"]: x for x in out["cast"]}
    assert set(ids) == {"c01", "c02"} and out["assignments"]["0001/p0003:0"] == "c02"
    un = c.get("/api/series/s/cast/unsorted", params={"chapter": "0001"}).json()
    assert [x["key"] for x in un["items"]] == ["0001/p0002:0"]
    assert un["items"][0]["placement"] == "rejected"
    assert un["items"][0]["image"].startswith("/data/series/s/chapters/0001/")
    # merging c02 back into c01 writes the ledger too, so it survives a rerun
    r = c.put("/api/series/s/cast", json={"merge": [["c01", "c02"]]}).json()
    assert [x["id"] for x in r["cast"]] == ["c01"]
    assert r["assignments"]["0001/p0003:0"] == "c01"
    assert len(r["cast"][0]["appearances"]) == 3


def test_a_cluster_glued_by_a_few_lookalike_pairs_is_split():
    """Two people, four faced pictures each, drawn far apart except for one
    pair that looks alike (same uniform). The low quantile glues them into one
    cluster; the median check cuts them apart again."""
    import numpy as np

    from panelforge.scene import cast

    n = 8
    d = np.full((n, n), 1.6)
    for i in range(n):
        for j in range(n):
            if (i < 4) == (j < 4):
                d[i, j] = 0.3
    d[3, 4] = d[4, 3] = 0.2  # the one look-alike pair across the two people
    np.fill_diagonal(d, 0.0)
    glued = [0] * n
    faced = list(range(n))
    labels = cast._split_glued(glued, d, faced)
    assert len(set(labels[:4])) == 1 and len(set(labels[4:])) == 1
    assert labels[0] != labels[4], labels
    # one real character drawn eight ways stays whole
    whole = np.full((n, n), 0.6)
    np.fill_diagonal(whole, 0.0)
    assert len(set(cast._split_glued(glued, whole, faced))) == 1


def test_a_second_chapter_keeps_the_first_chapters_names_and_voices(tmp_path):
    """Re-analysing with a new chapter in the mix must not lose what Emerson
    set on the cast: the cluster that still holds chapter 1's pictures of a
    character keeps that character's id, name and voice."""
    from panelforge.scene import cast

    series, cdir, doc, app = _fake_chapter(tmp_path)
    doc["cast"][0]["voice"] = {"kokoro": "af_alloy"}
    doc["cast"][0]["name"] = "Rook"
    # chapter 2 adds three more pictures of the same person
    cdir2 = series / "chapters" / "0002"
    (cdir2 / "work").mkdir(parents=True)
    more = []
    for i in range(3):
        more.append(
            {
                "chapter": "0002",
                "chapter_dir": cdir2,
                "panel_id": f"p{i + 1:04d}",
                "index": 0,
                "cutout": None,
                "face": [1, 1, 2, 2],
                "area_frac": 0.3,
            }
        )
    for a in app:
        a.update(
            {
                "chapter": "0001",
                "chapter_dir": cdir,
                "ccip": None,
                "hair": None,
                "body": None,
                "score": 0.9,
            }
        )
    everyone = app + more
    labels = [0] * len(everyone)
    rebuilt, _ = cast.build(everyone, labels, {0}, doc, series, cdir2)
    assert [c["id"] for c in rebuilt["cast"]] == ["c01"]
    assert rebuilt["cast"][0]["name"] == "Rook"
    assert rebuilt["cast"][0]["voice"] == {"kokoro": "af_alloy"}
    assert len(rebuilt["cast"][0]["appearances"]) == 7
