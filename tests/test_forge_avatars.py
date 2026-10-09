"""The shared avatar module: motion recipes, Live2D motion files, puppets.

WHY THIS EXISTS
    Emerson asked on 2026-09-24 for more than 8 motions on every avatar model,
    generated when needed, and for a puppet generator, editor and saver. What
    matters here: every built-in recipe is valid; a generated motion3 file has
    the counts Cubism's loader checks; a model only gets curves for parameters
    it has, under the names it uses; and puppets round-trip through the saver.

HOW TO RUN
    /usr/bin/python3 tests/test_forge_avatars.py

    System python on purpose: shared/ is stdlib-only.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

import forge_avatars as fa  # noqa: E402

REAL = Path(__file__).resolve().parents[1] / "shared" / "avatars"


def fake_model(root: Path, name: str, ids: list[str]) -> Path:
    folder = root / "live2d" / name
    folder.mkdir(parents=True)
    (folder / f"{name}.model3.json").write_text(
        json.dumps(
            {
                "Version": 3,
                "FileReferences": {
                    "Moc": "x.moc3",
                    "Motions": {"Idle": [{"File": "a.motion3.json"}]},
                },
            }
        )
    )
    (folder / f"{name}.cdi3.json").write_text(
        json.dumps({"Parameters": [{"Id": i} for i in ids]})
    )
    return folder


def fake_model2(root: Path, name: str, ids: list[str]) -> Path:
    """A Cubism 2 model: .model.json plus a .moc holding PARAM_* names."""
    folder = root / "live2d" / name
    (folder / "moc").mkdir(parents=True)
    (folder / "moc" / f"{name}.moc").write_bytes(
        b"moc\x00" + b"\x00".join(i.encode() for i in ids) + b"\x00"
    )
    (folder / f"{name}.model.json").write_text(
        json.dumps(
            {
                "model": f"moc/{name}.moc",
                "motions": {"idle": [{"file": "mtn/idle_01.mtn"}]},
                "expressions": [{"name": "f01", "file": "exp/f01.exp.json"}],
                "hit_areas": [{"name": "head", "id": "D_REF.HEAD"}],
            }
        )
    )
    return folder


class Cubism2(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_discovery_finds_model_json_and_reads_its_parts(self):
        fake_model2(self.root, "boy", ["PARAM_ANGLE_X", "PARAM_ANGLE_Y"])
        (model,) = fa.list_models(self.root)
        self.assertEqual(model["cubism"], 2)
        self.assertTrue(model["supported"])
        self.assertEqual(model["url"], "avatars/live2d/boy/boy.model.json")
        self.assertEqual(model["motions"], {"idle": ["idle_01"]})
        self.assertEqual(model["expressions"], ["f01"])
        self.assertEqual(model["hit_areas"], ["head"])
        self.assertEqual(model["params"], 2)

    def test_cubism4_is_still_recorded_as_4(self):
        fake_model(self.root, "girl", ["ParamAngleX"])
        (model,) = fa.list_models(self.root)
        self.assertEqual(model["cubism"], 4)

    def test_mtn_has_fps_and_one_value_per_frame_per_param(self):
        recipe = fa.load_recipes(REAL)["nod"]
        text = fa.mtn(recipe, {"PARAM_ANGLE_Y", "PARAM_ANGLE_X"})
        assert text is not None
        lines = text.splitlines()
        self.assertIn("$fps=30", lines)
        rows = [ln for ln in lines if ln.startswith("PARAM_")]
        self.assertTrue(rows)
        frames = int(round(recipe["duration"] * 30)) + 1
        for row in rows:
            name, values = row.split("=", 1)
            self.assertEqual(len(values.split(",")), frames, name)
            [float(v) for v in values.split(",")]
        self.assertIsNone(fa.mtn(recipe, {"PARAM_NOTHING"}))

    def test_ensure_motions_writes_mtn_for_cubism2(self):
        fake_model2(self.root, "boy", ["PARAM_ANGLE_X", "PARAM_ANGLE_Y"])
        shutil.copy(REAL / "motion_recipes.json", self.root / "motion_recipes.json")
        written = fa.ensure_motions("boy", self.root)
        self.assertIn("nod", written)
        self.assertTrue(all(p.endswith(".mtn") for p in written.values()))
        self.assertTrue((self.root / "live2d" / "boy" / written["nod"]).is_file())

    def test_real_cubism2_samples_are_found(self):
        ids = {m["id"]: m for m in fa.list_models(REAL)}
        self.assertEqual(ids["haruto"]["cubism"], 2)
        self.assertTrue(ids["haruto"]["supported"])
        self.assertIn("PARAM_ANGLE_X", fa.model_params(REAL / "live2d" / "haruto"))


class Recipes(unittest.TestCase):
    def test_every_built_in_recipe_is_valid_and_there_are_many(self):
        recipes = fa.load_recipes(REAL)
        self.assertGreaterEqual(len(recipes), 20)
        for name, recipe in recipes.items():
            with self.subTest(name):
                fa.validate_recipe(recipe)

    def test_keys_ease_between_points_and_hold_at_ends(self):
        curve = {"keys": [[0, 0], [1, 10]]}
        self.assertEqual(fa.sample(curve, -1, 1), 0)
        self.assertEqual(fa.sample(curve, 0.5, 1), 5)
        self.assertEqual(fa.sample(curve, 2, 1), 10)
        self.assertLess(fa.sample(curve, 0.25, 1), 2.5)  # eased, not linear

    def test_bell_envelope_silences_a_wave_at_both_ends(self):
        curve = {"wave": {"amp": 10, "freq": 1, "phase": 1.57}, "env": "bell"}
        self.assertAlmostEqual(fa.sample(curve, 0, 2), 0, places=6)
        self.assertAlmostEqual(fa.sample(curve, 2, 2), 0, places=6)

    def test_bad_recipes_are_refused_with_a_reason(self):
        for bad in [
            None,
            {"duration": 1},
            {"duration": 99, "curves": {"ParamAngleX": {"keys": [[0, 0]]}}},
            {"duration": 1, "curves": {"ParamNope": {"keys": [[0, 0]]}}},
            {"duration": 1, "curves": {"ParamAngleX": {"wave": {"freq": 0}}}},
            {"duration": 1, "curves": {"ParamAngleX": {}}},
        ]:
            with self.subTest(bad=bad), self.assertRaises(fa.AvatarError):
                fa.validate_recipe(bad)

    def test_improvise_is_repeatable_and_valid(self):
        a, b = fa.improvise(7, "happy"), fa.improvise(7, "happy")
        self.assertEqual(a, b)
        self.assertNotEqual(a, fa.improvise(8, "happy"))
        self.assertIn("ParamMouthForm", a["curves"])

    def test_custom_recipes_save_under_a_free_name_and_delete(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        shutil.copy(REAL / "motion_recipes.json", root / "motion_recipes.json")
        saved = fa.save_recipe("nod", fa.improvise(1), root)
        self.assertEqual(saved, "nod_2")  # never replaces the built-in
        self.assertEqual(fa.load_recipes(root)["nod_2"]["source"], "custom")
        self.assertTrue(fa.delete_recipe("nod_2", root))


class Motion3(unittest.TestCase):
    def test_counts_match_what_cubism_checks(self):
        recipe = fa.load_recipes(REAL)["laugh"]
        ids = {"ParamAngleY", "ParamAngleZ", "ParamMouthOpenY"}
        doc = fa.motion3(recipe, ids)
        assert doc is not None
        meta = doc["Meta"]
        self.assertEqual(meta["CurveCount"], len(doc["Curves"]))
        segs = points = 0
        for c in doc["Curves"]:
            s = c["Segments"]
            n = (len(s) - 2) // 3
            self.assertEqual(len(s), 2 + 3 * n)
            segs += n
            points += n + 1
            self.assertEqual(s[-2], meta["Duration"])
        self.assertEqual(meta["TotalSegmentCount"], segs)
        self.assertEqual(meta["TotalPointCount"], points)

    def test_only_parameters_the_model_has_under_its_own_names(self):
        recipe = fa.load_recipes(REAL)["nod"]
        doc = fa.motion3(recipe, {"PARAM_ANGLE_Y"})
        assert doc is not None
        self.assertEqual([c["Id"] for c in doc["Curves"]], ["PARAM_ANGLE_Y"])
        self.assertIsNone(fa.motion3(recipe, {"ParamSomethingElse"}))

    def test_values_are_clamped_and_speed_shortens(self):
        recipe = fa.validate_recipe(
            {
                "duration": 2,
                "curves": {"ParamAngleX": {"keys": [[0, 0], [1, 30], [2, 0]]}},
            }
        )
        doc = fa.motion3(recipe, {"ParamAngleX"}, intensity=3, speed=2)
        assert doc is not None
        values = doc["Curves"][0]["Segments"][1::3]
        self.assertLessEqual(max(values), 30)
        self.assertEqual(doc["Meta"]["Duration"], 1)

    def test_ensure_motions_writes_and_prunes(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        shutil.copy(REAL / "motion_recipes.json", root / "motion_recipes.json")
        folder = fake_model(
            root, "dog", ["PARAM_ANGLE_X", "PARAM_ANGLE_Y", "PARAM_EYE_L_OPEN"]
        )
        (folder / "forge_motions").mkdir()
        (folder / "forge_motions" / "gone.motion3.json").write_text("{}")
        written = fa.ensure_motions("dog", root)
        self.assertGreater(len(written), 15)
        self.assertFalse((folder / "forge_motions" / "gone.motion3.json").exists())
        for rel in written.values():
            json.loads((folder / rel).read_text())

    def test_every_real_model_gets_more_than_8_motions_in_total(self):
        recipes = fa.load_recipes(REAL)
        for model in fa.list_models(REAL):
            with self.subTest(model["id"]):
                ids = fa.model_params(REAL / "live2d" / model["id"])
                generated = sum(1 for r in recipes.values() if fa.motion3(r, ids))
                self.assertGreater(model["own_motion_count"] + generated, 8)


class Puppets(unittest.TestCase):
    def test_round_trip_and_list(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        puppet = fa.random_puppet(3, "girl", "cute")
        puppet["name"] = "Tetsu Test"
        slug = fa.save_puppet(puppet, root)
        self.assertEqual(slug, "tetsu_test")
        loaded = fa.load_puppet(slug, root)
        for key in ("hair_style", "colours", "eye_size", "body"):
            self.assertEqual(loaded[key], puppet[key])
        self.assertEqual([p["id"] for p in fa.list_puppets(root)], ["tetsu_test"])
        self.assertTrue(fa.delete_puppet(slug, root))

    def test_bad_puppets_and_names_are_refused(self):
        with self.assertRaises(fa.AvatarError):
            fa.validate_puppet({"hair_style": "mohawk-of-doom"})
        with self.assertRaises(fa.AvatarError):
            fa.validate_puppet({"colours": {"hair": "red; } body {"}})
        self.assertEqual(fa.safe_name("../../etc"), "etc")  # no path escapes
        with self.assertRaises(fa.AvatarError):
            fa.safe_name("../..")
        self.assertEqual(fa.safe_name("Kira Hype!"), "kira_hype")

    def test_jan_reply_parsing(self):
        reply = 'Sure! {"duration": 1, "curves": {"ParamAngleX": {"keys": [[0,0],[1,5]]}}} hope that helps'
        self.assertEqual(fa.recipe_from_text(reply)["duration"], 1)
        with self.assertRaises(fa.AvatarError):
            fa.recipe_from_text("no json here")


if __name__ == "__main__":
    unittest.main()
