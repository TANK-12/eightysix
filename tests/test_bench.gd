extends "res://tests/lib/test_case.gd"
## Lane B6: test bench mode. The rig (scripts/mech/bench_rig.gd) is checked on its own first: torque
## limits, power, heat, thermal cutout, shock failure and the battery, with the Juggernaut's real
## parts.json actuators and data/bench.json. The mech-level checks follow further down.

const HIP := "jg2_act_hip_pitch_FR"
const KNEE := "jg2_act_knee_FR"
const YAW := "jg2_act_hip_yaw_FR"

var rig: BenchRig


func before_each() -> void:
	rig = _make_rig()


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
	rig.step(0.05, {KNEE: {"torque": 3.0 * float(j["stall_nm"]), "omega": 0.0}})
	assert_false(bool(j["failed"]), "a 50 ms spike is survived")
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
