extends "res://tests/lib/test_case.gd"
## Resonance blade (lane A7): holding Blade with a Legion unit at the tips fills the meter over tune_s,
## holds it tuned, then drifts; the release strikes the unit with damage and penetration that grow with
## the tune; nothing in reach (or only behind) is a whiff; the Blade key drives it on the player's mech.

const RIG := preload("res://tests/lib/mission_rig.gd")


## A stand-in Legion unit: a 2 m box in the "legion" group that keeps the hits it takes.
class FakeLegion:
	extends StaticBody3D
	var dead := false
	var enemy_id := "ameise"
	var hits: Array = []

	func _init() -> void:
		var cs := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = Vector3(2, 2, 2)
		cs.shape = box
		add_child(cs)
		add_to_group("legion")
		collision_layer = LegionMech.LAYER_MECH

	func take_hit(info: Dictionary) -> Dictionary:
		hits.append(info)
		return {"dealt": float(info["damage"]), "penetrated": true}


var rig: RefCounted
var blade: ResonanceBlade


func before_each() -> void:
	rig = RIG.new(tree)
	blade = (rig.level.mech.get_node("Combat") as MechCombat).blade


func after_each() -> void:
	Input.action_release("blade")
	rig.free_all()


func _fake_at_tip(offset: Vector3 = Vector3.ZERO) -> FakeLegion:
	var f := FakeLegion.new()
	rig.level.add_child(f)
	f.global_position = blade.tip() + offset
	return f


func _hold_for(seconds: float) -> void:
	for i in roundi(seconds * 120.0):
		blade.hold(true, 1.0 / 120.0)


func test_the_juggernaut_carries_one() -> void:
	assert_not_null(blade, "the Model 2 has blade parts, so a resonance blade")
	assert_true(InputMap.has_action("blade"), "and a Blade action")
	assert_eq(ResonanceBlade.curve(0.6, blade.def), 0.5, "half way up at half tune_s")
	assert_eq(ResonanceBlade.curve(1.4, blade.def), 1.0, "tuned in the window")
	assert_almost_eq(ResonanceBlade.curve(1.7 + 1.0, blade.def), 0.5, 0.001, "drifted back to half")


func test_a_tuned_strike_cuts_harder_than_an_early_one() -> void:
	await physics_frames(5)
	var f := _fake_at_tip(Vector3(0, 0, -1.5))
	await physics_frames(2)
	var was_tuned := [false]
	blade.tuned.connect(func() -> void: was_tuned[0] = true)
	_hold_for(0.3)
	assert_eq(blade.target, f, "the unit at the tips is the target")
	assert_almost_eq(blade.resonance, 0.25, 0.02)
	blade.hold(false, 1.0 / 120.0)
	assert_eq(f.hits.size(), 1, "the early release strikes")
	await physics_frames(roundi(float(blade.def["cooldown_s"]) * 120.0) + 2)
	_hold_for(1.4)
	assert_true(was_tuned[0], "the meter fills and says so")
	assert_eq(blade.resonance, 1.0)
	blade.hold(false, 1.0 / 120.0)
	assert_eq(f.hits.size(), 2)
	var early: Dictionary = f.hits[0]
	var full: Dictionary = f.hits[1]
	assert_almost_eq(float(full["damage"]), 1600.0 * 3.0, 1.0, "tuned: three times the blade's damage")
	assert_almost_eq(float(full["penetration_mm"]), 850.0, 1.0, "and 250 + 600 mm")
	assert_gt(float(full["damage"]), float(early["damage"]) * 1.8, "far more than the early cut")
	assert_eq(full["shooter"], rig.level.mech, "the player's hit (the sortie log counts it)")
	assert_eq(int(blade.combat.blade_strikes), 2)
	assert_eq(float(blade.last_strike["resonance"]), 1.0)


func test_nothing_in_reach_or_behind_is_a_whiff() -> void:
	await physics_frames(5)
	_hold_for(1.4)
	assert_true(blade.target == null, "nothing at the tips")
	assert_eq(blade.resonance, 0.0, "so nothing to tune to")
	blade.hold(false, 1.0 / 120.0)
	assert_false(blade.last_strike.has("unit"), "a whiff")
	assert_eq(int(blade.combat.blade_strikes), 1, "still a swing")
	var behind := FakeLegion.new()
	rig.level.add_child(behind)
	behind.global_position = rig.level.mech.global_position + rig.level.mech.global_transform.basis.z * 3.0
	await physics_frames(roundi(float(blade.def["cooldown_s"]) * 120.0) + 2)
	_hold_for(0.5)
	assert_true(blade.target == null, "a unit behind the mech is not in front of the blades")
	blade.hold(false, 1.0 / 120.0)
	assert_eq(behind.hits.size(), 0)


func test_the_blade_key_drives_it_and_hits_a_real_legion_unit() -> void:
	await physics_frames(5)
	var u := LegionMech.build("ameise")
	rig.level.add_child(u)
	u.get_node("Brain").process_mode = Node.PROCESS_MODE_DISABLED  # it stands still to be cut
	var fwd: Vector3 = -rig.level.mech.global_transform.basis.z
	u.global_position = Vector3(blade.tip().x, 0.6, blade.tip().z) + fwd * 1.5
	u.look_at(rig.level.mech.global_position * Vector3(1, 0, 1) + Vector3.UP * 0.6, Vector3.UP)
	await physics_frames(10)
	var before := float(u.damage.total_fraction())
	Input.action_press("blade")
	await physics_frames(150)
	assert_true(blade.charging, "holding Blade charges")
	assert_eq(blade.target, u, "tuned to the Ameise at the tips")
	assert_eq(blade.resonance, 1.0)
	Input.action_release("blade")
	await physics_frames(3)
	assert_false(blade.charging)
	assert_gt(float(blade.last_strike.get("dealt", 0.0)), 0.0, "the cut lands")
	assert_true(u.dead or float(u.damage.total_fraction()) < before, "and hurts it")
	assert_eq(u.last_shooter, rig.level.mech)


## Bot run 605: on the real map the ground under the tips is a trimesh that answers a shape query with
## one result per triangle, so the 32 it returned were all ground and the Ameise right there was missed.
func test_ground_triangles_at_the_tips_do_not_hide_the_legion() -> void:
	await physics_frames(3)
	var mech: RigidBody3D = rig.level.mech
	var below := blade.tip() + Vector3.DOWN * 1.2
	var tris := PackedVector3Array()
	var cell := 0.25
	for ix in 32:
		for iz in 32:
			var a := below + Vector3((ix - 16) * cell, 0, (iz - 16) * cell)
			var b := a + Vector3(cell, 0, 0)
			var c := a + Vector3(0, 0, cell)
			var d := a + Vector3(cell, 0, cell)
			tris.append_array([a, b, c, b, d, c])
	var ground := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(tris)
	cs.shape = shape
	ground.add_child(cs)
	rig.level.add_child(ground)
	var f := _fake_at_tip(-mech.global_transform.basis.z * 2.0)
	await physics_frames(2)
	assert_eq(blade.find_target(), f, "the Legion unit at the tips is found over 2048 ground triangles")
