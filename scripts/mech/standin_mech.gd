extends RigidBody3D
## Lane A1's stand-in walker: game-mode "magic motors" on the same data path as the real Juggernaut.
## A spring per leg on a ray cast holds the body up; drive and turn forces are capped by grip; the
## brake plus a hard turn breaks traction into the skid, the fast combat turn; the jump is
## hold-to-charge (the body crouches, compressing the springs) with no control once airborne; the
## body tilts on its legs to aim (the gun never moves on its own). Legs are two-bone IK that step when
## their foot drifts too far, and their hitboxes follow them. Lane A2 replaces the springs and the
## stepping with the gait generator and real foot placement; parts, mass and actuators stay.

signal jumped(speed: float)
signal landed(impact_speed: float)
signal stepped(leg: String)

const RAY_MASK := 1

var mech_id := ""
var def: Dictionary = {}
var legs: Array = []
var mass_info: Dictionary = {}
var actuators: Array = []
var is_player := true

var grounded_legs := 0
var airborne := false
var skidding := false
var charging := false
var charge_s := 0.0
var crouch := 0.0
var running := false
var aim_pitch_deg := 0.0
var ground_normal := Vector3.UP
var last_launch_speed := 0.0

var _aim_yaw := 0.0
var _crouch_toggled := false
var _no_spring_s := 0.0
var _skid_hold := 0.0
var _air_s := 0.0
var _fall_speed := 0.0
var _jump_was_held := false
var _move := Vector2.ZERO
var _aim := Vector2.ZERO
var _mouse := Vector2.ZERO
var _brake := 0.0
var _bench_speed_cap := INF
var _t: Dictionary = {}
var _step_s := 0.28
var _step_lift_m := 0.55


func setup(id: String, mech_def: Dictionary, leg_list: Array, info: Dictionary, acts: Array) -> void:
	mech_id = id
	def = mech_def
	legs = leg_list
	mass_info = info
	actuators = acts
	_t = Registry.tune("standin", {})
	_apply_tuning()
	var height := float(def.get("stance", {}).get("height_m", 2.0))
	var k := _stiffness()
	for leg: Dictionary in legs:
		var hip: Vector3 = leg["hip"]
		var ride := height + hip.y
		leg["rest_len"] = ride + float(info["mass"]) * 9.81 / (legs.size() * k)
		leg["front"] = hip.z < 0.0
		leg["contact"] = false
		leg["planted"] = Vector3.ZERO
		leg["step_from"] = Vector3.ZERO
		leg["step_to"] = Vector3.ZERO
		leg["step_t"] = -1.0
		leg["foot"] = Vector3.ZERO
		leg["hit"] = Vector3.ZERO
	var reach := 0.0
	if legs.size() > 0:
		reach = float(legs[0]["upper_len"]) + float(legs[0]["lower_len"])
	for a: Dictionary in actuators:
		_bench_speed_cap = minf(_bench_speed_cap, JumpCharge.bench_speed_cap(a.get("bench", {}), reach))


func _ready() -> void:
	add_to_group("mechs")
	if is_player:
		add_to_group("player_mech")
	_aim_yaw = _yaw_of(global_transform.basis)
	for leg: Dictionary in legs:
		var foot_world := to_global(MechBuilder.rest_foot(def, leg["hip"]))
		leg["planted"] = foot_world
		leg["foot"] = foot_world


## Reads "step" (swing_s, lift_m) from `_t`; a subclass that swaps `_t` for its own tuning block
## (a real mech's legs are a different size to the stand-in's) calls this again afterwards.
func _apply_tuning() -> void:
	var step: Dictionary = _t.get("step", {})
	_step_s = float(step.get("swing_s", 0.28))
	_step_lift_m = float(step.get("lift_m", 0.55))


func bench_mode() -> bool:
	return Settings.get_s("gameplay.physics_mode") == "bench"


func _stiffness() -> float:
	var sus: Dictionary = _t.get("suspension", {})
	var per_tonne := float(sus.get("stiffness_n_per_m_per_t", 48000.0))
	return per_tonne * float(mass_info.get("mass", 1000.0)) / 1000.0 / maxf(legs.size(), 1)


# --- input (read once per physics tick, before the forces) ------------------------------------


func _read_input(dt: float) -> void:
	if not is_player or Game.is_paused():
		_move = Vector2.ZERO
		_aim = Vector2.ZERO
		_mouse = Vector2.ZERO
		_brake = 0.0
		return
	_move = Controls.stick("move")
	_aim = Controls.stick("aim") * Settings.get_f("controls.aim_speed")
	if Settings.get_b("controls.aim_invert_y"):
		_aim.y = -_aim.y
	var steer := Settings.get_s("controls.mouse_mode") == "steer" and not Input.is_action_pressed("free_look")
	_mouse = Controls.take_mouse_delta() if steer else Vector2.ZERO
	_brake = Controls.trigger("brake")
	if Settings.get_s("controls.sprint_mode") == "hold":
		running = Input.is_action_pressed("sprint")
	elif Input.is_action_just_pressed("sprint"):
		running = not running
	if Settings.get_s("controls.sprint_mode") == "toggle" and _move.y < 0.2:
		running = false
	if Settings.get_s("controls.crouch_mode") == "hold":
		_crouch_toggled = Input.is_action_pressed("crouch")
	elif Input.is_action_just_pressed("crouch"):
		_crouch_toggled = not _crouch_toggled
	var jump_held := Input.is_action_pressed("jump")
	if jump_held and not airborne:
		if not charging:
			charging = true
			charge_s = 0.0
			Rumble.play("jump_charge")
		charge_s += dt
	if _jump_was_held and not jump_held and charging:
		_release_jump()
	_jump_was_held = jump_held


func _release_jump() -> void:
	charging = false
	Rumble.stop("jump_charge")
	if grounded_legs < 3:
		charge_s = 0.0
		return
	var p: Dictionary = _t.get("jump", {})
	var speed := 0.0
	if bench_mode():
		var reach := float(legs[0]["upper_len"]) + float(legs[0]["lower_len"])
		speed = JumpCharge.bench_speed(charge_s, mass, actuators, reach, p, Registry.tune("jump_bench", {}))
	else:
		speed = JumpCharge.game_speed(charge_s, p)
	charge_s = 0.0
	if speed <= 0.0:
		return
	var dir := (ground_normal * 0.8 + global_transform.basis.y * 0.2).normalized()
	apply_central_impulse(dir * speed * mass)
	last_launch_speed = speed
	_no_spring_s = 0.18
	airborne = true
	jumped.emit(speed)
	if is_player:
		Rumble.play("jump_launch")


# --- physics -----------------------------------------------------------------------------------


func _integrate_forces(state: PhysicsDirectBodyState3D) -> void:
	var dt := state.step
	_read_input(dt)
	var xf := state.transform
	var up := xf.basis.y
	var v := state.linear_velocity
	var w := state.angular_velocity
	var com_world := xf * center_of_mass
	var space := state.get_space_state()
	var sus: Dictionary = _t.get("suspension", {})
	var k := _stiffness()
	var zeta := float(sus.get("damping_ratio", 0.5))
	var c := 2.0 * zeta * sqrt(k * mass / maxf(legs.size(), 1))
	var margin := float(sus.get("ray_margin_m", 1.0))
	var crouch_target := 1.0 if (charging or _crouch_toggled) else 0.0
	crouch = move_toward(crouch, crouch_target, float(sus.get("crouch_speed", 3.0)) * dt)
	var span := _hip_span_z()
	var tilt := tan(deg_to_rad(aim_pitch_deg)) * span * 0.5
	_no_spring_s = maxf(_no_spring_s - dt, 0.0)

	var load_margin := float(sus.get("load_margin_m", 0.05))
	grounded_legs = 0
	var normal_sum := Vector3.ZERO
	for leg: Dictionary in legs:
		var hip_w := xf * (leg["hip"] as Vector3)
		var rest := float(leg["rest_len"]) * (1.0 - crouch * float(sus.get("crouch_fraction", 0.45)))
		rest += tilt if leg["front"] else -tilt
		var query := PhysicsRayQueryParameters3D.create(hip_w, hip_w - up * (rest + margin), RAY_MASK, [get_rid()])
		var hit := space.intersect_ray(query)
		# The long ray only places the feet; a leg carries load (and counts as grounded) when the
		# ground is within its rest length plus a few centimetres, or, after a launch, only once
		# it is actually compressed again. So a mech just off the ground cannot drive or steer.
		leg["contact"] = not hit.is_empty()
		leg["loaded"] = false
		if hit.is_empty():
			continue
		var hit_pos: Vector3 = hit["position"]
		leg["hit"] = hit_pos
		var compression := rest - hip_w.distance_to(hit_pos)
		if compression < (0.0 if airborne else -load_margin):
			continue
		leg["loaded"] = true
		grounded_legs += 1
		normal_sum += hit["normal"]
		if _no_spring_s > 0.0:
			continue
		var point_v := v + w.cross(hip_w - com_world)
		var force := k * compression - c * point_v.dot(up)
		if force > 0.0:
			state.apply_force(up * force, hip_w - xf.origin)

	ground_normal = normal_sum.normalized() if grounded_legs > 0 else Vector3.UP
	var on_ground := grounded_legs >= 2 and _no_spring_s <= 0.0
	if on_ground:
		if airborne and _air_s > 0.15:
			_on_landed(-_fall_speed)
		airborne = false
		_air_s = 0.0
		_drive(state, v)
		_turn(state, xf.basis, w, dt)
		_steady(state, w)
	else:
		_air_s += dt
		if grounded_legs == 0:
			airborne = true
		_fall_speed = v.dot(Vector3.UP)
		_aim_yaw = _yaw_of(xf.basis)
		skidding = false
	_pitch_aim(dt)


func _drive(state: PhysicsDirectBodyState3D, v: Vector3) -> void:
	var d: Dictionary = _t.get("drive", {})
	var n := ground_normal
	var fwd := _flat(-state.transform.basis.z, n)
	var right := _flat(state.transform.basis.x, n)
	var top := float(d.get("run_m_s", 12.0)) if running else float(d.get("walk_m_s", 7.0))
	var back := float(d.get("reverse_m_s", 5.0))
	var side := float(d.get("strafe_m_s", 5.0))
	if bench_mode():
		top = minf(top, _bench_speed_cap)
		back = minf(back, _bench_speed_cap)
		side = minf(side, _bench_speed_cap)
	var target := fwd * (_move.y * (top if _move.y >= 0.0 else back)) + right * (_move.x * side)
	var planar := v - n * v.dot(n)
	var dv := target - planar
	var limit := float(d.get("accel_m_s2", 9.0))
	if _brake > 0.05:
		dv = -planar
		limit = float(d.get("brake_m_s2", 20.0)) * _brake
	var sk: Dictionary = _t.get("skid", {})
	var grip := float(d.get("grip_m_s2", 16.0)) * grounded_legs / maxf(legs.size(), 1)
	if skidding:
		grip *= float(sk.get("grip_factor", 0.3))
	var acc := (dv * 6.0).limit_length(minf(limit, grip))
	state.apply_central_force(acc * mass)


func _turn(state: PhysicsDirectBodyState3D, basis: Basis, w: Vector3, dt: float) -> void:
	var tt: Dictionary = _t.get("turn", {})
	var aim_cfg: Variant = Registry.tune("aim", {})
	var turn_input := _aim.x
	var yaw := _yaw_of(basis)
	_aim_yaw -= deg_to_rad(float(tt.get("rate_deg_s", 90.0))) * turn_input * dt
	_aim_yaw -= deg_to_rad(float((aim_cfg as Dictionary).get("mouse_turn_deg_per_px", 0.09))) * _mouse.x
	var diff := wrapf(_aim_yaw - yaw, -PI, PI)
	var lead := deg_to_rad(75.0)
	if absf(diff) > lead:
		_aim_yaw = yaw + clampf(diff, -lead, lead)
		diff = clampf(diff, -lead, lead)
	var sk: Dictionary = _t.get("skid", {})
	var speed := state.linear_velocity.length()
	var hard_turn := absf(turn_input) > 0.5 or absf(diff) > deg_to_rad(25.0)
	if _brake > 0.5 and hard_turn and speed > float(sk.get("min_speed_m_s", 4.0)):
		if not skidding and is_player:
			Rumble.play("skid")
		skidding = true
		_skid_hold = float(sk.get("recover_s", 0.35))
	elif skidding:
		_skid_hold -= dt
		if _skid_hold <= 0.0 or speed < 1.0:
			skidding = false
			Rumble.stop("skid")
	var rate := float(tt.get("run_rate_deg_s", 70.0)) if running else float(tt.get("rate_deg_s", 95.0))
	var accel := float(tt.get("accel_deg_s2", 420.0))
	if skidding:
		rate = float(tt.get("skid_rate_deg_s", 260.0))
		accel = float(tt.get("skid_accel_deg_s2", 1400.0))
	var n := ground_normal
	var want := clampf(diff * 6.0, -deg_to_rad(rate), deg_to_rad(rate))
	var have := w.dot(n)
	var ang := clampf((want - have) * 12.0, -deg_to_rad(accel), deg_to_rad(accel))
	state.apply_torque(n * ang * inertia.y)


func _steady(state: PhysicsDirectBodyState3D, w: Vector3) -> void:
	if not Settings.get_b("gameplay.upright_assist"):
		return
	var u: Dictionary = _t.get("upright", {})
	var tilt_w := w - ground_normal * w.dot(ground_normal)
	state.apply_torque(-tilt_w * float(u.get("damping", 2.0)) * inertia.x)


func _pitch_aim(dt: float) -> void:
	var a: Dictionary = Registry.tune("aim", {})
	var rate := 40.0
	aim_pitch_deg += _aim.y * rate * dt - _mouse.y * float(a.get("mouse_pitch_deg_per_px", 0.05))
	aim_pitch_deg = clampf(aim_pitch_deg, float(a.get("pitch_min_deg", -8.0)), float(a.get("pitch_max_deg", 18.0)))


func _on_landed(impact: float) -> void:
	landed.emit(impact)
	if not is_player:
		return
	var hard := float(_t.get("jump", {}).get("hard_landing_m_s", 9.0))
	Rumble.play("landing_hard" if impact >= hard else "landing_soft")


# --- legs: two-bone IK, a simple step when a foot drifts, hitboxes follow ----------------------


func _physics_process(delta: float) -> void:
	var xf := global_transform
	for leg: Dictionary in legs:
		var hip: Vector3 = leg["hip"]
		var target_world: Vector3
		if leg["contact"]:
			target_world = leg["hit"]
		else:
			target_world = xf * (hip + Vector3(signf(hip.x) * 0.9, -float(leg["rest_len"]) * 0.95, 0.0))
		var t := float(leg["step_t"])
		if t >= 0.0:
			t += delta / _step_s
			leg["step_t"] = t
			var from: Vector3 = leg["step_from"]
			var to: Vector3 = leg["step_to"] if not leg["contact"] else target_world
			var foot := from.lerp(to, minf(t, 1.0)) + xf.basis.y * sin(minf(t, 1.0) * PI) * _step_lift_m
			leg["foot"] = foot
			if t >= 1.0:
				leg["step_t"] = -1.0
				leg["planted"] = to
				stepped.emit(str(leg["name"]))
				if is_player and leg["contact"]:
					Rumble.play("footstep")
		else:
			var drift := (leg["planted"] as Vector3).distance_to(target_world)
			if not leg["contact"] or airborne:
				leg["planted"] = leg["planted"].lerp(target_world, minf(delta * 8.0, 1.0))
			elif drift > 0.9 and not _partner_stepping(str(leg["name"])):
				leg["step_from"] = leg["planted"]
				leg["step_to"] = target_world + linear_velocity * 0.15
				leg["step_t"] = 0.0
			leg["foot"] = leg["planted"]
		var foot_local := LegIK.reachable(hip, to_local(leg["foot"]), leg["upper_len"], leg["lower_len"])
		var knee := LegIK.knee(hip, foot_local, leg["upper_len"], leg["lower_len"], MechBuilder.knee_pole(hip))
		var upper_xf := LegIK.segment(hip, knee)
		var lower_xf := LegIK.segment(knee, foot_local)
		var foot_xf := Transform3D(Basis.IDENTITY, foot_local + Vector3(0, 0.1, 0))
		(leg["upper_mesh"] as Node3D).transform = upper_xf
		(leg["lower_mesh"] as Node3D).transform = lower_xf
		(leg["foot_mesh"] as Node3D).transform = foot_xf
		(leg["upper_hitbox"] as Node3D).transform = upper_xf
		(leg["lower_hitbox"] as Node3D).transform = lower_xf
		(leg["foot_hitbox"] as Node3D).transform = foot_xf


func _partner_stepping(name: String) -> bool:
	var diagonal := {"fl": "rr", "rr": "fl", "fr": "rl", "rl": "fr"}
	for leg: Dictionary in legs:
		if float(leg["step_t"]) >= 0.0 and str(leg["name"]) != diagonal.get(name, ""):
			return true
	return false


# --- readouts ----------------------------------------------------------------------------------


func telemetry() -> Dictionary:
	var p := global_position
	var clearance := 0.0
	var n := 0
	for leg: Dictionary in legs:
		if leg["contact"]:
			clearance += (global_transform * (leg["hip"] as Vector3)).distance_to(leg["hit"])
			n += 1
	return {
		"position": [snappedf(p.x, 0.01), snappedf(p.y, 0.01), snappedf(p.z, 0.01)],
		"speed_m_s": snappedf(linear_velocity.length(), 0.01),
		"heading_deg": snappedf(heading_deg(), 0.1),
		"pitch_deg": snappedf(rad_to_deg(global_transform.basis.get_euler().x), 0.1),
		"roll_deg": snappedf(rad_to_deg(global_transform.basis.get_euler().z), 0.1),
		"grounded_legs": grounded_legs,
		"airborne": airborne,
		"skidding": skidding,
		"charging": charging,
		"crouch": snappedf(crouch, 0.01),
		"hip_clearance_m": snappedf(clearance / maxf(n, 1), 0.01),
		"mass_kg": snappedf(mass, 0.1),
		"last_launch_m_s": snappedf(last_launch_speed, 0.01),
		"physics_mode": Settings.get_s("gameplay.physics_mode"),
	}


func heading_deg() -> float:
	return fposmod(-rad_to_deg(_yaw_of(global_transform.basis)), 360.0)


func charge_fraction() -> float:
	var p: Dictionary = _t.get("jump", {})
	return JumpCharge.fraction(charge_s, float(p.get("min_hold_s", 0.12)), float(p.get("full_charge_s", 1.1)))


func gun_ray() -> Array:
	var muzzle := global_transform * Vector3(0.0, 0.85, -3.5)
	return [muzzle, -global_transform.basis.z]


func _hip_span_z() -> float:
	var lo := INF
	var hi := -INF
	for leg: Dictionary in legs:
		lo = minf(lo, (leg["hip"] as Vector3).z)
		hi = maxf(hi, (leg["hip"] as Vector3).z)
	return hi - lo if hi > lo else 1.0


static func _yaw_of(b: Basis) -> float:
	var f := -b.z
	return atan2(-f.x, -f.z)


static func _flat(v: Vector3, n: Vector3) -> Vector3:
	var out := v - n * v.dot(n)
	return out.normalized() if out.length() > 0.0001 else Vector3.ZERO
