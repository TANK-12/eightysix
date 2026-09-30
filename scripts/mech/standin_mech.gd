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
## Scales the drive's top speeds (walk, run, reverse, strafe); MechCombat lowers it for a hurt leg.
var speed_scale := 1.0
## True while MechClimb hauls the mech up a ledge (feet off the ground, but not a jump).
var hauling := false

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
var _stuck_s := 0.0
var _run_stance := 0.0
var _skid_brace := 0.0
var _leg_scale := 1.0
var _since_ground := 0.0
var _lift := 0.0
var _spread := 1.0


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
		if not leg.has("sole_rest"):
			leg["sole_rest"] = MechBuilder.rest_foot(def, hip)
		if not leg.has("pivot"):
			leg["pivot"] = hip
			leg["end_offset"] = MechBuilder.FOOT_RAISE
			leg["pole"] = MechBuilder.knee_pole(hip)
		leg["sole_contact"] = false
		leg["sole_hit"] = Vector3.ZERO
		leg["sole_normal"] = Vector3.UP
		leg["planted_normal"] = Vector3.UP
		leg["foot_up"] = Vector3.UP
		leg["needs_seat"] = true
		leg["step_lift"] = _step_lift_m
	var reach := 0.0
	if legs.size() > 0:
		reach = float(legs[0]["upper_len"]) + float(legs[0]["lower_len"])
	for a: Dictionary in actuators:
		_bench_speed_cap = minf(_bench_speed_cap, JumpCharge.bench_speed_cap(a.get("bench", {}), reach))
	_read_stance()
	_apply_stance()


## The stance controls; the stand-in keeps the modelled pose (juggernaut_mech.gd reads Settings).
func _read_stance() -> void:
	pass


## Emerson's play-testing controls (2026-09-30): the stance the feet aim for and the springs hold.
## `_lift` raises the body (the springs' rest length grows and the soles aim that much lower),
## `_spread` draws the feet in towards (or out from) the hip joints, and `_leg_scale` lengthens the
## thigh and shin (IK, meshes and hitboxes together). The rest frames stay the modelled pose; only
## the targets move, and every foot steps into the new stance.
func _apply_stance() -> void:
	var height := float(def.get("stance", {}).get("height_m", 2.0))
	var k := _stiffness()
	for leg: Dictionary in legs:
		var hip: Vector3 = leg["hip"]
		leg["rest_len"] = height + _lift + hip.y + float(mass_info["mass"]) * 9.81 / (legs.size() * k)
		var sole: Vector3 = leg["sole_rest"]
		var pivot: Vector3 = leg["pivot"]
		leg["sole_stance"] = Vector3(pivot.x + (sole.x - pivot.x) * _spread, sole.y - _lift, pivot.z + (sole.z - pivot.z) * _spread)
		# The leg's spring stands over its foot at hip height (lane A2 part 5): the body is held on the
		# feet's wide footprint, not on the hips, which sit only 0.85 m apart on the real Juggernaut.
		leg["spring_at"] = Vector3((leg["sole_stance"] as Vector3).x, hip.y, (leg["sole_stance"] as Vector3).z)
		leg["needs_seat"] = true
		for seg: String in ["upper", "lower"]:
			for hb: Variant in leg.get(seg + "_hitboxes", [leg.get(seg + "_hitbox")]):
				_stretch_hitbox(hb as CollisionShape3D, _leg_scale)


## Stretches a leg segment's hitbox along the leg (local Z) from the shape it was built with, so it
## keeps matching the stretched mesh without scaling the CollisionShape3D node itself.
static func _stretch_hitbox(cs: CollisionShape3D, s: float) -> void:
	if cs == null or cs.shape == null:
		return
	if cs.shape is ConvexPolygonShape3D:
		var hull := cs.shape as ConvexPolygonShape3D
		if not cs.has_meta("base_points"):
			cs.set_meta("base_points", hull.points)
		var base: PackedVector3Array = cs.get_meta("base_points")
		hull.points = Transform3D(Basis.from_scale(Vector3(1, 1, s)), Vector3.ZERO) * base
	elif cs.shape is BoxShape3D:
		var box := cs.shape as BoxShape3D
		if not cs.has_meta("base_size"):
			cs.set_meta("base_size", box.size)
		var size: Vector3 = cs.get_meta("base_size")
		box.size = Vector3(size.x, size.y, size.z * s)


func _ready() -> void:
	add_to_group("mechs")
	if is_player:
		add_to_group("player_mech")
	_aim_yaw = _yaw_of(global_transform.basis)
	for leg: Dictionary in legs:
		var foot_world := to_global(leg["sole_stance"])
		leg["planted"] = foot_world
		leg["foot"] = foot_world
		leg["planted_normal"] = global_transform.basis.y


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
	var p: Dictionary = _t.get("jump", {})
	# Bench mode keeps the strict rule (3 loaded legs to push off). Game mode fires on 2, or within
	# jump.coyote_s of last being on the ground, so a jump released mid-stride at a run still goes.
	var ok := grounded_legs >= 3
	if not bench_mode():
		ok = grounded_legs >= 2 or _since_ground <= float(p.get("coyote_s", 0.0))
	if not ok:
		charge_s = 0.0
		return
	var speed := 0.0
	var leap := 0.0
	if bench_mode():
		var reach := float(legs[0]["upper_len"]) + float(legs[0]["lower_len"])
		speed = JumpCharge.bench_speed(charge_s, mass, actuators, reach, p, Registry.tune("jump_bench", {}))
	else:
		speed = JumpCharge.game_speed(charge_s, p)
		leap = float(p.get("leap_m_s", 0.0)) * JumpCharge.fraction(charge_s, float(p.get("min_hold_s", 0.12)), float(p.get("full_charge_s", 1.1)))
	charge_s = 0.0
	if speed <= 0.0:
		return
	var dir := (ground_normal * 0.8 + global_transform.basis.y * 0.2).normalized()
	var impulse := dir * speed
	# Game mode: a charged jump also leaps along the way the stick points (a running long jump).
	var along := _flat(-global_transform.basis.z * _move.y + global_transform.basis.x * _move.x, ground_normal)
	if leap > 0.0 and _move.length() > 0.1:
		impulse += along * leap * minf(_move.length(), 1.0)
	apply_central_impulse(impulse * mass)
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

	# Lane A2 part 3, ANALYSIS.md's run pose ("very low and level, stance wide... does not bob") and
	# the anime's outward-braced skid turn: both are a wider stance and (for running) a lower, nose-
	# down body, not just timing, so they live here with the suspension rather than as a step-timing
	# tuning number. Smoothed with move_toward (not snapped) so the transition itself does not read
	# as a bob. All zero on the stand-in by default (juggernaut.json supplies the real numbers), so
	# lane A1's own tests are unaffected.
	var rs: Dictionary = _t.get("run_stance", {})
	var stance_rate := 1.0 / maxf(float(rs.get("transition_s", 0.4)), 0.01)
	_run_stance = move_toward(_run_stance, 1.0 if running else 0.0, stance_rate * dt)
	_skid_brace = move_toward(_skid_brace, 1.0 if skidding else 0.0, stance_rate * dt)
	var splay := float(rs.get("splay_m", 0.0)) * _run_stance + float(_t.get("skid", {}).get("brace_out_m", 0.0)) * _skid_brace
	var run_drop := float(rs.get("drop_m", 0.0)) * _run_stance
	var run_tilt := tan(deg_to_rad(float(rs.get("pitch_deg", 0.0)))) * span * 0.5 * _run_stance

	var load_margin := float(sus.get("load_margin_m", 0.05))
	grounded_legs = 0
	var normal_sum := Vector3.ZERO
	for leg: Dictionary in legs:
		var out_w := xf.basis.x * signf((leg["hip"] as Vector3).x) * splay
		var cast_w := xf * (leg["spring_at"] as Vector3) + out_w
		_cast_sole(leg, space, xf, out_w, margin)
		var rest := float(leg["rest_len"]) * (1.0 - crouch * float(sus.get("crouch_fraction", 0.45))) - run_drop
		rest += (tilt + run_tilt) if leg["front"] else -(tilt + run_tilt)
		var query := PhysicsRayQueryParameters3D.create(cast_w, cast_w - up * (rest + margin), RAY_MASK, [get_rid()])
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
		var compression := rest - cast_w.distance_to(hit_pos)
		if compression < (0.0 if airborne else -load_margin):
			continue
		leg["loaded"] = true
		grounded_legs += 1
		normal_sum += hit["normal"]
		if _no_spring_s > 0.0:
			continue
		var point_v := v + w.cross(cast_w - com_world)
		var force := k * compression - c * point_v.dot(up)
		if force > 0.0:
			state.apply_force(up * force, cast_w - xf.origin)

	ground_normal = normal_sum.normalized() if grounded_legs > 0 else Vector3.UP
	var on_ground := grounded_legs >= 2 and _no_spring_s <= 0.0
	if on_ground:
		_since_ground = 0.0
		if airborne and _air_s > 0.15:
			_on_landed(-_fall_speed)
		airborne = false
		_air_s = 0.0
		_stuck_s = 0.0
		_drive(state, v)
		_turn(state, xf.basis, w, dt)
		_steady(state, w, 0.0)
	else:
		_air_s += dt
		_since_ground += dt
		if grounded_legs == 0:
			airborne = true
		# Game-feel arc (game mode only, tuning jump.fall_gravity_scale): heavier on the way down.
		var fall_scale := float(_t.get("jump", {}).get("fall_gravity_scale", 1.0))
		if airborne and v.y < 0.0 and fall_scale > 1.0 and not bench_mode():
			state.apply_central_force(state.total_gravity * (fall_scale - 1.0) * mass)
		_fall_speed = v.dot(Vector3.UP)
		if airborne and air_control_on():
			_air_control(state, v, w, dt)
		else:
			_aim_yaw = _yaw_of(xf.basis)
		skidding = false
		# Fewer than 2 legs grounded normally means "mid-jump, no assist" by design (a bad landing
		# angle should punish you). But a real jump keeps moving; a mech that has stayed almost still
		# without regaining ground for a while is not falling, it is tipped over or wedged on terrain
		# (results/A2.md: long_walk's tries 1 and 2, against a slab corner and a rock), and nothing
		# else in this file ever recovers that on its own. Only then does a proportional righting
		# torque and a small free-itself shove switch on, ramping in so it never fights a genuine
		# jump arc. (Checked and ruled out: a mech that stays fully grounded but rams itself against
		# an obstacle -- calibrated against the same slab -- was not actually stuck; plain reverse
		# input already frees it under the unmodified drive/turn, since those are never disabled
		# while on_ground. Only the documented < 2 legs case needed this.)
		var rc: Dictionary = _t.get("recover", {})
		if v.length() < float(rc.get("stuck_speed_m_s", 1.0)):
			_stuck_s += dt
		else:
			_stuck_s = 0.0
		var delay := float(rc.get("stuck_delay_s", 1.25))
		if _stuck_s > delay:
			var recover := clampf((_stuck_s - delay) / float(rc.get("ramp_s", 2.0)), 0.0, 1.0)
			_steady(state, w, recover)
			_unstick(state, xf.basis, recover)
	_keel(state, w)
	_pitch_aim(dt)


func air_control_on() -> bool:
	return not bench_mode() and not hauling and Settings.get_b("gameplay.air_control")


## Game-mode air control (Emerson, 2026-09-30: "movement in mid-air", aim with the mouse in the air
## too; Settings > Gameplay "Air control", off = the supplement's pure ballistic jump). An attitude
## controller swings the chassis to the aim yaw (mouse / right stick, faster than on the ground) and
## the aim pitch, so the fixed gun can be pointed and fired in flight (the recoil dodge included).
## The move stick adds a push along the chassis' heading and side, up to tuning air.max_m_s along
## that direction; momentum already past that is kept, never braked.
func _air_control(state: PhysicsDirectBodyState3D, v: Vector3, w: Vector3, dt: float) -> void:
	var a: Dictionary = _t.get("air", {})
	var basis := state.transform.basis.orthonormalized()
	var aim_cfg: Dictionary = Registry.tune("aim", {})
	_aim_yaw -= deg_to_rad(float(a.get("turn_rate_deg_s", 150.0))) * _aim.x * dt
	_aim_yaw -= deg_to_rad(float(aim_cfg.get("mouse_turn_deg_per_px", 0.09))) * _mouse.x
	var yaw := _yaw_of(basis)
	var lead := deg_to_rad(float(a.get("yaw_lead_deg", 90.0)))
	var diff := wrapf(_aim_yaw - yaw, -PI, PI)
	if absf(diff) > lead:
		_aim_yaw = yaw + clampf(diff, -lead, lead)
	var want := Basis(Vector3.UP, _aim_yaw) * Basis(Vector3.RIGHT, deg_to_rad(aim_pitch_deg))
	var err := (want * basis.inverse()).get_rotation_quaternion()
	var angle := err.get_angle()
	if angle > PI:
		angle -= TAU
	var axis := err.get_axis() if absf(angle) > 0.0001 else Vector3.ZERO
	var acc := axis * angle * float(a.get("attitude_stiffness", 40.0)) - w * float(a.get("attitude_damping", 10.0))
	acc = acc.limit_length(deg_to_rad(float(a.get("max_ang_accel_deg_s2", 900.0))))
	var local := basis.inverse() * acc
	state.apply_torque(basis * (local * inertia))
	var fwd := Vector3(-basis.z.x, 0.0, -basis.z.z).normalized()
	var right := Vector3(basis.x.x, 0.0, basis.x.z).normalized()
	var dir := (fwd * _move.y + right * _move.x).limit_length(1.0)
	if dir.length() < 0.05:
		return
	var along := Vector3(v.x, 0.0, v.z).dot(dir.normalized())
	if along < float(a.get("max_m_s", 14.0)):
		state.apply_central_force(dir * float(a.get("accel_m_s2", 6.0)) * mass)


## Game mode only (Emerson, 2026-09-30: normal play must not tip the spider over, and there are no
## fall or flail animations yet). Past upright.keep_deg of lean from the ground under it (world up
## in the air), a righting torque grows with the lean, capped, and the tilting spin is damped, so
## bumps, hard turns and landings settle back instead of rolling it. Weaker in the air
## (keep_air_factor). Off with Balance assist off, and in bench mode, which stays raw physics.
func _keel(state: PhysicsDirectBodyState3D, w: Vector3) -> void:
	var u: Dictionary = _t.get("upright", {})
	var keep := deg_to_rad(float(u.get("keep_deg", 0.0)))
	if keep <= 0.0 or bench_mode() or not Settings.get_b("gameplay.upright_assist"):
		return
	if airborne and air_control_on():
		return  # _air_control holds the attitude in the air
	var up := state.transform.basis.y
	var target := ground_normal if grounded_legs >= 2 else Vector3.UP
	var lean := up.angle_to(target)
	if lean <= keep:
		return
	var axis := up.cross(target)
	if axis.length() < 0.0001:
		return
	var factor := 1.0 if grounded_legs >= 2 else float(u.get("keep_air_factor", 0.35))
	var push := float(u.get("keep_stiffness", 20.0)) * minf((lean - keep) / keep, 3.0)
	var spin := w - up * w.dot(up)
	var accel := (axis.normalized() * push - spin * float(u.get("keep_damping", 4.0))) * factor
	state.apply_torque(accel * inertia.x)


func _drive(state: PhysicsDirectBodyState3D, v: Vector3) -> void:
	var d: Dictionary = _t.get("drive", {})
	var n := ground_normal
	var fwd := _flat(-state.transform.basis.z, n)
	var right := _flat(state.transform.basis.x, n)
	var top := float(d.get("run_m_s", 12.0)) if running else float(d.get("walk_m_s", 7.0))
	var back := float(d.get("reverse_m_s", 5.0))
	var side := float(d.get("strafe_m_s", 5.0))
	top *= speed_scale
	back *= speed_scale
	side *= speed_scale
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


## `recover` is 0 on ordinary standing ground (rate damping only, as before). Above 0 (only reached
## from the stuck path in `_integrate_forces`, below 2 grounded legs for a while) it adds a
## proportional righting torque toward world up -- using the "stiffness" tuning figure that sat
## unread in tuning.json's "upright" block until now -- so a mech that has already settled tipped
## over gets pushed back upright instead of just having its (already zero) angular rate damped.
## World up, not `ground_normal`: with under 2 legs grounded, `ground_normal` can come from a single
## leg pressed against a tilted rock or a wall, which would read as "already upright" relative to
## itself and right the mech toward the wrong orientation.
func _steady(state: PhysicsDirectBodyState3D, w: Vector3, recover: float) -> void:
	if not Settings.get_b("gameplay.upright_assist"):
		return
	var u: Dictionary = _t.get("upright", {})
	var tilt_w := w - ground_normal * w.dot(ground_normal)
	var torque := -tilt_w * float(u.get("damping", 2.0))
	if recover > 0.0:
		var up := state.transform.basis.y
		torque += up.cross(Vector3.UP) * float(u.get("stiffness", 6.0)) * recover
	state.apply_torque(torque * inertia.x)


## Only reached once `_integrate_forces` has decided the mech is genuinely stuck (not mid-jump): a
## small, capped shove away from whatever the chassis is actually pressed against, plus a little
## lift, so it can work itself free instead of sitting in permanent equilibrium. Pushing along the
## body's own forward was tried first and made things worse: calibrating against the slab at
## (34, -30) showed the real jam is the chassis rammed nose-first into the slab's vertical face, so
## a forward-biased shove presses it harder into the wall it is stuck on. Reading the actual contact
## normals from Jolt (the chassis parts collide; the leg hitboxes do not, see mech_builder.gd) and
## pushing along their sum is the direction that is actually open, whatever the obstacle is. Ramps
## in with `recover` and is gated by the same upright-assist setting as `_steady`, since it is the
## same recovery system.
func _unstick(state: PhysicsDirectBodyState3D, basis: Basis, recover: float) -> void:
	if not Settings.get_b("gameplay.upright_assist"):
		return
	var rc: Dictionary = _t.get("recover", {})
	var push := Vector3.ZERO
	for i in state.get_contact_count():
		push += state.get_contact_local_normal(i)
	var dir: Vector3
	if push.length() > 0.01:
		dir = (push.normalized() + Vector3.UP * 0.3).normalized()
	else:
		dir = (-basis.z * 0.7 + Vector3.UP * 0.3).normalized()
	var accel := float(rc.get("unstick_accel_m_s2", 3.0)) * recover
	state.apply_central_force(dir * accel * mass)


## Body tilt to aim up and down (mouse or right stick). Emerson, 2026-09-30: nothing follows the
## mouse up and down, the chassis and gun are fixed; so this is an option (gameplay.aim_tilt, off by
## default), and with it off the body eases back level.
func _pitch_aim(dt: float) -> void:
	if not Settings.get_b("gameplay.aim_tilt"):
		aim_pitch_deg = move_toward(aim_pitch_deg, 0.0, 40.0 * dt)
		return
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


## Lane A2 part 4: where the foot really stands. The leg's sole (MechBuilder.leg_sole: the model's
## sole socket, the foot's contact point at the rest pose) is pushed out by the run/skid splay, and a
## ray goes down through it from hip height, so each foot lands on the ground under it rather than
## on the ground under the hip 2-3 m further in (on rocky ground those differ). The springs keep
## their own rays at the hips: this places the feet and changes nothing about how the body is held.
func _cast_sole(leg: Dictionary, space: PhysicsDirectSpaceState3D, xf: Transform3D, out_w: Vector3, margin: float) -> void:
	var sole: Vector3 = leg["sole_stance"]
	var rise := maxf((leg["hip"] as Vector3).y - sole.y, 0.5)
	var sole_w := xf * sole + out_w
	var up := xf.basis.y
	var query := PhysicsRayQueryParameters3D.create(sole_w + up * rise, sole_w - up * margin, RAY_MASK, [get_rid()])
	var hit := space.intersect_ray(query)
	leg["sole_contact"] = not hit.is_empty()
	if not hit.is_empty():
		leg["sole_hit"] = hit["position"]
		leg["sole_normal"] = hit["normal"]


func _physics_process(delta: float) -> void:
	var xf := global_transform
	var feet: Dictionary = _t.get("feet", {})
	var max_tilt := deg_to_rad(float(feet.get("max_tilt_deg", 25.0)))
	var reseat := float(feet.get("reseat_m", 0.3))
	for leg: Dictionary in legs:
		var on_ground: bool = leg["sole_contact"] or leg["contact"]
		var target_world: Vector3
		var target_normal := xf.basis.y
		if leg["sole_contact"]:
			target_world = leg["sole_hit"]
			target_normal = leg["sole_normal"]
		elif leg["contact"]:
			target_world = leg["hit"]
		else:
			# Nothing under the foot: the leg hangs in its rest pose (fronts forward, rears back,
			# not tucked in: ANALYSIS.md's airborne legs).
			target_world = xf * (leg["sole_stance"] as Vector3)
		var t := float(leg["step_t"])
		if t >= 0.0:
			t += delta / _step_s
			leg["step_t"] = t
			var from: Vector3 = leg["step_from"]
			var to: Vector3 = leg["step_to"] if not on_ground else target_world
			var foot := from.lerp(to, minf(t, 1.0)) + xf.basis.y * sin(minf(t, 1.0) * PI) * float(leg["step_lift"])
			leg["foot"] = foot
			if t >= 1.0:
				leg["step_t"] = -1.0
				leg["planted"] = to
				leg["planted_normal"] = target_normal
				stepped.emit(str(leg["name"]))
				if is_player and on_ground:
					Rumble.play("footstep")
		else:
			var gap: Vector3 = target_world - (leg["planted"] as Vector3)
			var seat := bool(leg["needs_seat"]) and gap.length() > 0.05
			if not on_ground or airborne:
				leg["planted"] = leg["planted"].lerp(target_world, minf(delta * 8.0, 1.0))
				leg["planted_normal"] = target_normal
				leg["needs_seat"] = true
			elif (gap.length() > 0.9 or absf(gap.dot(xf.basis.y)) > reseat or seat) and not _partner_stepping(str(leg["name"])):
				# Step when the foot has drifted too far from where it should stand, is left
				# hovering above (or sunk into) the ground, or has just come down from the air (a
				# landing, or the drop at spawn) and is not yet where its sole belongs. A short
				# re-seat step lifts the foot less than a full stride.
				leg["step_from"] = leg["planted"]
				leg["step_to"] = target_world + linear_velocity * 0.15
				leg["step_t"] = 0.0
				leg["step_lift"] = _step_lift_m * clampf(gap.length() / 0.9, 0.3, 1.0)
				leg["needs_seat"] = false
			elif gap.length() <= 0.05:
				leg["needs_seat"] = false
			leg["foot"] = leg["planted"]
		# The foot pivots about its sole on the ground; the IK chain ends at its ankle above that.
		var planted := float(leg["step_t"]) < 0.0 and on_ground
		var tilt := Basis(Quaternion(Vector3.UP, _foot_up(leg, xf, planted, max_tilt, delta)))
		var pose := MechBuilder.pose_segments(leg, to_local(leg["foot"]) + tilt * (leg["end_offset"] as Vector3), tilt, _leg_scale)
		var upper_xf: Transform3D = pose["upper"]
		var lower_xf: Transform3D = pose["lower"]
		var foot_xf: Transform3D = pose["foot"]
		(leg["upper_mesh"] as Node3D).transform = upper_xf.scaled_local(Vector3(1, 1, _leg_scale))
		(leg["lower_mesh"] as Node3D).transform = lower_xf.scaled_local(Vector3(1, 1, _leg_scale))
		(leg["foot_mesh"] as Node3D).transform = foot_xf
		for hb: Node3D in leg.get("upper_hitboxes", [leg["upper_hitbox"]]):
			hb.transform = upper_xf
		for hb: Node3D in leg.get("lower_hitboxes", [leg["lower_hitbox"]]):
			hb.transform = lower_xf
		for hb: Node3D in leg.get("foot_hitboxes", [leg["foot_hitbox"]]):
			hb.transform = foot_xf


## The foot's up direction in the body frame: square to the ground it is planted on (the sole
## socket's normal is the model's up at rest), level while it swings or hangs, tilted at most
## feet.max_tilt_deg, and eased in so a foot settles onto a slope instead of snapping to it.
func _foot_up(leg: Dictionary, xf: Transform3D, planted: bool, max_tilt: float, delta: float) -> Vector3:
	var want := Vector3.UP
	if planted:
		want = (xf.basis.inverse() * (leg["planted_normal"] as Vector3)).normalized()
		var angle := want.angle_to(Vector3.UP)
		if angle > max_tilt:
			want = Vector3.UP.slerp(want, max_tilt / angle)
	var up := (leg["foot_up"] as Vector3).slerp(want, minf(delta * 12.0, 1.0)).normalized()
	leg["foot_up"] = up
	return up


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
	var soles := 0
	for leg: Dictionary in legs:
		if leg["contact"]:
			clearance += (global_transform * (leg["spring_at"] as Vector3)).distance_to(leg["hit"])
			n += 1
		if leg["sole_contact"]:
			soles += 1
	return {
		"position": [snappedf(p.x, 0.01), snappedf(p.y, 0.01), snappedf(p.z, 0.01)],
		"speed_m_s": snappedf(linear_velocity.length(), 0.01),
		"heading_deg": snappedf(heading_deg(), 0.1),
		"pitch_deg": snappedf(rad_to_deg(global_transform.basis.get_euler().x), 0.1),
		"roll_deg": snappedf(rad_to_deg(global_transform.basis.get_euler().z), 0.1),
		"grounded_legs": grounded_legs,
		"feet_on_ground": soles,
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
		lo = minf(lo, (leg["spring_at"] as Vector3).z)
		hi = maxf(hi, (leg["spring_at"] as Vector3).z)
	return hi - lo if hi > lo else 1.0


static func _yaw_of(b: Basis) -> float:
	var f := -b.z
	return atan2(-f.x, -f.z)


static func _flat(v: Vector3, n: Vector3) -> Vector3:
	var out := v - n * v.dot(n)
	return out.normalized() if out.length() > 0.0001 else Vector3.ZERO
