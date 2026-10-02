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


## World position of a point that rides leg joint `part` (rest model-space point `p`), as posed now.
func _posed(u: LegionMech, part: String, p: Vector3) -> Vector3:
	return u.global_transform * (u._delta_of(part) * p)


## Part 4 (Emerson after 010: "their running looks broken", "Legion legs as good as the
## Juggernaut's"): at each unit's top speed on flat ground the legs keep their shape and carry the
## body: no leg pulled straight, every knee stays up off the ground, the soles stay on their feet,
## the body neither pogos (the legs' load swinging far past its weight) nor flies (no leg down).
func test_legs_keep_their_shape_at_full_speed() -> void:
	for id: String in UNITS:
		var u := _spawn(id)
		await physics_frames(240)
		var top := float(Registry.entry("enemies", id)["speed_m_s"])
		var weight := u.mass * 9.81
		u.face_dir = -u.global_transform.basis.z
		u.move_goal = u.face_dir * top
		var frames := 0
		var straight := 0
		var knee_low := 0
		var none_down := 0
		var light := 0
		var heavy := 0
		var worst_tilt := 0.0
		var ik: Array[float] = []
		for i in 720:
			await physics_frames(1)
			if i < 240:
				continue
			frames += 1
			worst_tilt = maxf(worst_tilt, _tilt_deg(u))
			if u.planted_count == 0:
				none_down += 1
			if u.support_n < weight * 0.3:
				light += 1
			if u.support_n > weight * 2.5:
				heavy += 1
			for leg: Dictionary in u.legs:
				var hip := _posed(u, leg["thigh"], leg["p1"])
				var knee := _posed(u, leg["shin"], leg["p2"])
				var sole := _posed(u, leg["shin"], leg["sole"])
				if 180.0 - rad_to_deg((hip - knee).angle_to(sole - knee)) < 8.0:
					straight += 1
				if knee.y < sole.y + 0.3:
					knee_low += 1
				if i % 10 == 0:
					ik.append(u.sole_world(leg).distance_to(leg["foot"]))
		ik.sort()
		var ik95 := ik[int(ik.size() * 0.95)]
		var speed := Vector2(u.linear_velocity.x, u.linear_velocity.z).length()
		var leg_frames := frames * u.legs.size()
		var note := "%s at %.1f m/s (top %.0f): straight %d / %d leg-frames, knee low %d, no leg down %d / %d frames, load < 0.3 W %d, > 2.5 W %d, tilt %.1f deg, IK p95 %.2f m" % [id, speed, top, straight, leg_frames, knee_low, none_down, frames, light, heavy, worst_tilt, ik95]
		print("    " + note)
		assert_gt(speed, top * 0.85, note)
		assert_lt(float(straight) / leg_frames, 0.01, "legs pulled straight: " + note)
		assert_eq(knee_low, 0, "knees off the ground: " + note)
		assert_lt(float(none_down) / frames, 0.03, "a leg down: " + note)
		assert_lt(float(light + heavy) / frames, 0.05, "no pogo: " + note)
		assert_lt(worst_tilt, 10.0, "level: " + note)
		assert_lt(ik95, 0.3, "soles on their feet: " + note)
		u.free()


func _block(size: Vector3, at: Vector3, tilt_deg: float = 0.0) -> StaticBody3D:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	b.position = at
	b.rotation.x = -deg_to_rad(tilt_deg)  # the top leans away from a unit coming from +z
	# Sink it by half its thickness so its top face (not its centre line) meets the ground: no lip.
	b.position -= b.basis.z * size.z * 0.5
	tree.root.add_child(b)
	return b


## Part 4 (Emerson after 010: "they walk up and along cliffs", "climb the map's edge wall"): driven
## straight at a wall twice its hip height, one hip high, and at a 55 deg face, a unit stays on the ground (no
## foot on top, the body never rises); a 20 deg slope it still walks up.
func test_will_not_climb_walls_or_cliffs_but_walks_up_hills() -> void:
	for id: String in UNITS:
		for case: String in ["wall", "low_wall", "cliff", "hill"]:
			var u := _spawn(id)
			var hip_h := float(u.legs[0]["height"])
			var obstacle: StaticBody3D
			match case:
				"wall":
					obstacle = _block(Vector3(60, hip_h * 2.0, 3), Vector3(0, hip_h, -18))
				"low_wall":
					# Hip high, like the small map's ruin walls beside the Löwe's spawn.
					obstacle = _block(Vector3(60, hip_h, 3), Vector3(0, hip_h * 0.5, -18))
				"cliff":
					# A slab tilted 55 deg back, its foot at z = -14.
					obstacle = _block(Vector3(60, 40, 2), Vector3(0, 40 * 0.5 * sin(deg_to_rad(55.0)), -14 - 20 * cos(deg_to_rad(55.0))), 90.0 - 55.0)
				"hill":
					obstacle = _block(Vector3(60, 80, 2), Vector3(0, 80 * 0.5 * sin(deg_to_rad(20.0)), -14 - 40 * cos(deg_to_rad(20.0))), 90.0 - 20.0)
			await physics_frames(240)
			var y0 := u.global_position.y
			u.face_dir = -u.global_transform.basis.z
			u.move_goal = u.face_dir * 5.0
			var rise := 0.0
			var top_foot := 0.0
			for i in 1200:
				await physics_frames(1)
				rise = maxf(rise, u.global_position.y - y0)
				for leg: Dictionary in u.legs:
					if bool(leg["down"]) and bool(leg.get("ok", true)):  # feet that carry (not one resting on the face)
						top_foot = maxf(top_foot, (leg["planted"] as Vector3).y)
			var note := "%s at a %s: body rose %.2f m, highest foot %.2f m (hip height %.2f)" % [id, case, rise, top_foot, hip_h]
			print("    " + note)
			if case == "hill":
				assert_gt(rise, 3.0, "walks up a 20 deg hill: " + note)
			else:
				assert_lt(rise, hip_h * 0.5, "stays down: " + note)
				assert_lt(top_foot, hip_h * 0.6, "no foot up there: " + note)
			u.free()
			obstacle.free()


## Rough ground like the small map's (0.5 m bumps on rolling slopes), as one height-map body.
func _rough_ground() -> StaticBody3D:
	var b := StaticBody3D.new()
	var hm := HeightMapShape3D.new()
	var n := 257
	hm.map_width = n
	hm.map_depth = n
	var noise := FastNoiseLite.new()
	noise.seed = 86
	noise.frequency = 0.25
	var heights := PackedFloat32Array()
	heights.resize(n * n)
	for z in n:
		for x in n:
			var fx := float(x - n / 2)
			var fz := float(z - n / 2)
			heights[z * n + x] = noise.get_noise_2d(fx, fz) * 0.45 + sin(fx * 0.05) * 1.5 + cos(fz * 0.04) * 1.5
	hm.map_data = heights
	var cs := CollisionShape3D.new()
	cs.shape = hm
	b.add_child(cs)
	tree.root.add_child(b)
	return b


## Part 4 (Emerson after 010: "their running looks broken"; seen on screen: an Ameise at 8 m/s
## over the small map's ground with its legs thrown out flat): a slalom at two thirds of top speed
## over rough ground keeps every leg in its own sector (hip yaw within gait.hip_yaw_max_deg of rest),
## none pulled straight, the knees up and the soles on their feet.
func test_legs_keep_their_shape_running_a_slalom_on_rough_ground() -> void:
	ground.free()
	ground = _rough_ground()
	for id: String in UNITS:
		var u := _spawn(id, Vector3(0, 2.2, 0))
		await physics_frames(240)
		var top := float(Registry.entry("enemies", id)["speed_m_s"])
		var yaw_max := 0.0
		var straight := 0
		var knee_low := 0
		var frames := 0
		var ik: Array[float] = []
		var tilts: Array[float] = []
		for i in 960:
			var heading := Vector3.FORWARD.rotated(Vector3.UP, sin(i / 120.0 * 1.2) * 0.9)
			u.face_dir = heading
			u.move_goal = heading * top * 0.65
			await physics_frames(1)
			if i < 120:
				continue
			frames += 1
			tilts.append(_tilt_deg(u))
			for leg: Dictionary in u.legs:
				yaw_max = maxf(yaw_max, absf(rad_to_deg(float(u._angle[leg["hip"]]))))
				var hip := _posed(u, leg["thigh"], leg["p1"])
				var knee := _posed(u, leg["shin"], leg["p2"])
				var sole := _posed(u, leg["shin"], leg["sole"])
				if 180.0 - rad_to_deg((hip - knee).angle_to(sole - knee)) < 8.0:
					straight += 1
				if knee.y < sole.y + 0.3:
					knee_low += 1
				if i % 10 == 0:
					ik.append(u.sole_world(leg).distance_to(leg["foot"]))
		ik.sort()
		var ik95 := ik[int(ik.size() * 0.95)]
		tilts.sort()
		var tilt95 := tilts[int(tilts.size() * 0.95)]
		var note := "%s slalom at %.1f m/s on rough ground: hip yaw max %.0f deg, straight %d / %d, knee low %d, IK p95 %.2f m, tilt p95 %.1f deg, worst %.1f" % [id, top * 0.65, yaw_max, straight, frames * u.legs.size(), knee_low, ik95, tilt95, tilts[-1]]
		print("    " + note)
		assert_lt(yaw_max, float(u.def["gait"].get("hip_yaw_max_deg", 50.0)) + 0.5, note)
		assert_lt(float(straight) / (frames * u.legs.size()), 0.01, note)
		assert_eq(knee_low, 0, note)
		assert_lt(ik95, 0.3, note)
		assert_lt(tilt95, 15.0, "level over the bumps: " + note)
		assert_lt(tilts[-1], 30.0, "never close to tipping: " + note)
		u.free()


## Lane B5 part 3: a Legion unit that falls a long way (a bridge span dropping under a column) is hurt by the
## landing, one that steps down a small drop is not. Hull damage from the impact speed over fall.safe_m_s.
func test_a_long_fall_hurts_a_unit_and_a_small_one_does_not() -> void:
	var u := _spawn("grauwolf", Vector3(0, 12.0, 0))
	await physics_frames(360)  # 3 s: falls 12 m (about 15 m/s) and settles
	var hurt := u.health_fraction()
	print("    grauwolf dropped 12 m: hull %.2f" % hurt)
	assert_lt(hurt, 0.8, "a 12 m fall costs real hull")
	assert_gt(hurt, 0.0, "but a 10 t unit survives it")
	u.free()
	var v := _spawn("grauwolf", Vector3(0, 1.5, 0))
	await physics_frames(240)
	assert_almost_eq(v.health_fraction(), 1.0, 0.001, "a short drop costs nothing")


## Lane B5 part 3: on the big map's hills the Legion tumbled and lay on their backs for good (finale run: tilt
## 114-174 degrees, no feet planted, speed 0, for minutes). The player's Juggernaut has an upright keel; now so do
## they: past gait.keep_deg of lean from the ground a righting torque grows with the lean (and, once nearly still,
## rights a unit that is lying over).
func test_a_unit_lying_on_its_side_or_back_rights_itself() -> void:
	for id: String in UNITS:
		var u := _spawn(id, Vector3(0, 3.0, 0))
		u.rotation = Vector3(deg_to_rad(120.0), 0.0, 0.0)  # well past on its side
		await physics_frames(1200)  # 10 s
		var tilt := _tilt_deg(u)
		print("    %s started 120 degrees over: %.0f degrees after 10 s, %d feet planted" % [id, tilt, u.planted_count])
		assert_lt(tilt, 25.0, id + " is upright again")
		u.free()


## A steep hillside with 1 m bumps, like the big map's 25-35 degree slopes (a foothold needs a flat enough
## 0.8 m patch: on this ground about a quarter of the spots fail). Rises toward -z at `deg`.
func _bumpy_hill(deg: float) -> StaticBody3D:
	var b := StaticBody3D.new()
	var hm := HeightMapShape3D.new()
	var n := 257
	hm.map_width = n
	hm.map_depth = n
	var noise := FastNoiseLite.new()
	noise.seed = 7
	noise.frequency = 0.55
	var heights := PackedFloat32Array()
	heights.resize(n * n)
	for z in n:
		for x in n:
			heights[z * n + x] = noise.get_noise_2d(float(x), float(z)) * 0.7 - float(z - n / 2) * tan(deg_to_rad(deg))
	hm.map_data = heights
	var cs := CollisionShape3D.new()
	cs.shape = hm
	b.add_child(cs)
	tree.root.add_child(b)
	return b


## Part 4 (the Frontier sweep's last wave stalled on the big map's hills, units motionless with one foot planted):
## a leg that found no foothold set its foot down where it was going and never tried again while the body was
## still (no stride, so no retry), and a unit with under two feet standing has no grip. Now such a leg searches
## the ground around the spot and keeps trying, and the body leans with the slope (its hips are held level to the
## hillside, not to the world) so the front legs can reach. Driven up a rough 27 degree hill, each unit gets 40 m up it.
func test_a_unit_keeps_climbing_a_rough_hillside_instead_of_stalling() -> void:
	ground.free()
	ground = _bumpy_hill(27.0)
	for id: String in UNITS:
		var u := _spawn(id, Vector3(0, -60.0 * tan(deg_to_rad(27.0)) + 3.0, 60.0))
		await physics_frames(240)
		var z0 := u.global_position.z
		u.face_dir = Vector3(0, 0, -1)
		u.move_goal = Vector3(0, 0, -4.0)
		var worst_stall := 0.0
		var still := 0.0
		for i in 3600:  # 30 s
			await physics_frames(1)
			if Vector2(u.linear_velocity.x, u.linear_velocity.z).length() < 0.2:
				still += 1.0 / 120.0
				worst_stall = maxf(worst_stall, still)
			else:
				still = 0.0
		var got := z0 - u.global_position.z
		print("    %s on a rough 27 degree hill: %.0f m up in 30 s, longest standstill %.1f s, body %.0f degrees from level, feet %s" % [id, got, worst_stall, _tilt_deg(u), u.telemetry()["feet"]])
		assert_gt(got, 40.0, id + " got up the hill")
		assert_lt(worst_stall, 6.0, id + " never stood still for long")
		u.free()


func test_a_unit_stuck_on_its_belly_hops_off_with_shake_free() -> void:
	var u := _spawn("ameise", Vector3(0, 3.0, 0))
	await physics_frames(240)
	u.rotation = Vector3(deg_to_rad(44.0), 0.0, 0.0)  # leaning like the one on the 41 degree face
	var y0 := u.global_position.y
	u.shake_free()
	var top := 0.0
	for i in 40:
		await physics_frames(1)
		top = maxf(top, u.global_position.y - y0)
	assert_gt(top, 0.5, "it left the ground (rose %.2f m)" % top)
	await physics_frames(600)
	assert_lt(_tilt_deg(u), 25.0, "and is back on its feet, %.0f degrees from level" % _tilt_deg(u))
	u.free()


## Lane B5 part 6: the big map's 1 m ground where the Löwe stood 80 s on the Frontier finale (bot run 368, x -160
## z 1075, feet "hhhhssss"): gentle on the 8 m overview (10-25 degrees) but 30-50 degrees from one metre to the next.
func _big_map_patch(at: Vector2) -> StaticBody3D:
	var t := BigTerrain.new(Registry.entry("maps", "big_map"))
	var b := StaticBody3D.new()
	b.collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE
	var c := t.tile_of(at.x, at.y)
	for dz in range(-1, 2):
		for dx in range(-1, 2):
			var data := t.tile(c.x + dx, c.y + dz, 1)
			var o := t.tile_origin(c.x + dx, c.y + dz)
			var cs := CollisionShape3D.new()
			cs.shape = BigTerrain.tile_shape(data)
			cs.position = Vector3(o.x + BigTerrain.TILE_M * 0.5, 0.0, o.y + BigTerrain.TILE_M * 0.5)
			b.add_child(cs)
	b.set_meta("terrain", t)
	tree.root.add_child(b)
	return b


## The Löwe's own brain walking it to a stop 120 m on, up out of the hollow past a 3-4 m bank of about 40 degrees
## (west of the start). Before part 6 it got 9 m in 90 s: it sank onto its belly against the bank, and with its hips
## under the ground ahead no foot could land (the step-up limit was a ledge rule, so a long stride could not climb
## past 19 degrees, and a sunk body had no foothold in reach). Now a foot may climb the grippable slope plus a ledge,
## bear weight where it cannot grip, and tuck in under its hip to stand the body back up.
func test_the_lowe_brain_finds_a_way_off_the_rough_patch() -> void:
	ground.free()
	ground = _big_map_patch(Vector2(-160, 1075))
	var t: BigTerrain = ground.get_meta("terrain")
	var dir := Vector3(-115, 0, -94).normalized()
	var goal := Vector3(-160, 0, 1075) + dir * 120.0
	goal.y = t.height_at(goal.x, goal.z)
	unit = LegionMech.build("lowe")
	unit.position = Vector3(-160, t.height_at(-160, 1075) + 4.0, 1075)
	var brain := unit.get_node("Brain")
	brain.setup(unit.position, [brain], 0, 7, [goal] as Array[Vector3])
	tree.root.add_child(unit)
	var start := unit.global_position
	var worst_stall := 0.0
	var still := 0.0
	var best := INF
	for i in 120 * 150:  # 150 s
		await physics_frames(1)
		if Vector2(unit.linear_velocity.x, unit.linear_velocity.z).length() < 0.5:
			still += 1.0 / 120.0
			worst_stall = maxf(worst_stall, still)
		else:
			still = 0.0
		best = minf(best, Vector2(goal.x - unit.global_position.x, goal.z - unit.global_position.z).length())
		if best < 6.0:
			break
	print("    lowe brain on the rough patch: closest %.0f m to a stop 120 m away, longest standstill %.1f s, feet %s" % [best, worst_stall, unit.telemetry()["feet"]])
	assert_lt(best, 20.0, "it got to the stop")
	assert_lt(worst_stall, 10.0, "it never stood still for long")
	unit.free()


## Lane B5 part 7: the small map's shell craters (7 m across, walls of 36-40 degrees, the Ameise's feet grip 38) are
## bowls the legs cannot get out of the way they went in. Emerson's first wave rolled over in them and sat in one for
## ten seconds (x -215 z 247). The brain's look-ahead keeps `ai.slope_margin_deg` under the feet's limit, so a pair
## sent straight across the crater goes round or over the lip rather than into it.
func _crater_pairs(margin: float, pairs: int) -> Dictionary:
	var small := SmallMapTerrain.new(Registry.entry("maps", "small_map"))
	var map := StaticBody3D.new()
	map.collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE
	var cs := CollisionShape3D.new()
	cs.shape = small.build_shape()
	map.add_child(cs)
	tree.root.add_child(map)
	var c := Vector2(-210, 250)
	var flips := 0
	var steep_s := 0.0
	for k in pairs:
		var pair: Array[LegionMech] = []
		var tilt: Array[float] = [0.0, 0.0]
		var goals: Array[Vector2] = []
		for j in 2:
			var a := deg_to_rad(30.0 * k + 3.0 + 70.0 * j)
			var s := c + Vector2(cos(a), sin(a)) * (40.0 + 2.3 * k + 1.7 * j)
			var u := LegionMech.build("ameise")
			(u.def["ai"] as Dictionary)["slope_margin_deg"] = margin
			u.position = Vector3(s.x, small.height_at(s.x, s.y) + 1.5, s.y)
			var far := c + (c - s).normalized() * 55.0
			goals.append(far)
			var brain := u.get_node("Brain")
			brain.setup(u.position, [brain], 0, 7 + j, [Vector3(far.x, small.height_at(far.x, far.y), far.y)] as Array[Vector3])
			tree.root.add_child(u)
			pair.append(u)
		for i in 120 * 45:
			await physics_frames(1)
			for j in 2:
				var deg := rad_to_deg(pair[j].global_transform.basis.y.angle_to(Vector3.UP))
				tilt[j] = maxf(tilt[j], deg)
				steep_s += (1.0 / 120.0) if deg > 45.0 else 0.0
			if i % 120 == 0 and goals[0].distance_to(Vector2(pair[0].global_position.x, pair[0].global_position.z)) < 6.0 and goals[1].distance_to(Vector2(pair[1].global_position.x, pair[1].global_position.z)) < 6.0:
				break
		flips += int(tilt[0] > 90.0) + int(tilt[1] > 90.0)
		for u in pair:
			u.free()
	map.free()
	return {"flips": flips, "steep_s": steep_s}


func test_a_pair_sent_across_a_shell_crater_does_not_roll_over_in_it() -> void:
	var before := await _crater_pairs(0.0, 4)
	var after := await _crater_pairs(float(Registry.entry("enemies", "ameise")["ai"]["slope_margin_deg"]), 4)
	print("    ameise pairs across the crater, 8 units: flipped over %d -> %d, seconds past 45 degrees %.0f -> %.0f (margin 0 -> data)" % [before["flips"], after["flips"], before["steep_s"], after["steep_s"]])
	assert_lt(after["flips"], maxi(int(before["flips"]), 1), "fewer roll over with the margin")
	assert_lt(float(after["steep_s"]), float(before["steep_s"]) * 0.6, "and they spend far less time tilted")
