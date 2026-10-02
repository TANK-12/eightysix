extends "res://tests/lib/test_case.gd"
## Lane A4 part 5 (Emerson's note 6, "first-person view is broken"): the cockpit camera sits inside the
## pod, where it saw only the back of the hull around the pilot (a dark tunnel, images/267). It now draws
## just the parts mechs.json "cockpit_show" names (the barrel and the sub-arms); every other camera
## still draws the whole mech. A layer test is "shares any layer with the camera's mask".

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


func test_the_first_person_view_draws_only_the_gun_and_the_sub_arms() -> void:
	var show: Array = (mech.get("def") as Dictionary).get("cockpit_show", [])
	assert_gt(show.size(), 0, "the Juggernaut lists what the cockpit view draws")
	cam.set("view", "cockpit")
	cam.call("_process", 0.0)
	var drawn: Array = []
	for mi: MeshInstance3D in _meshes():
		if mi.layers & cam.cull_mask != 0:
			drawn.append(str(mi.name))
	drawn.sort()
	var want := show.duplicate()
	want.sort()
	assert_eq(drawn, want, "only the listed parts reach the cockpit camera, not the canopy, tub, hull or legs")


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
