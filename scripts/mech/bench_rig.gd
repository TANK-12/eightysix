class_name BenchRig
extends RefCounted
## Test bench mode's actuator and power model (lane B6; physics supplement, point 5). Pure logic, no
## nodes: the mech's BenchDriver measures each joint's torque and speed and calls step(); the rig
## answers what every joint can still give (limit_nm) and keeps the bus, heat and failure state.
##
## Per joint, from its parts.json "bench" figures and data/bench.json:
##   torque limit  = stall torque x thermal derate x power scale x (1 - |speed| / no-load speed),
##                   the no-load speed following the bus voltage (back-EMF);
##   electrical    = mechanical power + copper heat + idle, copper heat = heat_w x (torque / rated)^2;
##   temperature   = integral of (copper heat - cooling x (T - ambient)) / thermal mass;
##   failure       = thermal cutout (resets when cool), or a shock past shock_fail_factor x peak torque
##                   (latched until reset()).
## The bus is one battery with an internal resistance: heavy current sags the voltage and slows every
## joint, more power than the pack can give browns it out, and an empty pack cuts everything.

const OK := "ok"
const WARM := "warm"
const SATURATED := "saturated"
const TRIPPED := "tripped"
const FAILED := "failed"
const NO_POWER := "no power"

var cfg: Dictionary = {}
var joints: Dictionary = {}  # actuator id -> joint dictionary (see joint_from_part)
var supply: Dictionary = {}
var failures_on := true
var cooling_scale := 1.0
var time_s := 0.0
var events: Array = []  # [{"t": s, "joint": id, "what": text}], newest last, capped


## cfg: the data/bench.json top-level dictionary.
func _init(config: Dictionary = {}) -> void:
	cfg = config
	supply = new_supply(config.get("supply", {}))


static func new_supply(s: Dictionary) -> Dictionary:
	var capacity_j := float(s.get("capacity_kwh", 60.0)) * 3.6e6
	return {
		"capacity_j": capacity_j,
		"energy_j": capacity_j,
		"voltage_v": float(s.get("nominal_v", 96.0)),
		"current_a": 0.0,
		"power_w": 0.0,
		"limit_w": float(s.get("max_discharge_kw", 400.0)) * 1000.0,
		"scale": 1.0,
		"brownout": false,
	}


## Normalises a parts.json actuator entry into the joint figures the rig runs on (torque space).
static func joint_from_part(id: String, part: Dictionary, config: Dictionary, leg: String = "") -> Dictionary:
	var b: Dictionary = part.get("bench", {})
	var motor: Dictionary = config.get("motor", {})
	var th: Dictionary = config.get("thermal", {})
	var pf := float(motor.get("peak_torque_factor", 1.6))
	var rated := 0.0
	var omega_nl := 0.0
	var stall := 0.0
	if b.has("rated_torque_nm"):
		rated = float(b["rated_torque_nm"])
		omega_nl = float(b.get("speed_rad_s", 0.1)) * pf / (pf - 1.0)
	elif b.has("rated_force_n"):
		var arm := maxf(float(b.get("moment_arm_m", b.get("lever_arm_m", 0.3))), 0.001)
		rated = float(b["rated_force_n"]) * arm
		omega_nl = float(b.get("speed_m_s", 0.05)) / arm * pf / (pf - 1.0)
	else:
		# The older linear templates: continuous and peak force over a lever arm, no-load speed given.
		var arm := maxf(float(b.get("lever_arm_m", 0.3)), 0.001)
		rated = float(b.get("continuous_force_n", float(b.get("peak_force_n", 0.0)) / pf)) * arm
		stall = float(b.get("peak_force_n", rated / arm * pf)) * arm
		omega_nl = float(b.get("no_load_speed_m_s", 0.1)) / arm
	if stall <= 0.0:
		stall = rated * pf
	rated = maxf(rated, 1.0)
	var omega_rated := omega_nl * (1.0 - rated / maxf(stall, rated + 1.0))
	var p_in := float(b.get("power_w", b.get("rated_power_w", rated * omega_rated)))
	var heat := float(b.get("heat_w", p_in * float(motor.get("fallback_heat_share", 0.35))))
	var max_c := float(b.get("max_winding_c", th.get("max_winding_c", 155.0)))
	var derate_c := float(b.get("derate_from_c", th.get("derate_from_c", 120.0)))
	var ambient := float(th.get("ambient_c", 20.0))
	var cool := float(b.get("cooling_w_per_k", heat * float(th.get("cooling_share", 0.5)) / maxf(max_c - ambient, 1.0)))
	return {
		"id": id,
		"joint": str(part.get("joint", "")),
		"leg": leg,
		"label": str(part.get("label", id)),
		"rated_nm": rated,
		"stall_nm": stall,
		"omega_rated": omega_rated,
		"omega_nl": omega_nl,
		"heat_w": heat,
		"power_in_w": p_in,
		"idle_w": float(motor.get("idle_w", 80.0)),
		"thermal_mass": maxf(float(b.get("thermal_mass_j_per_k", 15000.0)), 1.0),
		"cool_w_per_k": cool,
		"max_c": max_c,
		"derate_c": derate_c,
		"reset_c": derate_c - float(th.get("reset_below_derate_c", 15.0)),
		"temp_c": ambient,
		# live state
		"demand_nm": 0.0,
		"torque_nm": 0.0,
		"omega": 0.0,
		"limit_nm": stall,
		"mech_w": 0.0,
		"elec_w": 0.0,
		"heat_now_w": 0.0,
		"current_a": 0.0,
		"status": OK,
		"tripped": false,
		"failed": false,
		"over_s": 0.0,
		"stall_s": 0.0,
		"peak_nm": 0.0,
	}


func add_joint(id: String, part: Dictionary, leg: String = "") -> void:
	joints[id] = joint_from_part(id, part, cfg, leg)


func has_joint(id: String) -> bool:
	return joints.has(id)


## Bus voltage as a share of nominal (the motors' no-load speed follows it).
func voltage_frac() -> float:
	return float(supply["voltage_v"]) / maxf(float(cfg.get("supply", {}).get("nominal_v", 96.0)), 1.0)


func charge_frac() -> float:
	return float(supply["energy_j"]) / maxf(float(supply["capacity_j"]), 1.0)


## 1 up to the derate point, falling to the floor at the cutout temperature (where it trips).
func thermal_factor(j: Dictionary) -> float:
	var floor_share := float(cfg.get("thermal", {}).get("derate_floor", 0.5))
	var past := clampf((float(j["temp_c"]) - float(j["derate_c"])) / maxf(float(j["max_c"]) - float(j["derate_c"]), 1.0), 0.0, 1.0)
	return lerpf(1.0, floor_share, past)


## The torque this joint can give right now while moving at `omega` rad/s.
func limit_nm(id: String, omega: float = 0.0, with_bus_share: bool = true) -> float:
	var j: Dictionary = joints.get(id, {})
	if j.is_empty() or bool(j["tripped"]) or bool(j["failed"]):
		return 0.0
	var nl := float(j["omega_nl"]) * clampf(voltage_frac(), 0.0, 1.2)
	var speed_term := clampf(1.0 - absf(omega) / maxf(nl, 0.0001), 0.0, 1.0)
	return float(j["stall_nm"]) * thermal_factor(j) * (float(supply["scale"]) if with_bus_share else 1.0) * speed_term


## The joint's fastest swing right now (no load), rad/s: slower on a sagging bus or a hot winding.
func speed_limit(id: String) -> float:
	var j: Dictionary = joints.get(id, {})
	if j.is_empty() or bool(j["tripped"]) or bool(j["failed"]):
		return 0.0
	return float(j["omega_nl"]) * clampf(voltage_frac(), 0.0, 1.2) * thermal_factor(j) * float(supply["scale"])


func status_of(id: String) -> String:
	return str(joints.get(id, {}).get("status", OK))


## One tick. demands: actuator id -> {"torque": N m (signed, what the load asks), "omega": rad/s}.
## Joints that are not named are idle (zero demand, zero speed).
func step(dt: float, demands: Dictionary) -> void:
	if dt <= 0.0:
		return
	time_s += dt
	var th: Dictionary = cfg.get("thermal", {})
	var fail: Dictionary = cfg.get("failure", {})
	var sup: Dictionary = cfg.get("supply", {})
	var ambient := float(th.get("ambient_c", 20.0))
	var total_w := 0.0
	var wanted_w := 0.0
	var alive := charge_frac() > 0.0
	for id: String in joints:
		var j: Dictionary = joints[id]
		var d: Dictionary = demands.get(id, {})
		var want := absf(float(d.get("torque", 0.0)))
		var omega := float(d.get("omega", 0.0))
		var lim := limit_nm(id, omega) if alive else 0.0
		j["limit_nm"] = lim
		j["demand_nm"] = want
		j["omega"] = omega
		j["peak_nm"] = maxf(float(j["peak_nm"]), want)
		var gives := minf(want, lim)
		j["torque_nm"] = gives
		var powered := not bool(j["tripped"]) and not bool(j["failed"]) and alive
		var signed_mech := float(d.get("torque", 0.0)) * omega
		var mech := maxf(gives * absf(omega), 0.0) if (signed_mech >= 0.0) else 0.0
		var ratio := gives / float(j["rated_nm"])
		var heat := float(j["heat_w"]) * ratio * ratio if powered else 0.0
		var elec := (mech + heat + float(j["idle_w"])) if powered else 0.0
		if powered and signed_mech < 0.0:
			elec = maxf(elec - gives * absf(omega) * float(sup.get("regen_share", 0.0)), 0.0)
		j["mech_w"] = mech
		j["heat_now_w"] = heat
		j["elec_w"] = elec
		total_w += elec
		if powered:
			# what it would draw with the whole bus to itself, so the bus share does not chatter tick to tick
			var full := minf(want, limit_nm(id, omega, false))
			var full_ratio := full / float(j["rated_nm"])
			wanted_w += float(j["heat_w"]) * full_ratio * full_ratio + (full * absf(omega) if signed_mech >= 0.0 else 0.0) + float(j["idle_w"])
		# temperature
		var cool := float(j["cool_w_per_k"]) * cooling_scale * (float(j["temp_c"]) - ambient)
		j["temp_c"] = float(j["temp_c"]) + (heat - cool) * dt / float(j["thermal_mass"])
		# stall and shock
		if want > lim * 1.001 and want > 1.0:
			j["stall_s"] = float(j["stall_s"]) + dt
		else:
			j["stall_s"] = 0.0
		if want > float(j["stall_nm"]) * float(fail.get("shock_fail_factor", 2.2)):
			j["over_s"] = float(j["over_s"]) + dt
		else:
			j["over_s"] = 0.0
		_update_status(j, fail)
	_step_supply(dt, total_w, wanted_w, sup)
	for id: String in joints:
		var j: Dictionary = joints[id]
		j["current_a"] = float(j["elec_w"]) / maxf(float(supply["voltage_v"]), 1.0)


func _update_status(j: Dictionary, fail: Dictionary) -> void:
	var id := str(j["id"])
	if not bool(j["failed"]) and failures_on and float(j["over_s"]) >= float(fail.get("shock_fail_s", 0.08)):
		j["failed"] = true
		_event(id, "failed: shock load %.0f kN m is past %.1f x its peak" % [float(j["peak_nm"]) / 1000.0, float(fail.get("shock_fail_factor", 2.2))])
	if failures_on and not bool(j["tripped"]) and float(j["temp_c"]) >= float(j["max_c"]):
		j["tripped"] = true
		_event(id, "tripped: winding reached %.0f C" % float(j["temp_c"]))
	elif bool(j["tripped"]) and float(j["temp_c"]) <= float(j["reset_c"]):
		j["tripped"] = false
		_event(id, "back on line at %.0f C" % float(j["temp_c"]))
	var s := OK
	if bool(j["failed"]):
		s = FAILED
	elif bool(j["tripped"]):
		s = TRIPPED
	elif charge_frac() <= 0.0:
		s = NO_POWER
	elif float(j["stall_s"]) > 0.0:
		s = SATURATED
	elif float(j["temp_c"]) >= float(j["derate_c"]):
		s = WARM
	j["status"] = s


func _step_supply(dt: float, total_w: float, wanted_w: float, sup: Dictionary) -> void:
	var nominal := float(sup.get("nominal_v", 96.0))
	var r := float(sup.get("internal_mohm", 1.0)) / 1000.0
	var empty := float(sup.get("empty_v_frac", 0.8))
	var open_v := nominal * lerpf(empty, 1.0, clampf(charge_frac() * 1.5, 0.0, 1.0))
	var best := open_v * open_v / (4.0 * r)  # the most power a source with this resistance can pass
	var limit := minf(float(supply["limit_w"]), best * 0.98)
	var drawn := minf(total_w, limit)
	var disc := maxf(open_v * open_v - 4.0 * r * drawn, 0.0)
	var volts := (open_v + sqrt(disc)) / 2.0
	supply["voltage_v"] = volts
	supply["power_w"] = drawn
	supply["current_a"] = drawn / maxf(volts, 1.0)
	var over := wanted_w > limit * 1.0001
	supply["brownout"] = over or volts < nominal * float(sup.get("min_v_frac", 0.7))
	# the next tick's joints get the share the bus can give
	supply["scale"] = clampf(limit / maxf(wanted_w, 1.0), 0.0, 1.0) if over else 1.0
	supply["energy_j"] = maxf(float(supply["energy_j"]) - drawn * dt, 0.0)
	if charge_frac() <= 0.0:
		supply["scale"] = 0.0
		if not supply.get("flat_logged", false):
			supply["flat_logged"] = true
			_event("battery", "empty")


## Spends `joules` from the pack at once (a jump's launch); returns how much the pack really gave.
func spend_j(joules: float) -> float:
	var got := minf(joules, float(supply["energy_j"]))
	supply["energy_j"] = float(supply["energy_j"]) - got
	return got


## Total electrical draw this tick, W.
func total_power_w() -> float:
	return float(supply["power_w"])


## Back on the stand: failures cleared, windings at ambient, battery full.
func reset() -> void:
	var th: Dictionary = cfg.get("thermal", {})
	for id: String in joints:
		var j: Dictionary = joints[id]
		j["temp_c"] = float(th.get("ambient_c", 20.0))
		j["tripped"] = false
		j["failed"] = false
		j["over_s"] = 0.0
		j["stall_s"] = 0.0
		j["peak_nm"] = 0.0
		j["status"] = OK
	supply = new_supply(cfg.get("supply", {}))
	events.clear()
	_event("bench", "reset")


func hottest() -> Dictionary:
	var best: Dictionary = {}
	for id: String in joints:
		if best.is_empty() or float(joints[id]["temp_c"]) > float(best["temp_c"]):
			best = joints[id]
	return best


## Ids of every joint that is failed or tripped.
func down() -> PackedStringArray:
	var out := PackedStringArray()
	for id: String in joints:
		if bool(joints[id]["failed"]) or bool(joints[id]["tripped"]):
			out.append(id)
	return out


func _event(id: String, what: String) -> void:
	events.append({"t": snappedf(time_s, 0.01), "joint": id, "what": what})
	if events.size() > 40:
		events.pop_front()
