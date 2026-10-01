extends "res://tests/lib/test_case.gd"
## Lane A4: the Legion in the game, built from lane B2's exports. Each unit's mass is summed from its
## parts; it stands on its legs (springs from hip to planted foot), its leg IK puts every sole on its
## foot target, it walks at the speed it is asked through its feet's grip and turns to face a
## heading; hits land on damage zones (hull, legs, weak points) and a lost hull destroys it.
## --fixed-fps 120.

const UNITS := ["ameise", "grauwolf", "lowe"]

var ground: StaticBody3D
var unit: LegionMech


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(800, 2, 800)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)


func after_each() -> void:
	if unit != null and is_instance_valid(unit):
		unit.free()
	ground.free()
	for n: Node in tree.root.get_children():
		if n.name.begins_with("Round") or n is RigidBody3D or n is GPUParticles3D or n is CPUParticles3D or n is Decal or n is OmniLight3D:
			n.free()


func _spawn(id: String, at: Vector3 = Vector3(0, 0.3, 0)) -> LegionMech:
	unit = LegionMech.build(id)
	unit.position = at
	var brain := unit.get_node_or_null("Brain")
	if brain != null:
		brain.free()  # driven by hand in these tests
	tree.root.add_child(unit)
	return unit


func _tilt_deg(u: Node3D) -> float:
	return rad_to_deg(u.global_transform.basis.y.angle_to(Vector3.UP))


func test_every_unit_builds_with_mass_from_its_parts() -> void:
	for id: String in UNITS:
		assert_true(LegionMech.can_build(id), id + " export synced")
		var u := LegionMech.build(id)
		var data := LegionMech.model_data(Registry.entry("enemies", id))
		assert_almost_eq(u.mass, float(data["total_mass_kg"]), float(data["total_mass_kg"]) * 0.01, id + " mass from parts")
		assert_eq(u.legs.size(), int(data["legs_expected"]), id + " legs")
		assert_true(u.damage.has("hull"), id + " hull zone")
		for wp: String in data["weak_points"]:
			if wp != "leg_joints":
				assert_true(u.damage.has("wp_" + wp), id + " weak point " + wp)
		var keys := {}
		for cs: CollisionShape3D in u.find_children("Collider_*", "CollisionShape3D", true, false):
			keys[str(cs.get_meta("damage_key"))] = true
		assert_has(keys, "hull", id + " has hull colliders")
		assert_gt(keys.size(), 4, id + " colliders carry several zones (%s)" % str(keys.keys()))
		u.free()


func test_stands_with_soles_on_their_feet() -> void:
	for id: String in UNITS:
		var u := _spawn(id)
		await physics_frames(480)
		assert_lt(_tilt_deg(u), 4.0, id + " upright (%.1f deg)" % _tilt_deg(u))
		assert_gt(u.planted_count, u.legs.size() / 2 - 1, id + " on its legs (%d planted)" % u.planted_count)
		assert_almost_eq(u.support_n, u.mass * 9.81, u.mass * 9.81 * 0.1, id + " the legs carry its weight")
		var worst := 0.0
		for leg: Dictionary in u.legs:
			worst = maxf(worst, u.sole_world(leg).distance_to(leg["foot"]))
		assert_lt(worst, 0.12, id + " IK puts every sole on its foot (worst %.3f m)" % worst)
		print("    %s: %.0f kg, %d legs, stands %.2f m above its feet, tilt %.1f deg, IK worst %.3f m" % [id, u.mass, u.legs.size(), u.global_position.y, _tilt_deg(u), worst])
		u.free()


func test_walks_and_turns_through_its_feet() -> void:
	for id: String in UNITS:
		var u := _spawn(id)
		await physics_frames(240)
		var steps := [0]
		u.stepped.connect(func(_l: String) -> void: steps[0] += 1)
		var want := minf(float(Registry.entry("enemies", id)["speed_m_s"]) * 0.6, 8.0)
		u.move_goal = -u.global_transform.basis.z * want
		u.face_dir = -u.global_transform.basis.z
		var worst_tilt := 0.0
		var worst_ik := 0.0
		for i in 600:
			await physics_frames(1)
			worst_tilt = maxf(worst_tilt, _tilt_deg(u))
			if i > 240 and i % 20 == 0:
				for leg: Dictionary in u.legs:
					worst_ik = maxf(worst_ik, u.sole_world(leg).distance_to(leg["foot"]))
		var speed := Vector2(u.linear_velocity.x, u.linear_velocity.z).length()
		assert_between(speed, want * 0.8, want * 1.1, id + " walks at the asked %.1f m/s (%.1f)" % [want, speed])
		assert_gt(steps[0], 20, id + " by stepping (%d steps)" % steps[0])
		assert_lt(worst_tilt, 8.0, id + " stays level (worst %.1f deg)" % worst_tilt)
		assert_lt(worst_ik, 0.35, id + " soles follow the feet while walking (worst %.2f m)" % worst_ik)
		# Turn a quarter round on the spot.
		u.move_goal = Vector3.ZERO
		var right := u.global_transform.basis.x
		u.face_dir = right
		await physics_frames(600)
		var fwd := -u.global_transform.basis.z
		var err := rad_to_deg(Vector2(fwd.x, fwd.z).angle_to(Vector2(right.x, right.z)))
		assert_lt(absf(err), 6.0, id + " turned to face the new heading (%.1f deg off)" % err)
		print("    %s: walk %.1f m/s asked %.1f, %d steps, tilt %.1f deg, IK %.2f m, turn error %.1f deg" % [id, speed, want, steps[0], worst_tilt, worst_ik, err])
		u.free()


func test_hits_land_on_zones_and_the_hull_destroys_it() -> void:
	var u := _spawn("ameise")
	await physics_frames(240)
	var r := u.take_hit({"key": "wp_optic_sensor", "damage": 900.0, "penetration_mm": 180.0, "point": u.global_position, "dir": Vector3.FORWARD, "speed": 1550.0, "projectile_kg": 1.2})
	assert_true(bool(r["penetrated"]))
	assert_lt(u.damage.fraction("hull"), 1.0, "a penetrating hit on the optic reaches the hull too")
	var died := [false]
	u.destroyed.connect(func() -> void: died[0] = true)
	for i in 4:
		u.take_hit({"key": "hull", "damage": 900.0, "penetration_mm": 180.0, "point": u.global_position, "dir": Vector3.FORWARD})
	assert_true(died[0] and u.dead, "the hull lost: destroyed")
	await physics_frames(240)
	assert_eq(u.planted_count, 0, "the legs no longer hold it")


func test_a_57mm_round_finds_a_leg_through_its_moving_hitbox() -> void:
	var u := _spawn("grauwolf")
	await physics_frames(240)
	var leg: Dictionary = u.legs[0]
	var aim := u.sole_world(leg).lerp(u.global_transform * (leg["p2"] as Vector3), 0.5)
	var got: Array = []
	u.hit_taken.connect(func(key: String, dealt: float, _i: Dictionary) -> void: got.append(key))
	var round_def: Dictionary = (Registry.entry("weapons", "gun_57mm")["ammo"] as Dictionary)["apfsds"].duplicate()
	round_def["id"] = "apfsds"
	var from := aim + Vector3(40, 0.0, 0) * signf((u.to_local(aim)).x)
	var skip: Array[RID] = []
	Projectile.spawn(tree.root, from, (aim - from).normalized() * 1550.0, round_def, null, 1.0, skip)
	await physics_frames(10)
	assert_eq(got.size(), 1, "one hit")
	if got.size() == 1:
		assert_true(str(got[0]).begins_with("leg_") or str(got[0]).begins_with("knee_"), "on the leg (%s)" % got[0])


func test_lite_model_past_lod_range_follows_the_pose() -> void:
	var u := _spawn("grauwolf")
	assert_not_null(u.lite, "the lite export is loaded")
	var full_mesh := u.model.find_children("*", "GeometryInstance3D", true, false)[0] as GeometryInstance3D
	var lite_mesh := u.lite.find_children("*", "GeometryInstance3D", true, false)[0] as GeometryInstance3D
	assert_almost_eq(full_mesh.visibility_range_end, 150.0, 0.01, "full model up to 150 m")
	assert_almost_eq(lite_mesh.visibility_range_begin, 150.0, 0.01, "lite model past it")
	u.move_goal = -u.global_transform.basis.z * 6.0
	u.aim_point = u.global_position + Vector3(30, 5, -30)
	await physics_frames(240)
	var worst := 0.0
	var data := LegionMech.model_data(Registry.entry("enemies", "grauwolf"))
	for j: Dictionary in data["joints"]:
		var a := u.model.find_child(str(j["part"]), true, false) as Node3D
		var b := u.lite.find_child(str(j["part"]), true, false) as Node3D
		worst = maxf(worst, a.global_position.distance_to(b.global_position))
	assert_lt(worst, 0.001, "every joint part of the lite model sits where the full one does (%.4f m)" % worst)
	u.set_lod(0.0)
	assert_eq(full_mesh.visibility_range_end, 0.0, "lod off: full model at every distance")
	assert_false(u.lite.visible, "and the lite one hidden")
