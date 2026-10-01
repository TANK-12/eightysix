extends "res://tests/lib/test_case.gd"
## Lane A3's gun: WeaponState's magazine/reload/ammo rules, Ballistics' drop, and the real Juggernaut
## firing: a round leaves the muzzle, flies, and hits; recoil pushes the body back, far harder in the
## air (the recoil dodge). tools/run_tests.sh runs at --fixed-fps 120 (120 physics frames = 1 s).


class Catcher:
	extends StaticBody3D
	var hits: Array = []

	func take_hit(info: Dictionary) -> Dictionary:
		hits.append(info)
		return {}


var ground: StaticBody3D
var mech: RigidBody3D
var extras: Array = []


func _gun() -> WeaponState:
	return WeaponState.new("gun_57mm", Registry.entry("weapons", "gun_57mm"))


func _ground() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 2, 400)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)


func _mech(at: Vector3) -> MechCombat:
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = at
	tree.root.add_child(mech)
	return mech.get_node("Combat") as MechCombat


func after_each() -> void:
	for n: Node in extras:
		if is_instance_valid(n):
			n.free()
	extras.clear()
	if is_instance_valid(mech):
		mech.free()
	if is_instance_valid(ground):
		ground.free()
	for r: Node in tree.root.find_children("Round", "", false, false):
		r.free()
	Settings.reset_all_quietly()


func test_magazine_cycle_and_auto_reload() -> void:
	var g := _gun()
	assert_eq(g.magazine, 12)
	assert_eq(g.loaded_ammo, "apfsds")
	assert_false(g.fire().is_empty(), "first shot")
	assert_true(g.fire().is_empty(), "the breech has not cycled yet")
	g.tick(0.95)
	assert_eq(str(g.fire().get("id", "")), "apfsds", "fires again after cycle_s")
	assert_eq(g.magazine, 10)
	for i in 10:
		g.tick(1.0)
		g.fire()
	assert_eq(g.magazine, 0)
	assert_true(g.reloading(), "an empty magazine starts the reload by itself")
	assert_true(g.fire().is_empty(), "cannot fire while reloading")
	var done := false
	for i in 50:
		done = g.tick(0.1) or done
	assert_true(done, "reload completes after reload_s")
	assert_eq(g.magazine, 12)
	assert_eq(g.reserve, 48, "the refill came out of the reserve")


func test_ammo_swap_unloads_to_reserve() -> void:
	var g := _gun()
	g.fire()
	assert_eq(g.select_next_ammo(), "heat")
	assert_true(g.reloading(), "a type change is a reload")
	for i in 50:
		g.tick(0.1)
	assert_eq(g.loaded_ammo, "heat")
	assert_eq(g.magazine, 12)
	assert_eq(g.reserve, 60 + 11 - 12, "the 11 unfired darts went back to the reserve")


func test_reserve_runs_dry_unless_unlimited() -> void:
	var g := _gun()
	g.reserve = 0
	g.magazine = 0
	assert_false(g.start_reload(), "no reserve, no reload")
	var u := WeaponState.new("gun_57mm", Registry.entry("weapons", "gun_57mm"), true)
	u.reserve = 0
	u.magazine = 0
	assert_true(u.start_reload())
	for i in 50:
		u.tick(0.1)
	assert_eq(u.magazine, 12, "unlimited reserve still refills")


func test_ballistic_drop() -> void:
	var drop := Ballistics.drop_at(1000.0, 1550.0, 9.81, 0.0)
	var t := 1000.0 / 1550.0
	assert_almost_eq(drop, 0.5 * 9.81 * t * t, 0.1, "no drag: the textbook drop at 1 km")
	assert_gt(Ballistics.drop_at(1000.0, 1550.0, 9.81, 0.02), drop, "drag adds drop")
	assert_gt(Ballistics.drop_at(1000.0, 800.0, 9.81, 0.1), Ballistics.drop_at(1000.0, 1550.0, 9.81, 0.02) * 3.0, "slow HE drops far more than the dart")


func test_every_collider_has_a_damage_key() -> void:
	var combat := _mech(Vector3(0, 3, 0))
	var keys := 0
	for cs: Node in mech.find_children("*", "CollisionShape3D", true, false):
		if not cs.has_meta("part_id"):
			continue
		assert_true(cs.has_meta("damage_key"), "%s has a damage key" % cs.name)
		keys += 1
		var key := str(cs.get_meta("damage_key"))
		if Registry.entry("parts", str(cs.get_meta("part_id"))).get("health", 0) > 0:
			assert_true(combat.damage.has(key), "the damage model knows %s" % key)
	assert_gt(keys, 40, "chassis parts and 12 leg hitboxes")
	assert_true(combat.damage.has("leg_fr_upper"))
	assert_not_null(combat.gun, "the loadout's main gun")
	assert_not_null(combat.anchor, "the loadout's wire anchor")


func test_fired_round_flies_and_hits_a_target() -> void:
	_ground()
	var combat := _mech(Vector3(0, 3, 0))
	await physics_frames(240)
	var target := Catcher.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(8, 8, 1)
	cs.shape = box
	target.add_child(cs)
	tree.root.add_child(target)
	extras.append(target)
	var muzzle := mech.global_transform * combat.muzzle_local()
	target.global_position = muzzle + combat.gun_direction() * 120.0
	assert_true(combat.fire_main(), "fires")
	assert_eq(combat.gun.magazine, 11)
	assert_not_null(combat.last_shot, "a round is in flight")
	await physics_frames(30)
	assert_eq(target.hits.size(), 1, "the round hit the plate 120 m out")
	if target.hits.size() == 1:
		var info: Dictionary = target.hits[0]
		assert_almost_eq(float(info["damage"]), 900.0, 0.01, "APFSDS damage")
		assert_between(float(info["range_m"]), 115.0, 125.0, "flew the distance")
		assert_gt(float(info["speed"]), 1400.0, "still fast")
	assert_false(combat.fire_main(), "the breech is still cycling")


func test_recoil_is_the_real_impulse_and_all_of_it_moves_the_body_in_the_air() -> void:
	# Lane A3 part 4 (Emerson: real physics only): projectile 1.2 kg x 1550 m/s plus propellant gas
	# 1.6 kg x 1.5 x 1550 m/s = 5,580 N s, no game scale, no muzzle brake.
	_ground()
	var combat := _mech(Vector3(0, 3, 0))
	await physics_frames(360)
	var back := mech.global_transform.basis.z
	var v0 := mech.linear_velocity.dot(back)
	var m0 := mech.mass
	combat.fire_main()
	assert_almost_eq(combat.last_recoil.length(), 5580.0, 1.0, "projectile + gas momentum")
	assert_almost_eq(m0 - mech.mass, 10.75, 0.01, "the round fired leaves the mech lighter")
	await physics_frames(1)
	var ground_kick := mech.linear_velocity.dot(back) - v0
	assert_gt(ground_kick, 0.0, "the shot shoves the body back on the ground")
	mech.free()
	ground.free()
	combat = _mech(Vector3(0, 40, 0))
	await physics_frames(60)
	assert_true(bool(mech.get("airborne")), "falling with nothing under it")
	back = mech.global_transform.basis.z
	v0 = mech.linear_velocity.dot(back)
	var mass := mech.mass
	var pitch0 := mech.angular_velocity.dot(mech.global_transform.basis.x)
	combat.fire_main()
	await physics_frames(1)
	var air_kick := mech.linear_velocity.dot(back) - v0
	assert_almost_eq(air_kick, 5580.0 / mass, 0.05, "in the air the speed change is impulse / mass (%.2f m/s)" % air_kick)
	assert_gt(air_kick, ground_kick, "the feet's grip takes some of it on the ground")
	var pitch := mech.angular_velocity.dot(mech.global_transform.basis.x) - pitch0
	assert_gt(pitch, 0.0, "the bore line sits above the centre of mass: the nose kicks up")


## Lane A4 (Emerson 2026-10-01: "more gun recoil, a shell type with more recoil, and damage"): the
## overcharged heavy shot puts more momentum out of the muzzle (4 kg x 1100 + 2.4 kg gas x 1.5 x 1100
## = 8,360 N s against the APFSDS 5,580) and carries more energy (2.4 MJ, damage 1510).
func test_heavy_round_kicks_harder_and_hits_harder() -> void:
	var combat := _mech(Vector3(0, 40, 0))
	await physics_frames(30)
	var gun: Dictionary = Registry.entry("weapons", "gun_57mm")
	var heavy: Dictionary = gun["ammo"]["heavy"]
	var apfsds: Dictionary = gun["ammo"]["apfsds"]
	assert_almost_eq(Ballistics.recoil_impulse(gun, heavy), 8360.0, 1.0)
	var energy := 0.5 * float(heavy["projectile_kg"]) * pow(float(heavy["muzzle_m_s"]), 2.0)
	var energy_ap := 0.5 * float(apfsds["projectile_kg"]) * pow(float(apfsds["muzzle_m_s"]), 2.0)
	assert_almost_eq(float(heavy["damage"]) / energy, float(apfsds["damage"]) / energy_ap, 0.00001, "damage per joule as the APFSDS")
	while combat.gun.selected_ammo != "heavy":
		combat.gun.select_next_ammo()
	for i in 700:
		combat.gun.tick(1.0 / 120.0)
	assert_eq(combat.gun.loaded_ammo, "heavy", "loaded after the swap")
	var back := mech.global_transform.basis.z
	var v0 := mech.linear_velocity.dot(back)
	var mass := mech.mass
	assert_true(combat.fire_main())
	await physics_frames(1)
	var kick := mech.linear_velocity.dot(back) - v0
	assert_almost_eq(kick, 8360.0 / mass, 0.06, "in the air a heavy shot kicks %.2f m/s" % kick)
	assert_gt(kick, 1.4, "about half as hard again as the APFSDS (1.0 m/s)")


func test_sub_arm_guns_fire_in_turn_with_real_recoil() -> void:
	# Lane A3 part 5 (Emerson: "add the sub guns"): the pair of 12.7 mm guns on the sub-arms.
	var combat := _mech(Vector3(0, 40, 0))
	await physics_frames(30)
	assert_not_null(combat.sub_guns, "the Juggernaut carries the sub-arm guns")
	var belt0 := combat.sub_guns.magazine
	var m0 := mech.mass
	var sides: Array = []
	for i in 120:
		var before := combat.sub_shots
		var side := int(combat.get("_sub_side"))
		combat.fire_sub()
		if combat.sub_shots > before:
			sides.append(side)
		await physics_frames(1)
	assert_gt(combat.sub_shots, 12, "about 16 rounds a second from the pair (%d in 1 s)" % combat.sub_shots)
	assert_eq(belt0 - combat.sub_guns.magazine, combat.sub_shots, "every round fired came off the belts")
	assert_eq(sides.slice(0, 4), [0, 1, 0, 1], "the arms fire in turn")
	assert_almost_eq(combat.last_sub_recoil.length(), 0.045 * 890.0 + 0.015 * 1.5 * 890.0, 0.1, "60 N s: projectile + gas momentum")
	assert_almost_eq(m0 - mech.mass, combat.sub_shots * 0.117, 0.01, "each round's 117 g leaves the mech")


func test_sub_arms_swing_to_the_crosshair_not_the_body() -> void:
	_ground()
	Settings.set_value("gameplay.sub_guns_aim", "arms", false)
	var combat := _mech(Vector3(0, 3, 0))
	await physics_frames(240)
	var body_fwd := -mech.global_transform.basis.z
	mech.set("look_pitch_deg", 30.0)
	await physics_frames(120)
	var dir := combat.sub_direction(0)
	var pitch := rad_to_deg(asin(clampf(dir.y, -1.0, 1.0)))
	assert_almost_eq(pitch, 30.0, 3.0, "the left arm points up the look line (%.1f deg)" % pitch)
	var body_pitch := rad_to_deg(asin(clampf((-mech.global_transform.basis.z).y, -1.0, 1.0)))
	assert_lt(body_pitch, 20.0, "while the body tilts only as far as its legs allow (%.1f deg)" % body_pitch)
	assert_gt(dir.angle_to(body_fwd), deg_to_rad(10.0), "the arms, not the body, did the aiming")


func test_combat_hud_follows_the_mech() -> void:
	var combat := _mech(Vector3(0, 3, 0))
	var hud := CombatHud.new()
	hud.size = Vector2(1920, 1080)
	extras.append(hud)
	tree.root.add_child(hud)
	hud.watch(mech)
	assert_eq(hud.combat, combat, "finds the mech's Combat child")
	assert_true(CombatHud.health_color(1.0).is_equal_approx(UiTheme.color("good")), "health 1.0 is good")
	assert_true(CombatHud.health_color(0.5).is_equal_approx(UiTheme.color("warn")), "health 0.5 is warn")
	assert_true(CombatHud.health_color(0.0).is_equal_approx(UiTheme.color("bad")), "health 0.0 is bad")
	await physics_frames(2)
	combat.damage.hit("leg_fl_lower", 1500.0 * 0.6, 999.0)
	hud.queue_redraw()
	await physics_frames(2)
	assert_lt(combat.limp_factor(), 1.0, "the diagram's limp line has something to show")


func test_a_round_knocks_a_loose_steel_plate_away() -> void:
	_ground()
	var combat := _mech(Vector3(0, 3, 0))
	await physics_frames(240)
	var plate := RigidBody3D.new()
	plate.mass = 400.0
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(2.4, 4.5, 0.25)  # the range's plates: tall enough for a level shot (muzzle 2.9 m up)
	cs.shape = box
	plate.add_child(cs)
	tree.root.add_child(plate)
	extras.append(plate)
	var muzzle := mech.global_transform * combat.muzzle_local()
	# 30 m out, standing on the ground: the gun line (the chassis rests a degree or two nose-up)
	# crosses it about 3.8 m up, inside the 4.5 m plate.
	var at := muzzle + combat.gun_direction() * 30.0
	assert_between(at.y, 0.5, 4.3, "the gun line crosses the plate")
	plate.global_position = Vector3(at.x, 2.25, at.z)
	plate.look_at(Vector3(muzzle.x, 2.25, muzzle.z))
	await physics_frames(60)
	assert_gt(plate.global_transform.basis.y.dot(Vector3.UP), 0.95, "standing before the shot")
	var start := plate.global_position
	combat.fire_main()
	await physics_frames(12)
	# Lane A3 part 4: the push is the dart's own momentum, 1.2 kg x ~1550 m/s = 1,860 N s, about
	# 4.6 m/s on a 400 kg plate (the old x4 game scale is gone).
	assert_gt(plate.angular_velocity.length(), 1.5, "the hit sets it spinning (%.1f rad/s)" % plate.angular_velocity.length())
	await physics_frames(108)
	assert_gt(plate.global_position.distance_to(start), 2.5, "and throws it back (%.1f m)" % plate.global_position.distance_to(start))



## Emerson 2026-10-01: no recoil buffer, no barrel slide; the gun is solid on the frame and the whole
## kick goes straight into the body, in the same tick.
func test_the_gun_is_rigid_and_the_whole_kick_lands_at_once() -> void:
	var combat := _mech(Vector3(0, 40, 0))
	await physics_frames(30)
	var sk := mech.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var bone := sk.find_bone("gun_pitch")
	var rest := sk.get_bone_pose_position(bone)
	var back := mech.global_transform.basis.z
	var v0 := mech.linear_velocity.dot(back)
	combat.fire_main()
	await physics_frames(1)
	var kick := mech.linear_velocity.dot(back) - v0
	assert_almost_eq(kick, combat.last_recoil.length() / mech.mass, 0.05, "all of it in one tick (%.2f m/s)" % kick)
	for i in 30:
		await physics_frames(1)
		assert_true(sk.get_bone_pose_position(bone).is_equal_approx(rest), "the barrel never slides")


## Part 4 (Emerson after 010: the sub-arm guns were "put on the arms instead of fixed to the body as he
## wanted"; "a little bit of movement with the guns" welcome, "no movement of the big gun"): by default
## both 12.7 mm guns point straight down the body's heading whatever the crosshair does; "play" lets
## each mount swing at most combat.sub_play_deg toward it; the 57 mm stays on the body's heading in
## every mode.
func test_sub_guns_fixed_by_default_a_little_play_as_an_option_and_the_57mm_never_moves() -> void:
	_ground()
	var combat := _mech(Vector3(0, 3, 0))
	await physics_frames(240)
	var play := float(Registry.tune("combat", {}).get("sub_play_deg", 4.0))
	var out := {}
	for mode: String in ["fixed", "play", "arms"]:
		Settings.set_value("gameplay.sub_guns_aim", mode, false)
		mech.set("look_pitch_deg", 30.0)
		await physics_frames(180)
		var fwd := -mech.global_transform.basis.z
		out[mode] = rad_to_deg(combat.sub_direction(0).angle_to(fwd))
		var gun_off := rad_to_deg(combat.gun_direction().angle_to(fwd))
		assert_lt(gun_off, 0.01, "%s: the 57 mm points down the body's heading (%.3f deg off)" % [mode, gun_off])
		mech.set("look_pitch_deg", 0.0)
		await physics_frames(120)
	print("    sub-gun off the body's heading with the crosshair 30 deg up: fixed %.2f, play %.2f, arms %.1f deg" % [out["fixed"], out["play"], out["arms"]])
	assert_lt(float(out["fixed"]), 0.5, "fixed: straight down the body")
	assert_between(float(out["play"]), play * 0.5, play + 0.3, "play: a few degrees toward the aim")
	assert_gt(float(out["arms"]), 10.0, "arms: the arms aim")


## Part 4 (Emerson: "can't tell where the 57 mm is aiming"): the 57 mm's mark is where its round
## lands. A wall 120 m down the bore: the solver lands on the wall at 120 m, a little under the bore
## line by the round's drop; with nothing in the way it reports a far miss, not a false hit.
func test_the_57mm_mark_is_where_its_round_lands() -> void:
	_ground()
	var combat := _mech(Vector3(0, 3, 0))
	await physics_frames(240)
	var muzzle := mech.global_transform * combat.muzzle_local()
	var dir := combat.gun_direction()
	var flat := Vector3(dir.x, 0.0, dir.z).normalized()
	var wall := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40, 40, 1)
	cs.shape = box
	wall.add_child(cs)
	tree.root.add_child(wall)
	wall.global_position = muzzle + flat * 120.5
	wall.look_at(muzzle, Vector3.UP)
	extras.append(wall)
	await physics_frames(2)
	var hit := combat.main_impact()
	var bore_at := muzzle + dir * float(hit["range_m"])
	var under := bore_at.y - (hit["point"] as Vector3).y
	print("    57 mm mark on a wall 120 m out: range %.1f m, %.3f m under the bore line" % [hit["range_m"], under])
	assert_true(bool(hit["hit"]), "it lands on the wall")
	assert_almost_eq(float(hit["range_m"]), 120.0, 1.5, "at the wall's range")
	assert_between(under, 0.0, 0.2, "a little under the bore line (the drop over 120 m)")
