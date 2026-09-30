extends "res://tests/lib/test_case.gd"
## The asset kit (lane B3): every data/kit.json entry builds, collides as its entry says, and the
## breakable pieces really come apart.


func test_every_entry_builds_with_a_mesh() -> void:
	for id in Kit.ids():
		if str(Kit.entry(id).get("builder", "")) == "crater":
			continue
		var node := Kit.build(id, 3)
		var mi := node.get_node_or_null("Mesh") as MeshInstance3D
		assert_not_null(mi, id + " has a mesh")
		if mi != null:
			assert_gt(mi.mesh.get_surface_count(), 0, id + " mesh has surfaces")
			assert_gt(mi.mesh.get_aabb().size.length(), 0.05, id + " mesh has size")
		var wants := str(Kit.entry(id).get("collision", "none"))
		if wants == "none":
			assert_false(node is StaticBody3D, id + " does not collide")
		else:
			assert_true(node is StaticBody3D, id + " collides")
			assert_gt(node.get_child_count(), 1, id + " has collision shapes")
			var grapple := bool(Kit.entry(id).get("grapple", false))
			assert_eq((node as StaticBody3D).collision_layer & Kit.LAYER_GRAPPLE != 0, grapple, id + " grapple layer")
		node.free()


func test_round_is_57mm_and_about_66cm_long() -> void:
	var node := Kit.build("round_57mm")
	var aabb := (node.get_node("Mesh") as MeshInstance3D).mesh.get_aabb()
	assert_almost_eq(aabb.size.y, 0.664, 0.002, "length")
	assert_almost_eq(aabb.size.x, 0.092, 0.003, "rim diameter")
	node.free()


func test_damage_removes_wall_pieces() -> void:
	var whole := Kit.build("wall_4m", 1, {"damage": 0.0})
	var broken := Kit.build("wall_4m", 1, {"damage": 0.8})
	var n_whole: int = whole.get_meta("pieces").size()
	var n_broken: int = broken.get_meta("pieces").size()
	assert_eq(n_whole, 16, "a 4 m by 3.2 m wall is 4 by 4 blocks")
	assert_lt(n_broken, n_whole, "damage takes blocks away")
	var window := Kit.build("wall_window_4m", 1)
	assert_lt(window.get_meta("pieces").size(), n_whole, "the window is a hole")
	for n in [whole, broken, window]:
		n.free()


func test_break_apart_makes_debris() -> void:
	var holder := Node3D.new()
	tree.root.add_child(holder)
	var wall := Kit.build("wall_4m", 2)
	holder.add_child(wall)
	var n: int = wall.get_meta("pieces").size()
	var debris := Kit.break_apart(wall, Vector3(0, 1, 3), 2000.0)
	assert_eq(debris.size(), n, "one body per piece")
	for b in debris:
		assert_true(b is RigidBody3D)
		assert_gt(b.mass, 5.0)
	await physics_frames(10)
	assert_false(is_instance_valid(wall), "the standing wall is gone")
	holder.free()


func test_mast_and_outcrop_have_anchors() -> void:
	var mast := Kit.build("mast")
	var anchors: Array = mast.get_meta("anchors")
	assert_gt(anchors.size(), 0)
	assert_almost_eq((anchors[0] as Vector3).y, 30.0, 0.01, "mast anchor at the top")
	var rock := Kit.build("outcrop", 5, {"size": 12.0})
	assert_gt(rock.get_meta("anchors").size(), 0, "outcrops anchor on top")
	mast.free()
	rock.free()
