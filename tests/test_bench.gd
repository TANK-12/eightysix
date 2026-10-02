extends "res://tests/lib/test_case.gd"
## Lane B6: test bench mode. The rig (scripts/mech/bench_rig.gd) is checked on its own first: torque
## limits, power, heat, thermal cutout, shock failure and the battery, with the Juggernaut's real
## parts.json actuators and data/bench.json. The mech-level checks follow further down.

const HIP := "jg2_act_hip_pitch_FR"
const KNEE := "jg2_act_knee_FR"
const YAW := "jg2_act_hip_yaw_FR"

var rig: BenchRig
var ground: StaticBody3D
var mech: RigidBody3D


func before_each() -> void:
	rig = _make_rig()


func after_each() -> void:
	for a: String in ["move_forward", "jump", "sprint", "turn_left"]:
		Input.action_release(a)
	if mech != null and is_instance_valid(mech):
		mech.free()
	if ground != null and is_instance_valid(ground):
		ground.free()
	mech = null
	ground = null
	Settings.reset_all_quietly()


## The real Juggernaut on flat ground in test bench mode, dropped from a hand's breadth.
func _spawn(drop_m: float = 0.5) -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(600, 2, 600)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	Settings.set_value("gameplay.physics_mode", "bench", false)
	Settings.set_value("mech.leg_length", 1.0, false)
	Settings.set_value("mech.foot_spread", 1.0, false)
	Settings.set_value("mech.ride_lift_m", 0.0, false)
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 2.4 + drop_m, 0)
	tree.root.add_child(mech)


func _frames(n: int) -> void:
	for i in n:
		await tree.physics_frame


func _driver() -> Node:
	return mech.get("bench")


func _joint(leg: String, kind: String) -> Dictionary:
	return _driver().rig.joints[_driver().leg_joints[leg][kind]]


func _make_rig(ids: Array = [HIP, KNEE, YAW]) -> BenchRig:
	var r := BenchRig.new(Registry.file("bench"))
	for id: String in ids:
		r.add_joint(id, Registry.entry("parts", id), "fr")
	return r


func _hold(r: BenchRig, id: String, frac_of_rated: float, seconds: float, omega: float = 0.0, dt: float = 0.25) -> void:
	var j: Dictionary = r.joints[id]
	var t := 0.0
	while t < seconds:
		r.step(dt, {id: {"torque": frac_of_rated * float(j["rated_nm"]), "omega": omega}})
		t += dt


func test_bench_registry_loads() -> void:
	assert_true(Registry.has_file("bench"), "data/bench.json is a registry")
	var cfg := Registry.file("bench")
	for key: String in ["motor", "thermal", "failure", "supply", "gait", "grounds", "readout"]:
		assert_true(cfg.has(key), "bench.json has " + key)


func test_joint_figures_come_from_parts_json() -> void:
	var hip: Dictionary = rig.joints[HIP]
	assert_almost_eq(float(hip["rated_nm"]), 202150.7, 1.0, "hip pitch rated torque is parts.json's")
	assert_almost_eq(float(hip["omega_rated"]), 0.15, 0.001, "rated speed survives the conversion")
	assert_almost_eq(float(hip["stall_nm"]), float(hip["rated_nm"]) * 1.6, 1.0, "peak is rated x the bench factor")
	var knee: Dictionary = rig.joints[KNEE]
	# a linear ram: torque is its force over the moment arm
	assert_almost_eq(float(knee["rated_nm"]), 1014519.26 * 0.11113808, 5.0, "knee torque = ram force x moment arm")
	assert_almost_eq(float(knee["omega_rated"]), 0.025 / 0.11113808, 0.002, "knee speed = ram speed / moment arm")


func test_older_linear_templates_still_resolve() -> void:
	var r := BenchRig.new(Registry.file("bench"))
	r.add_joint("legacy", Registry.entry("parts", "act_linear_heavy_knee"), "")
	var j: Dictionary = r.joints["legacy"]
	assert_almost_eq(float(j["stall_nm"]), 220000.0 * 0.4, 1.0, "peak force x lever arm")
	assert_almost_eq(float(j["omega_nl"]), 0.2 / 0.4, 0.001, "no-load speed over the lever arm")
	assert_gt(float(j["cool_w_per_k"]), 0.0)


func test_torque_limit_falls_with_speed() -> void:
	var stall := rig.limit_nm(HIP, 0.0)
	var half := rig.limit_nm(HIP, float(rig.joints[HIP]["omega_nl"]) * 0.5)
	assert_almost_eq(stall, float(rig.joints[HIP]["stall_nm"]), 1.0, "full torque at standstill")
	assert_almost_eq(half, stall * 0.5, stall * 0.01, "half the no-load speed, half the torque")
	assert_eq(rig.limit_nm(HIP, 10.0), 0.0, "nothing past the no-load speed")
	var rated := float(rig.joints[HIP]["rated_nm"])
	assert_almost_eq(rig.limit_nm(HIP, float(rig.joints[HIP]["omega_rated"])), rated, rated * 0.01, "the rated point is on the line")


func test_power_at_the_rated_point_is_the_parts_figure() -> void:
	var hip: Dictionary = rig.joints[HIP]
	_hold(rig, HIP, 1.0, 0.25, float(hip["omega_rated"]))
	assert_almost_eq(float(hip["elec_w"]), 46650.17 + float(hip["idle_w"]), 60.0, "mechanical + copper heat + idle")
	assert_almost_eq(float(hip["heat_now_w"]), 16327.56, 5.0, "copper heat at rated torque")
	assert_gt(float(hip["current_a"]), 400.0, "hundreds of amps on a 96 V bus")


func test_holding_still_costs_heat_but_no_mechanical_power() -> void:
	_hold(rig, HIP, 0.5, 0.25)
	var hip: Dictionary = rig.joints[HIP]
	assert_eq(float(hip["mech_w"]), 0.0, "no motion, no mechanical power")
	assert_almost_eq(float(hip["heat_now_w"]), 16327.56 * 0.25, 5.0, "copper heat goes with torque squared")


func test_standing_on_four_legs_is_sustainable() -> void:
	# static need on two legs is 0.8 of rated; four legs share it, so 0.4. It must settle below the derate point.
	_hold(rig, HIP, 0.4, 3000.0, 0.0, 0.5)
	_hold(rig, KNEE, 0.4, 3000.0, 0.0, 0.5)
	assert_lt(float(rig.joints[HIP]["temp_c"]), 120.0, "hip holds the stance for ever")
	assert_lt(float(rig.joints[KNEE]["temp_c"]), 120.0, "knee holds the stance for ever")
	assert_eq(rig.status_of(HIP), BenchRig.OK)


func test_holding_a_heavy_load_overheats_and_trips() -> void:
	var t := 0.0
	var dt := 0.25
	var j: Dictionary = rig.joints[KNEE]
	while t < 1200.0 and not bool(j["tripped"]):
		rig.step(dt, {KNEE: {"torque": 0.95 * float(j["rated_nm"]), "omega": 0.0}})
		t += dt
	assert_true(bool(j["tripped"]), "the knee trips from heat")
	assert_between(t, 20.0, 900.0, "within minutes, not instantly and not never")
	assert_eq(rig.limit_nm(KNEE), 0.0, "a tripped joint holds nothing")
	assert_eq(rig.status_of(KNEE), BenchRig.TRIPPED)
	assert_true(rig.events.size() > 0 and str(rig.events[-1]["what"]).begins_with("tripped"), "logged")
	# let it cool with no load
	var cool_s := 0.0
	while cool_s < 3000.0 and bool(j["tripped"]):
		rig.step(0.5, {})
		cool_s += 0.5
	assert_false(bool(j["tripped"]), "back on line once cool")
	assert_lt(float(j["temp_c"]), float(j["derate_c"]), "and below the derate point")


func test_torque_derates_as_it_gets_hot() -> void:
	var j: Dictionary = rig.joints[HIP]
	j["temp_c"] = 120.0
	var full := rig.limit_nm(HIP)
	j["temp_c"] = 137.5
	assert_almost_eq(rig.limit_nm(HIP), full * 0.75, full * 0.01, "half way up the derate band, three quarters of the torque")
	j["temp_c"] = 154.0
	assert_between(rig.limit_nm(HIP), full * 0.5, full * 0.56, "folded back to about half at the cutout")


func test_a_shock_load_breaks_the_joint_until_reset() -> void:
	var j: Dictionary = rig.joints[KNEE]
	rig.step(0.02, {KNEE: {"torque": 3.0 * float(j["stall_nm"]), "omega": 0.0}})
	assert_false(bool(j["failed"]), "a 20 ms spike is survived")
	for i in 3:
		rig.step(0.05, {KNEE: {"torque": 3.0 * float(j["stall_nm"]), "omega": 0.0}})
	assert_true(bool(j["failed"]), "past shock_fail_s it shears")
	assert_eq(rig.limit_nm(KNEE), 0.0)
	rig.step(1.0, {})
	assert_true(bool(j["failed"]), "and stays broken")
	assert_eq(rig.down().size(), 1)
	rig.reset()
	assert_false(bool(j["failed"]), "the bench reset repairs it")
	assert_eq(rig.down().size(), 0)


func test_failures_can_be_switched_off() -> void:
	rig.failures_on = false
	var j: Dictionary = rig.joints[KNEE]
	for i in 10:
		rig.step(0.05, {KNEE: {"torque": 3.0 * float(j["stall_nm"]), "omega": 0.0}})
	assert_false(bool(j["failed"]), "no latch with failures off")
	assert_almost_eq(float(j["torque_nm"]), float(j["stall_nm"]), 1.0, "but the limit still holds")


func test_asking_for_too_much_saturates_it() -> void:
	var j: Dictionary = rig.joints[HIP]
	rig.step(0.1, {HIP: {"torque": 2.0 * float(j["stall_nm"]), "omega": 0.0}})
	assert_eq(rig.status_of(HIP), BenchRig.SATURATED)
	assert_almost_eq(float(j["torque_nm"]), float(j["stall_nm"]), 1.0, "gives what it has")
	assert_gt(float(j["demand_nm"]), float(j["torque_nm"]))


func test_the_bus_sags_under_load_and_slows_the_joints() -> void:
	var all: Array = []
	for leg: String in ["FR", "FL", "RR", "RL"]:
		for kind: String in ["hip_pitch", "knee", "hip_yaw", "ankle"]:
			all.append("jg2_act_%s_%s" % [kind, leg])
	var r := _make_rig(all)
	var idle_v := r.voltage_frac()
	var no_load_speed := r.speed_limit(HIP) if r.has_joint(HIP) else 0.0
	var demands := {}
	for id: String in all:
		var j: Dictionary = r.joints[id]
		demands[id] = {"torque": float(j["rated_nm"]), "omega": float(j["omega_rated"])}
	for i in 4:
		r.step(0.05, demands)
	assert_lt(r.voltage_frac(), idle_v, "heavy current sags the voltage")
	assert_gt(float(r.supply["current_a"]), 2000.0, "thousands of amps at 96 V")
	assert_lt(r.speed_limit(HIP), no_load_speed, "a sagging bus slows the joint")


func test_the_pack_browns_out_when_asked_for_more_than_it_gives() -> void:
	var all: Array = []
	for leg: String in ["FR", "FL", "RR", "RL"]:
		for kind: String in ["hip_pitch", "knee"]:
			all.append("jg2_act_%s_%s" % [kind, leg])
	var r := _make_rig(all)
	r.supply["limit_w"] = 100000.0
	var demands := {}
	for id: String in all:
		var j: Dictionary = r.joints[id]
		demands[id] = {"torque": float(j["rated_nm"]), "omega": float(j["omega_rated"])}
	r.step(0.05, demands)
	r.step(0.05, demands)
	assert_true(bool(r.supply["brownout"]), "more than the limit is a brownout")
	assert_lt(float(r.supply["scale"]), 0.6, "every joint gets a share")
	assert_lt(r.limit_nm(HIP, 0.0), float(r.joints[HIP]["stall_nm"]) * 0.6, "so each can give less")
	assert_lt(float(r.supply["power_w"]), 100001.0, "the pack never gives past its limit")


func test_an_empty_battery_cuts_every_joint() -> void:
	rig.supply["energy_j"] = 100.0
	var j: Dictionary = rig.joints[HIP]
	for i in 40:
		rig.step(0.25, {HIP: {"torque": 0.5 * float(j["rated_nm"]), "omega": 0.0}})
	assert_eq(rig.charge_frac(), 0.0)
	assert_eq(rig.limit_nm(HIP), 0.0, "no charge, no torque")
	assert_eq(rig.status_of(HIP), BenchRig.NO_POWER)


func test_spending_energy_for_a_jump() -> void:
	var before := float(rig.supply["energy_j"])
	var got := rig.spend_j(5.0e6)
	assert_almost_eq(got, 5.0e6, 1.0)
	assert_almost_eq(float(rig.supply["energy_j"]), before - 5.0e6, 1.0)
	assert_almost_eq(rig.spend_j(1.0e12), before - 5.0e6, 1.0, "never more than the pack holds")


# --- the mech on the bench ----------------------------------------------------------------------


func test_standing_on_the_bench_reads_the_static_loads() -> void:
	_spawn()
	await _frames(600)
	assert_true(mech.call("bench_on"), "the bench model is steering the mech")
	assert_eq(int(mech.call("telemetry")["grounded_legs"]), 4, "stands on four legs")
	var hip := _joint("fl", "hip_pitch")
	var knee := _joint("fl", "knee")
	var share := float(hip["torque_nm"]) / float(hip["rated_nm"])
	print("    standing: hip %.0f N m (%.2f of rated), knee %.0f N m (%.2f), bus %.1f V %.1f kW" % [float(hip["torque_nm"]), share, float(knee["torque_nm"]), float(knee["torque_nm"]) / float(knee["rated_nm"]), float(_driver().rig.supply["voltage_v"]), _driver().rig.total_power_w() / 1000.0])
	# parts.json sizes the actuators for B1's 12.25 t export (static_torque_nm is 0.8 of rated on two legs); the
	# game's realistic mass is 5.4 t, so four legs carry it at about 0.15 of rated.
	var want := mech.mass * 9.81 / 4.0
	assert_between(float(hip["torque_nm"]) / (want * 2.7), 0.7, 1.4, "hip torque is the leg's share of the weight over the hip-to-foot reach (about 2.7 m)")
	assert_between(share, 0.1, 0.25, "about 0.15 of the hip's rated torque")
	assert_between(float(knee["torque_nm"]) / float(knee["rated_nm"]), 0.1, 0.25, "and of the knee's")
	assert_eq(_driver().rig.down().size(), 0, "nothing tripped or broken standing")
	assert_gt(_driver().rig.total_power_w(), 5000.0, "holding the body costs real power")
	assert_lt(float(_driver().rig.supply["voltage_v"]), 96.0, "and sags the bus")


func test_game_mode_is_untouched() -> void:
	_spawn()
	Settings.set_value("gameplay.physics_mode", "game", false)
	await _frames(240)
	assert_false(mech.call("bench_on"), "game mode does not use the bench")
	assert_eq(float(_driver().rig.total_power_w()), 0.0, "the rig sees nothing")
	assert_true((mech.call("telemetry")["bench"] as Dictionary).is_empty())


func test_walking_on_the_bench_is_slow_and_costs_power() -> void:
	_spawn()
	await _frames(360)
	var start := mech.global_position
	Input.action_press("move_forward", 1.0)
	await _frames(1800)
	Input.action_release("move_forward")
	var moved := Vector2(mech.global_position.x - start.x, mech.global_position.z - start.z).length()
	var hot: Dictionary = _driver().rig.hottest()
	print("    walked %.1f m in 15 s; peak draw seen in log %.0f kW; hottest %s at %.1f C" % [moved, _peak_kw(), str(hot["id"]), float(hot["temp_c"])])
	assert_gt(moved, 1.0, "it walks")
	assert_lt(moved, 15.0 * 2.0, "but at a crawl")
	assert_lt(absf(rad_to_deg(mech.global_transform.basis.get_euler().x)), 20.0, "without tipping")
	assert_gt(float(hot["temp_c"]), 20.3, "and the joints warm up")
	assert_gt(_peak_kw(), 20.0, "walking draws far more than standing")


func _peak_kw() -> float:
	var best := 0.0
	for row: Dictionary in _driver().log:
		best = maxf(best, float(row["kw"]))
	return best


func test_a_flat_battery_drops_the_machine() -> void:
	_spawn()
	await _frames(360)
	var standing_y := mech.global_position.y
	_driver().rig.supply["energy_j"] = 0.0
	await _frames(480)
	print("    flat battery: body %.2f m -> %.2f m" % [standing_y, mech.global_position.y])
	assert_lt(mech.global_position.y, standing_y - 0.35, "without power the legs fold")
	assert_eq(int(mech.call("telemetry")["grounded_legs"]) >= 0, true)


func test_a_dead_knee_drops_its_corner() -> void:
	_spawn()
	await _frames(360)
	var knee := _joint("fl", "knee")
	knee["failed"] = true
	await _frames(300)
	var force := 0.0
	for leg: Dictionary in mech.get("legs"):
		if str(leg["name"]) == "fl":
			force = float(leg.get("ground_force_n", 0.0))
	assert_lt(force, 2000.0, "the broken leg carries almost nothing")
	var roll := rad_to_deg(mech.global_transform.basis.get_euler().z)
	var pitch := rad_to_deg(mech.global_transform.basis.get_euler().x)
	print("    fl knee failed: fl force %.0f N, pitch %.1f roll %.1f" % [force, pitch, roll])
	assert_gt(absf(roll) + absf(pitch), 1.0, "the body leans onto the other three")


func test_a_hard_landing_breaks_actuators() -> void:
	_spawn(14.0)
	var worst := 0.0
	var low := 99.0
	for i in 900:
		await tree.physics_frame
		for leg: Dictionary in mech.get("legs"):
			worst = maxf(worst, float(leg.get("ground_demand_n", 0.0)))
		low = minf(low, mech.global_position.y)
	print("    max demand %.0f N, lowest body y %.2f, vy now %.2f" % [worst, low, mech.linear_velocity.y])
	var down: PackedStringArray = _driver().rig.down()
	print("    dropped 14 m: down = %s" % str(down))
	assert_gt(down.size(), 0, "a drop from 14 m is past what the joints can take")


func test_the_jump_is_paid_for_from_the_battery() -> void:
	_spawn()
	await _frames(360)
	var before := float(_driver().rig.supply["energy_j"])
	var got: float = _driver().call("bill_jump", 3.0, mech.mass)
	assert_almost_eq(got, 3.0, 0.001, "a full pack gives the whole jump")
	assert_lt(float(_driver().rig.supply["energy_j"]), before - 10000.0, "and it costs energy")
	_driver().rig.supply["energy_j"] = 1000.0
	var weak: float = _driver().call("bill_jump", 3.0, mech.mass)
	assert_lt(weak, 1.0, "a nearly flat pack cannot launch it")


func test_reset_puts_the_bench_back() -> void:
	_spawn()
	await _frames(240)
	_joint("fr", "knee")["failed"] = true
	_driver().rig.supply["energy_j"] = 10.0
	_driver().call("reset")
	assert_eq(_driver().rig.down().size(), 0)
	assert_almost_eq(_driver().rig.charge_frac(), 1.0, 0.001, "full pack at reset")


# --- the two bench grounds ----------------------------------------------------------------------


func _open_ground(map_id: String) -> Node3D:
	Settings.set_value("gameplay.physics_mode", "game", false)
	var entry := Registry.entry("maps", map_id)
	assert_true(Game.can_start(map_id), "%s can be started from the menu" % map_id)
	var level: Node3D = (load(str(entry["scene"])) as PackedScene).instantiate()
	tree.root.add_child(level)
	return level


func _close_ground(level: Node3D) -> void:
	level.free()
	Game.level = null
	mech = null


func test_the_flat_pad_spawns_a_mech_in_bench_mode_and_it_stands() -> void:
	var level := _open_ground("test_bench_flat")
	mech = level.get("mech")
	assert_true(mech != null, "a mech is spawned")
	assert_eq(Settings.get_s("gameplay.physics_mode"), "bench", "the map forces test bench physics")
	await _frames(600)
	assert_true(mech.call("bench_on"), "the actuator model is steering it")
	assert_eq(int(mech.call("telemetry")["grounded_legs"]), 4, "stands on four legs on the pad")
	assert_between(mech.global_position.y, 0.5, 5.0, "on top of the pad, not through it (%.2f m)" % mech.global_position.y)
	assert_eq(float(level.call("ground_height", 30.0, -20.0)), 0.0, "the pad is level")
	_close_ground(level)
	assert_eq(Settings.get_s("gameplay.physics_mode"), "game", "leaving the map gives the physics mode back")


func test_the_flat_pad_has_marks_and_two_ramps() -> void:
	var level := _open_ground("test_bench_flat")
	var step := float(Registry.file("bench")["grounds"]["flat"]["mark_every_m"])
	var strips := 0
	var ramps := 0
	for n: Node in level.get_children():
		if n is MeshInstance3D:
			strips += 1
		elif n is StaticBody3D and absf((n as Node3D).rotation.x) > 0.05:
			ramps += 1
	assert_eq(ramps, 2, "two ramps")
	assert_gt(strips, int(400.0 / step), "painted marks every %.0f m both ways (%d strips)" % [step, strips])
	_close_ground(level)


func test_the_rough_field_is_rough_but_flat_at_the_spawn() -> void:
	var level := _open_ground("test_bench_rough")
	var spec: Dictionary = Registry.file("bench")["grounds"]["rough"]
	var lo := INF
	var hi := -INF
	for k in 400:
		var h := float(level.call("ground_height", -190.0 + k * 0.95, -120.0 + 0.37 * k))
		lo = minf(lo, h)
		hi = maxf(hi, h)
	print("    rough field: %.2f to %.2f m on a 400-point cross (set amplitude %.2f m)" % [lo, hi, float(spec["amplitude_m"])])
	assert_gt(hi - lo, 0.4, "the field has relief")
	assert_lt(hi - lo, float(spec["amplitude_m"]) * 1.2, "within the set amplitude")
	assert_lt(absf(float(level.call("ground_height", 0.0, 0.0))), 0.01, "the spawn is at height zero")
	var bodies := 0
	for n: Node in level.get_children():
		if n is StaticBody3D and n.name != "TerrainBody":
			bodies += 1
	assert_gt(bodies, int(spec["boulders"]) + int(spec["steps"]) - 1, "boulders and steps are solid bodies (%d)" % bodies)
	_close_ground(level)


func test_the_rough_field_holds_the_mech_up() -> void:
	var level := _open_ground("test_bench_rough")
	mech = level.get("mech")
	await _frames(600)
	assert_true(mech.call("bench_on"), "bench physics on the rough ground")
	assert_gt(int(mech.call("telemetry")["grounded_legs"]), 2, "standing on the field")
	assert_between(mech.global_position.y, 0.5, 5.0, "on the surface (%.2f m)" % mech.global_position.y)
	_close_ground(level)


func test_the_bench_grounds_load_whatever_design_the_setting_names() -> void:
	Settings.set_value("bench.design", "standin", false)
	var level := _open_ground("test_bench_flat")
	mech = level.get("mech")
	assert_eq(str(mech.get("def").get("id", "standin")), "standin", "the stand-in is on the pad")
	_close_ground(level)
