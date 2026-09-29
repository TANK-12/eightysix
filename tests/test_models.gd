extends "res://tests/lib/test_case.gd"
## Synced model exports (tools/sync_models.py) load in the game: every mech whose "model" file is
## present imports as a scene; the Juggernaut's has its skeleton, sockets and clips, and its json
## lists parts with colliders and the actuators. A model that is not synced yet is only reported.


func test_present_models_load() -> void:
	for id in Registry.ids("mechs"):
		var entry := Registry.entry("mechs", id)
		var path := str(entry.get("model", ""))
		if path == "":
			continue
		if not ResourceLoader.exists(path):
			print("    (model for %s not synced yet: %s)" % [id, path])
			continue
		var scene := load(path) as PackedScene
		assert_not_null(scene, path + " loads")
		if scene == null:
			continue
		var root := scene.instantiate()
		assert_gt(root.find_children("*", "MeshInstance3D", true, false).size(), 0, path + " has meshes")
		root.free()


func test_juggernaut_export_contract() -> void:
	var entry := Registry.entry("mechs", "juggernaut_m2")
	var path := str(entry.get("model", ""))
	if not ResourceLoader.exists(path):
		print("    (juggernaut export not synced yet)")
		return
	var root := (load(path) as PackedScene).instantiate()
	assert_eq(root.find_children("*", "Skeleton3D", true, false).size(), 1, "one skeleton")
	var sockets := root.find_children("socket_*", "", true, false)
	assert_gt(sockets.size(), 8, "sockets for gun, sub-arms, anchors, cockpit camera, logo")
	var players := root.find_children("*", "AnimationPlayer", true, false)
	assert_eq(players.size(), 1)
	if players.size() == 1:
		assert_true((players[0] as AnimationPlayer).get_animation_list().has("JG2_walk"), "walk clip")
	root.free()
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(str(entry.get("model_data", ""))))
	assert_true(data is Dictionary, "model_data json parses")
	if data is Dictionary:
		var parts: Array = (data as Dictionary).get("parts", [])
		assert_gt(parts.size(), 40, "parts")
		assert_true(parts.all(func(p: Dictionary) -> bool: return p.get("collider") != null), "every part has a collider")
		assert_gt(((data as Dictionary).get("actuators", []) as Array).size(), 10, "actuators")
