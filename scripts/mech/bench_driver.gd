extends Node
## Test bench mode on a mech (lane B6): turns the mech's real ground reaction into joint torque and
## speed, feeds BenchRig, and gives the mech back what its actuators can really do. A child of the mech
## (standin_mech.gd _ready adds it); it does nothing while Settings gameplay.physics_mode is "game".
##
## Each leg is a planar chain, hip -> knee -> ankle -> sole. The ground pushes on the sole (up with the
## spring force, along the ground with this leg's share of the drive force), so the torque on a joint is
## (sole - joint) x force along that joint's axis: the hip and knee pitch about the axis across the leg's
## vertical plane, the hip yaw about the body's up. A leg in the air only carries its own weight.
## Joint speeds are the finite-differenced joint angles of the same pose the legs are drawn with.
##
## What the mech gets back: leg_force_cap() (a leg cannot push harder than its weakest joint can hold),
## drive_force_cap() (nor push the body along harder than the joints have left), speed_factor() and
## min_swing_s() (the joints' speed limits slow the steps), bill_jump() (a jump is paid for in battery).

const Rig := preload("res://scripts/mech/bench_rig.gd")
const HoldKinds := ["hip_pitch", "knee"]
const MIN_LEVER_M := 0.08
const GRAVITY := 9.81
const SMOOTH_S := 0.12

var mech: RigidBody3D
var rig: BenchRig
var active := false
var leg_joints: Dictionary = {}  # leg name -> {joint kind -> actuator id}
var _angle: Dictionary = {}  # actuator id -> last joint angle, rad
var _omega: Dictionary = {}  # actuator id -> smoothed joint speed, rad/s
var _demand: Dictionary = {}  # actuator id -> {"torque": N m, "omega": rad/s} for this tick
var _hud: CanvasLayer
var _log_s := 0.0
var drive_force_n := Vector3.ZERO  # the drive's push on the body this tick (set by the mech), N
var log: Array = []  # [{"t", "speed", "kw", "volts", "charge", "hottest", "hottest_c", "down"}]


func _ready() -> void:
	mech = get_parent() as RigidBody3D
	rig = Rig.new(Registry.file("bench"))
	var def: Dictionary = mech.get("def")
	for leg: Dictionary in mech.get("legs"):
		var name := str(leg["name"])
		leg_joints[name] = {}
		for id: String in def.get("legs", {}).get(name, {}).get("actuators", []):
			var part := Registry.entry("parts", id)
			if not part.has("bench") or str(part.get("joint", "")) == "":
				continue
			rig.add_joint(id, part, name)
			leg_joints[name][str(part["joint"])] = id
	apply_settings()
	Settings.changed.connect(_on_setting_changed)


func _on_setting_changed(key: String, _value: Variant) -> void:
	if key.begins_with("bench."):
		apply_settings()


## Settings > Gameplay > Physics > Test bench. The battery level only matters at reset.
func apply_settings() -> void:
	rig.failures_on = Settings.get_b("bench.failures")
	rig.cooling_scale = Settings.get_f("bench.cooling")
	rig.supply["capacity_j"] = Settings.get_f("bench.battery_kwh") * 3.6e6
	rig.supply["energy_j"] = minf(float(rig.supply["energy_j"]), float(rig.supply["capacity_j"]))


func start_charge() -> void:
	rig.supply["energy_j"] = float(rig.supply["capacity_j"]) * Settings.get_f("bench.charge_pct") / 100.0


func reset() -> void:
	rig.reset()
	apply_settings()
	start_charge()
	_angle.clear()
	_omega.clear()


func is_active() -> bool:
	return active


func _unhandled_input(event: InputEvent) -> void:
	if not active or not mech.get("is_player"):
		return
	if event.is_action_pressed("bench_reset"):
		reset()
	elif event.is_action_pressed("bench_readouts"):
		Settings.set_value("bench.hud", not Settings.get_b("bench.hud"))
		if _hud != null:
			_hud.visible = Settings.get_b("bench.hud")


# --- geometry -----------------------------------------------------------------------------------


## World positions of a leg's joints and its sole, and the unit axis its pitch joints turn about.
func _pose(leg: Dictionary) -> Dictionary:
	var xf := mech.global_transform
	var hip := xf * (leg["pivot"] as Vector3)
	var knee := xf * (leg.get("knee_local", leg["pivot"]) as Vector3)
	var ankle := xf * (leg.get("ankle_local", leg["pivot"]) as Vector3)
	var sole: Vector3 = leg["foot"]
	var across := Vector3.UP.cross(_flat(sole - hip))
	var axis := across.normalized() if across.length() > 0.05 else xf.basis.x
	return {"hip": hip, "knee": knee, "ankle": ankle, "sole": sole, "axis": axis}


static func _flat(v: Vector3) -> Vector3:
	return Vector3(v.x, 0.0, v.z)


## Torque (N m, signed) a force at the sole puts on joint `kind`.
static func joint_torque(pose: Dictionary, kind: String, force: Vector3) -> float:
	var sole: Vector3 = pose["sole"]
	match kind:
		"hip_yaw":
			return (sole - (pose["hip"] as Vector3)).cross(force).dot(Vector3.UP)
		"hip_pitch":
			return (sole - (pose["hip"] as Vector3)).cross(force).dot(pose["axis"])
		"knee":
			return (sole - (pose["knee"] as Vector3)).cross(force).dot(pose["axis"])
		"ankle":
			return (sole - (pose["ankle"] as Vector3)).cross(force).dot(pose["axis"])
	return 0.0


## Torque on `kind` from the leg's own weight (a leg hanging in the air): the thigh's and shin's
## centres of mass sit half way along them.
func _weight_torque(pose: Dictionary, kind: String, leg_mass: float) -> float:
	var lower_share := float(rig.cfg.get("motor", {}).get("lower_mass_share", 0.45))
	var down := Vector3.DOWN * GRAVITY
	var hip: Vector3 = pose["hip"]
	var knee: Vector3 = pose["knee"]
	var ankle: Vector3 = pose["ankle"]
	var upper_com := (hip + knee) * 0.5
	var lower_com := (knee + ankle) * 0.5
	var m_low := leg_mass * lower_share
	var m_up := leg_mass - m_low
	match kind:
		"hip_pitch":
			return ((upper_com - hip).cross(down * m_up) + (lower_com - hip).cross(down * m_low)).dot(pose["axis"])
		"knee":
			return (lower_com - knee).cross(down * m_low).dot(pose["axis"])
	return 0.0


## Joint angle for the speed estimate, rad (any monotonic measure of the joint's turn will do).
func _joint_angle(leg: Dictionary, kind: String) -> float:
	var pivot: Vector3 = leg["pivot"]
	var knee: Vector3 = leg.get("knee_local", pivot)
	var ankle: Vector3 = leg.get("ankle_local", pivot)
	match kind:
		"hip_yaw":
			return atan2(knee.x - pivot.x, -(knee.z - pivot.z))
		"hip_pitch":
			return atan2(Vector2(knee.x - pivot.x, knee.z - pivot.z).length(), -(knee.y - pivot.y))
		"knee":
			return (pivot - knee).angle_to(ankle - knee)
		"ankle":
			return atan2(Vector2(ankle.x - knee.x, ankle.z - knee.z).length(), -(ankle.y - knee.y))
	return 0.0


# --- per tick -----------------------------------------------------------------------------------


func _physics_process(dt: float) -> void:
	active = mech.has_method("bench_mode") and bool(mech.call("bench_mode"))
	if not active or dt <= 0.0:
		return
	var n_loaded := 0
	for leg: Dictionary in mech.get("legs"):
		if bool(leg.get("loaded", false)):
			n_loaded += 1
	var share := drive_force_n / maxf(n_loaded, 1)
	_demand.clear()
	for leg: Dictionary in mech.get("legs"):
		var name := str(leg["name"])
		var joints: Dictionary = leg_joints.get(name, {})
		if joints.is_empty():
			continue
		var pose := _pose(leg)
		var loaded := bool(leg.get("loaded", false))
		var force := Vector3.UP * float(leg.get("ground_demand_n", 0.0)) + share if loaded else Vector3.ZERO
		var leg_mass: float = mech.call("_leg_mass", leg)
		for kind: String in joints:
			var id: String = joints[kind]
			var angle := _joint_angle(leg, kind)
			var rate := 0.0
			if _angle.has(id):
				rate = wrapf(angle - float(_angle[id]), -PI, PI) / dt
			_angle[id] = angle
			_omega[id] = lerpf(float(_omega.get(id, 0.0)), rate, minf(dt / SMOOTH_S, 1.0))
			var torque := joint_torque(pose, kind, force) if loaded else _weight_torque(pose, kind, leg_mass)
			_demand[id] = {"torque": torque, "omega": float(_omega[id])}
	rig.step(dt, _demand)
	_log_s += dt
	if _log_s >= float(rig.cfg.get("readout", {}).get("log_interval_s", 0.5)):
		_log_s = 0.0
		_log_row()
	if mech.get("is_player") and _hud == null and Settings.get_b("bench.hud") and DisplayServer.get_name() != "headless":
		_hud = (load("res://scripts/ui/bench_hud.gd") as GDScript).new()
		_hud.call("watch", self)
		mech.add_child(_hud)


func _log_row() -> void:
	var hot := rig.hottest()
	log.append(
		{
			"t": snappedf(rig.time_s, 0.1),
			"speed": snappedf(mech.linear_velocity.length(), 0.01),
			"kw": snappedf(rig.total_power_w() / 1000.0, 0.1),
			"volts": snappedf(float(rig.supply["voltage_v"]), 0.1),
			"charge": snappedf(rig.charge_frac(), 0.001),
			"hottest": str(hot.get("id", "")),
			"hottest_c": snappedf(float(hot.get("temp_c", 0.0)), 0.1),
			"down": Array(rig.down()),
		}
	)
	if log.size() > 2400:
		log.pop_front()


# --- what the mech asks ------------------------------------------------------------------------------


## The most a leg can push up with, N, from what its pitch joints can give at the current pose; the
## force the leg is asked for (and what it was capped from) is kept on the leg for the readouts.
## `extending`: the leg is pushing the body up, so its motors drive against their speed limit; a leg
## being compressed is back-driven by the load, which a motor holds at full torque whatever the speed.
func leg_force_cap(leg: Dictionary, extending: bool = true) -> float:
	var joints: Dictionary = leg_joints.get(str(leg["name"]), {})
	if joints.is_empty():
		return INF
	var pose := _pose(leg)
	var cap := INF
	for kind: String in HoldKinds:
		if not joints.has(kind):
			continue
		var id: String = joints[kind]
		var lever := absf(joint_torque(pose, kind, Vector3.UP))
		if lever < MIN_LEVER_M:
			continue
		cap = minf(cap, rig.limit_nm(id, float(_omega.get(id, 0.0)) if extending else 0.0) / lever)
	return cap


## What the ground asks of a leg, N: the spring force, or when the leg has closed up against its end
## stop (compression past failure.travel_frac of its rest length) the force of stopping what is
## still moving down over failure.stop_m. Standing and walking never get there; a hard landing does.
func shock_demand(spring_n: float, compression_m: float, rest_m: float, v_down: float, leg_mass_kg: float) -> float:
	var f: Dictionary = rig.cfg.get("failure", {})
	if compression_m < rest_m * float(f.get("travel_frac", 0.6)) or v_down <= 0.0:
		return spring_n
	return maxf(spring_n, 0.5 * leg_mass_kg * v_down * v_down / maxf(float(f.get("stop_m", 0.06)), 0.005))


## The most horizontal push the loaded legs can add to what they already carry, N: per leg what its
## joints have left over (limit minus the torque the weight takes) over the lever of a push along
## the drive's direction, summed over the legs on the ground.
func drive_force_cap(direction: Vector3) -> float:
	var dir := _flat(direction).normalized()
	if dir.length() < 0.5:
		return INF
	var total := 0.0
	for leg: Dictionary in mech.get("legs"):
		if not bool(leg.get("loaded", false)):
			continue
		var joints: Dictionary = leg_joints.get(str(leg["name"]), {})
		if joints.is_empty():
			return INF
		var pose := _pose(leg)
		var weight := Vector3.UP * float(leg.get("ground_force_n", 0.0))
		var best := INF
		for kind: String in ["hip_pitch", "knee", "hip_yaw"]:
			if not joints.has(kind):
				continue
			var id: String = joints[kind]
			var lever := absf(joint_torque(pose, kind, dir))
			if lever < MIN_LEVER_M:
				continue
			var left := rig.limit_nm(id, float(_omega.get(id, 0.0))) - absf(joint_torque(pose, kind, weight))
			best = minf(best, maxf(left, 0.0) / lever)
		total += best if best < INF else 0.0
	return total if total > 0.0 else 0.0


## Share of its nominal swing speed the joints have, from the slowest of the legs' hip pitch joints.
func speed_factor() -> float:
	var floor_share := float(rig.cfg.get("gait", {}).get("sag_floor", 0.1))
	var best := 1.0
	for name: String in leg_joints:
		var joints: Dictionary = leg_joints[name]
		for kind: String in ["hip_pitch", "knee"]:
			if joints.has(kind):
				var j: Dictionary = rig.joints[joints[kind]]
				best = minf(best, rig.speed_limit(joints[kind]) / maxf(float(j["omega_nl"]), 0.0001))
	return maxf(best, floor_share)


## The least time a step's swing may take: the foot must travel `stride_m` at the hip's pace.
func min_swing_s(stride_m: float, reach_m: float) -> float:
	var share := float(rig.cfg.get("gait", {}).get("step_speed_share", 0.5))
	var slowest := INF
	for name: String in leg_joints:
		var joints: Dictionary = leg_joints[name]
		if joints.has("hip_pitch"):
			slowest = minf(slowest, rig.speed_limit(joints["hip_pitch"]))
	if slowest == INF:
		return 0.0
	var foot_m_s := maxf(slowest * share * reach_m, 0.02)
	return stride_m / foot_m_s


## Mechanical power the drive may use, W: what the bus gives less what the legs hold the body up with.
func drive_power_w() -> float:
	var sup: Dictionary = rig.cfg.get("supply", {})
	var mech_w := 0.0
	for id: String in rig.joints:
		mech_w += float(rig.joints[id]["mech_w"])
	var holding_w := maxf(rig.total_power_w() - mech_w, 0.0)
	return maxf(float(rig.supply["limit_w"]) - holding_w, 0.0) * float(sup.get("drive_efficiency", 0.6))


## A jump is paid for from the battery: kinetic energy over the legs' efficiency. Returns the launch
## speed the pack could really give (the same, or less on a low pack).
func bill_jump(speed: float, mass: float) -> float:
	var eff := float(rig.cfg.get("supply", {}).get("jump_efficiency", 0.6))
	var need := 0.5 * mass * speed * speed / maxf(eff, 0.05)
	var got := rig.spend_j(need)
	return speed * sqrt(got / maxf(need, 1.0))


func telemetry() -> Dictionary:
	var hot := rig.hottest()
	return {
		"charge_pct": snappedf(rig.charge_frac() * 100.0, 0.1),
		"volts": snappedf(float(rig.supply["voltage_v"]), 0.1),
		"kw": snappedf(rig.total_power_w() / 1000.0, 0.1),
		"amps": snappedf(float(rig.supply["current_a"]), 1.0),
		"brownout": bool(rig.supply["brownout"]),
		"hottest": str(hot.get("id", "")),
		"hottest_c": snappedf(float(hot.get("temp_c", 0.0)), 0.1),
		"down": Array(rig.down()),
	}
