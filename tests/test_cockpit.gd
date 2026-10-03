extends "res://tests/lib/test_case.gd"
## Lane A4 part 5 (Emerson's note 6, "first-person view is broken"), reworked in R3 (Emerson after 014: "the
## first-person model is still bad; I want the whole mech to still be there"). The cockpit camera sits at the
## pilot's seat inside the pod, which saw only the back of the hull around the pilot (a dark tunnel, images/267).
## The fix in A4 part 5 drew just the barrel and the sub-arms, which left a spike and two dark blobs (images/462).
## Now it draws the whole mech except the pod shell around the eye, the parts mechs.json "cockpit_hide" names
## (canopy, tub, side panels), and that shell casts no shadow while the eye is inside.
## Every other camera still draws the whole mech. A layer test is "shares any layer with the camera's mask".

var ground: StaticBody3D
var mech: RigidBody3D
var cam: Camera3D


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 2, 400)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)
	cam = Camera3D.new()
	cam.set_script(load("res://scripts/camera/chase_camera.gd"))
	tree.root.add_child(cam)
	cam.call("follow", mech)
	await physics_frames(30)


func after_each() -> void:
	cam.free()
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


func _meshes() -> Array:
	var out: Array = []
	for node: Node in mech.find_children("*", "MeshInstance3D", true, false):
		if node.get_parent().name != "Combat":
			out.append(node)
	return out


func _drawn_from_cockpit() -> Array:
	cam.set("view", "cockpit")
	cam.call("_process", 0.0)
	var drawn: Array = []
	for mi: MeshInstance3D in _meshes():
		if mi.layers & cam.cull_mask != 0:
			drawn.append(mi)
	return drawn


func test_the_first_person_view_draws_everything_but_the_pod_shell() -> void:
	var hide: Array = (mech.get("def") as Dictionary).get("cockpit_hide", [])
	assert_gt(hide.size(), 0, "the Juggernaut lists the pod shell the cockpit view leaves out")
	var drawn_names: Array = []
	for mi: MeshInstance3D in _drawn_from_cockpit():
		drawn_names.append(str(mi.name))
	for part: String in hide:
		assert_false(drawn_names.has(part), "%s (the pod shell) is not drawn from the pilot's seat" % part)
	for part: String in ["JG2_barrel", "JG2_subarm_L", "JG2_subarm_R", "JG2_flank_L", "JG2_flank_R", "JG2_dart_L", "JG2_coxa_FL", "JG2_receiver"]:
		assert_true(drawn_names.has(part), "%s is drawn from the pilot's seat" % part)
	var all := _meshes().size()
	assert_lt(hide.size(), all / 4, "only a few parts are cut (%d of %d)" % [hide.size(), all])


func test_no_drawn_part_touches_the_eye_or_the_near_plane() -> void:
	var eye_local: Vector3 = load("res://scripts/camera/chase_camera.gd").eye_point(mech)
	var inv := mech.global_transform.affine_inverse()
	var nearest := 1e9
	var who := ""
	for mi: MeshInstance3D in _drawn_from_cockpit():
		if mi.mesh == null or not str(mi.name).begins_with("JG2_"):
			continue
		for i in mi.mesh.get_surface_count():
			for p: Vector3 in mi.mesh.surface_get_arrays(i)[Mesh.ARRAY_VERTEX]:
				var d := ((inv * mi.global_transform) * p).distance_to(eye_local)
				if d < nearest:
					nearest = d
					who = str(mi.name)
	assert_gt(nearest, 0.3, "the nearest drawn vertex is %.2f m from the eye (%s), well past the near plane" % [nearest, who])
	assert_gt(nearest, cam.near * 4.0, "...and several near-plane lengths away, so nothing clips at the eye")


func test_the_pod_shell_casts_no_shadow_while_the_eye_is_inside() -> void:
	var hide: Array = (mech.get("def") as Dictionary).get("cockpit_hide", [])
	var shell: Array = []
	for mi: MeshInstance3D in _meshes():
		if hide.has(str(mi.name)):
			shell.append(mi)
	assert_gt(shell.size(), 0, "the shell parts are in the model")
	for mi: MeshInstance3D in shell:
		assert_eq(mi.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_ON, "%s casts a shadow from outside" % mi.name)
	cam.set("view", "cockpit")
	cam.call("_process", 0.0)
	for mi: MeshInstance3D in shell:
		assert_eq(mi.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_OFF, "%s casts no shadow from the pilot's seat" % mi.name)
	cam.set("view", "third")
	cam.call("_process", 0.0)
	for mi: MeshInstance3D in shell:
		assert_eq(mi.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_ON, "%s casts its shadow again outside" % mi.name)


func test_every_other_view_still_draws_the_whole_mech() -> void:
	cam.set("view", "third")
	cam.call("_process", 0.0)
	for mi: MeshInstance3D in _meshes():
		assert_ne(mi.layers & cam.cull_mask, 0, "%s is drawn in the third-person view" % mi.name)


func test_ground_decals_and_scorch_marks_treat_the_shell_like_the_rest_of_the_mech() -> void:
	var ground_mark := CombatFx.decal(ground, Vector3.ZERO, Vector3.UP, 1.0, true)
	for mi: MeshInstance3D in _meshes():
		assert_eq(mi.layers & ground_mark.cull_mask, 0, "%s is not painted by a ground gouge" % mi.name)
		assert_ne(mi.layers & CombatFx.MECH_LAYERS, 0, "%s takes hull scorch marks" % mi.name)
	ground_mark.free()


func test_the_cockpit_view_still_draws_other_mechs() -> void:
	var unit := LegionMech.build("grauwolf")
	tree.root.add_child(unit)
	await physics_frames(5)
	cam.set("view", "cockpit")
	cam.call("_process", 0.0)
	var meshes := unit.find_children("*", "MeshInstance3D", true, false)
	assert_gt(meshes.size(), 5, "the Legion unit has meshes")
	for mi: MeshInstance3D in meshes:
		assert_ne(mi.layers & cam.cull_mask, 0, "%s of an enemy is drawn from the cockpit" % mi.name)
	unit.free()


## Emerson's note 13 (2026-10-02): in first person the wingmen looked "cooked": every Juggernaut's hull went on
## the cockpit shell layer, not only the pilot's own. A Juggernaut that is not the player is drawn whole.
func test_the_cockpit_view_draws_a_wingman_whole() -> void:
	var wingman := MechBuilder.build("juggernaut_m2")
	wingman.set("is_player", false)
	wingman.position = Vector3(12, 3.0, -10)
	tree.root.add_child(wingman)
	await physics_frames(5)
	cam.set("view", "cockpit")
	cam.call("_process", 0.0)
	var hidden: Array = []
	for mi: Node in wingman.find_children("*", "MeshInstance3D", true, false):
		if mi.get_parent().name != "Combat" and (mi as MeshInstance3D).layers & cam.cull_mask == 0:
			hidden.append(str(mi.name))
	assert_eq(hidden.size(), 0, "no part of the wingman is cut from the cockpit view: %s" % ", ".join(hidden))
	wingman.free()
