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
const BENCH_DRIVER := preload("res://scripts/mech/bench_driver.gd")

var mech_id := ""
var def: Dictionary = {}
var legs: Array = []
var mass_info: Dictionary = {}
var actuators: Array = []
var is_player := true

var grounded_legs := 0
var airborne := false
var skidding := false
## How far the feet's grip is broken into a slide, 0 (full grip) to 1 (skating on kinetic friction):
## the slide trigger's depth at speed (lane A3 part 4, see _update_slide).
var slide_amount := 0.0
var charging := false
var charge_s := 0.0
var crouch := 0.0
var running := false
var aim_pitch_deg := 0.0
## Where the pilot looks up or down (world pitch, degrees): the camera and the wire anchors follow it;
## the body tilts after it only as far as its legs allow (aim.pitch_min/max_deg, gameplay.aim_tilt).
var look_pitch_deg := 0.0
var ground_normal := Vector3.UP
var last_launch_speed := 0.0
## Scales the drive's top speeds (walk, run, reverse, strafe); MechCombat lowers it for a hurt leg.
var speed_scale := 1.0
## True while MechClimb hauls the mech up a ledge (feet off the ground, but not a jump).
var hauling := false

var _aim_yaw := 0.0
var _crouch_toggled := false
var _no_spring_s := 0.0
var _air_s := 0.0
var _fall_speed := 0.0
var _jump_was_held := false
var _move := Vector2.ZERO
var _aim := Vector2.ZERO
var _aim_deflection := 0.0  # the aim stick's up-down deflection, -1 to 1 (before the speed setting)
var _mouse_pitch := 0.0  # the pitch the mouse has set in the "angle" aim mode (the stick adds its deflection)
var _mouse := Vector2.ZERO
var _brake := 0.0
var _bench_speed_cap := INF
var bench: Node  # BenchDriver (lane B6): the actuators' real torque, power and heat; idle in game mode
var _drive_force := Vector3.ZERO  # the last tick's drive push on the body, N (the bench reads it)
var _t: Dictionary = {}
var _step_s := 0.28
var _step_lift_m := 0.55
var _stuck_s := 0.0
var _run_stance := 0.0
var _skid_brace := 0.0
var _leg_scale := 1.0
var _since_ground := 0.0
var _on_ground_s := 0.0  # how long it has stood on 2+ legs since the last time in the air
var _drive_moment := Vector3.ZERO  # the drive's moment about the centre of mass, smoothed (N m)
var _lift := 0.0
var _spread := 1.0
var _stride_half := 0.45  # how far ahead of its rest spot a foot lands, and behind it steps again
var _swing_now := 0.28  # this tick's swing time: _step_s, shortened when the stride is maxed out

enum Swing { IDLE, SWEEP, TUCK, RETURN, UNTUCK }
## Leg-swing turning in the air (see _air_legs): the legs' swing away from their stance (x = yaw
## about the body's up, y = pitch about its side axis, radians), its rate, how far they are tucked in
## (0 outstretched, 1 tucked), the cycle's phase and sweep direction, the legs' moments of inertia
## about the body axes (outstretched and tucked), and the angular momentum they carry (world frame).
var air_swing := Vector2.ZERO
var air_tuck := 0.0
var air_phase := Swing.IDLE
var leg_momentum := Vector3.ZERO
var leg_inertia := {"yaw": Vector2.ZERO, "pitch": Vector2.ZERO, "roll": Vector2.ZERO}
## Flips (lane A4, Emerson 2026-10-01 "let me flip in mid air"): how far the legs are tucked in by the
## pilot holding crouch in the air (0 outstretched, 1 tucked), the body inertia that tuck gives
## (pitch, yaw, roll about the body axes) and the stance inertia it started from.
var flip_tuck := 0.0
## True from a flip's take-off until the feet are down again: the leg swing then only turns the body
## about its up axis and leaves the pitch and roll spin alone (it would otherwise swing against it).
var flipping := false
var last_flip_offset := Vector3.ZERO
var _body_tuck := 0.0
var _stance_inertia := Vector3.ZERO
var _swing_w := Vector2.ZERO
var _swing_dir := Vector2.ZERO


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
		leg["step_from_local"] = Vector3.ZERO
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
	_measure_leg_inertia()
	# No made-up damping: Godot's default 0.1/s linear and angular damping is replaced by real air
	# drag (_air_drag) and, in flight, no spin damping at all (angular momentum is conserved).
	linear_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
	linear_damp = 0.0
	angular_damp_mode = RigidBody3D.DAMP_MODE_REPLACE


## The legs' moment of inertia about the body's up (yaw) and side (pitch) axes through the centre of
## mass when they swing together about their hips, outstretched and tucked. Each leg is a rod from its
## hip pivot to its sole (mass = thigh + shin + foot parts), its centre halfway; a rod swinging about
## its end at pivot h (from the centre of mass) with half-length vector r carries
## m * ((h + r) . r + |r|^2 / 3) per rad/s about an axis (components square to the axis only).
## Tucked, the feet draw in to air.tuck_scale of their reach. Reasoned from the parts' masses.
func _measure_leg_inertia() -> void:
	var a: Dictionary = _t.get("air", {})
	var tuck := float(a.get("tuck_scale", 0.55))
	var yaw := Vector2.ZERO
	var pitch := Vector2.ZERO
	var roll := Vector2.ZERO
	for leg: Dictionary in legs:
		var m := _leg_mass(leg)
		var pivot: Vector3 = leg["pivot"]
		var h := pivot - center_of_mass
		var r := ((leg["sole_stance"] as Vector3) - pivot) * 0.5
		yaw += Vector2(_rod_inertia(m, h, r, Vector3.UP), _rod_inertia(m, h, r * tuck, Vector3.UP))
		pitch += Vector2(_rod_inertia(m, h, r, Vector3.RIGHT), _rod_inertia(m, h, r * tuck, Vector3.RIGHT))
		roll += Vector2(_rod_inertia(m, h, r, Vector3.BACK), _rod_inertia(m, h, r * tuck, Vector3.BACK))
	leg_inertia = {"yaw": yaw, "pitch": pitch, "roll": roll}


## Thigh, shin and foot, plus the parts that swing with the leg about the hip: the coxa (the hip's
## yaw link) and the knee ram (mechs.json legs.<leg>.swing_parts).
func _leg_mass(leg: Dictionary) -> float:
	var leg_def: Dictionary = def.get("legs", {}).get(leg["name"], {})
	var m := 0.0
	for seg: String in ["upper", "lower", "foot"]:
		if leg_def.has(seg):
			m += float(Registry.entry("parts", str(leg_def[seg])).get("mass_kg", 0.0))
	for pid: Variant in leg_def.get("swing_parts", []):
		m += float(Registry.entry("parts", str(pid)).get("mass_kg", 0.0))
	return m


static func _rod_inertia(m: float, h: Vector3, r: Vector3, axis: Vector3) -> float:
	var hp := h - axis * h.dot(axis)
	var rp := r - axis * r.dot(axis)
	return m * ((hp + rp).dot(rp) + rp.length_squared() / 3.0)


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
	if not actuators.is_empty():
		bench = BENCH_DRIVER.new()
		bench.name = "Bench"
		add_child(bench)
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


## True when the bench's actuator model is steering this mech (bench mode and a driver with joints).
func bench_on() -> bool:
	return bench != null and bench_mode() and bool(bench.call("is_active"))


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
	_aim_deflection = clampf(_aim.y / maxf(Settings.get_f("controls.aim_speed"), 0.01), -1.0, 1.0)
	var steer := Settings.get_s("controls.mouse_mode") == "steer" and not Input.is_action_pressed("free_look")
	_mouse = Controls.take_mouse_delta() if steer else Vector2.ZERO
	_brake = Controls.trigger("brake")
	if Settings.get_s("controls.sprint_mode") == "hold":
		running = Input.is_action_pressed("sprint")
	elif Input.is_action_just_pressed("sprint"):
		running = not running
	if Settings.get_s("controls.sprint_mode") == "toggle" and _move.length() < 0.2:
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
		if bench_on():
			speed = float(bench.call("bill_jump", speed, mass))
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
	last_flip_offset = flip_offset(along, impulse)
	flipping = last_flip_offset != Vector3.ZERO
	apply_impulse(impulse * mass, global_transform.basis * center_of_mass + last_flip_offset)
	last_launch_speed = speed
	_no_spring_s = 0.18
	airborne = true
	jumped.emit(speed)
	if is_player:
		Rumble.play("jump_launch")


## Where the launch push passes the centre of mass (world offset), for a flip: holding crouch as a
## charged jump is let go leans the push onto the feet on one side, so the same impulse leaves the
## ground off-centre and the body takes off spinning (stick forward = front flip, back = backflip,
## sideways = side flip). The flight computer picks how far off-centre: far enough that the body
## turns gameplay.flip_turns over the predicted flight (2 vz / g), times how far the stick is pushed.
## It can move the push at most to the grounded foot furthest that way (all the push through it),
## times gameplay.flip_lean. Without that aim, the same lean made 1.9 turns forwards, 2.3 backwards
## and 7.7 sideways (the body's roll inertia is a fraction of its pitch inertia): Emerson's "side
## flip way too fast". Zero without crouch held or in bench mode. `launch` is the launch velocity.
func flip_offset(along: Vector3, launch: Vector3) -> Vector3:
	if bench_mode() or not Input.is_action_pressed("crouch") or along.length() < 0.1:
		return Vector3.ZERO
	var away := -along.normalized()
	var com := global_transform * center_of_mass
	var reach := 0.0
	for leg: Dictionary in legs:
		if leg["contact"] or leg["sole_contact"]:
			reach = maxf(reach, ((leg["foot"] as Vector3) - com).dot(away))
	var most := reach * Settings.get_f("gameplay.flip_lean")
	var g := float(ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)) * gravity_scale
	var flight := 2.0 * maxf(launch.y, 0.5) / maxf(g, 0.1)
	var spin := TAU * Settings.get_f("gameplay.flip_turns") * minf(_move.length(), 1.0) / flight
	# Spin per metre of offset: the impulse's moment (r x J) through the inverse inertia about the
	# axis it turns, worked in body axes (inertia is the principal x pitch, y yaw, z roll).
	var b := global_transform.basis.orthonormalized()
	var torque_axis := b.inverse() * away.cross(launch * mass)
	var per_m := (torque_axis / inertia).length()
	if per_m <= 0.0:
		return Vector3.ZERO
	return away * minf(spin / per_m, most)


## Holding crouch in the air tucks the legs in (released, they open out again over air.tuck_s). The
## body's inertia follows the legs (the stance inertia less what the tuck takes off, per axis from
## _measure_leg_inertia) and its spin rises or falls to keep the angular momentum, like a diver.
func _tuck_body(state: PhysicsDirectBodyState3D, dt: float, wants_tuck: bool) -> void:
	var a: Dictionary = _t.get("air", {})
	var rate := 1.0 / maxf(float(a.get("tuck_s", 0.12)), 0.01)
	flip_tuck = move_toward(flip_tuck, 1.0 if wants_tuck else 0.0, rate * dt)
	var t := maxf(flip_tuck, air_tuck)
	if absf(t - _body_tuck) < 0.0001:
		return
	if _stance_inertia == Vector3.ZERO:
		_stance_inertia = inertia
	var before := tucked_inertia(_body_tuck)
	var after := tucked_inertia(t)
	var basis := state.transform.basis.orthonormalized()
	var w_local := basis.inverse() * state.angular_velocity
	state.angular_velocity = basis * (w_local * before / after)
	inertia = after
	_body_tuck = t


## The body's principal inertia (body axes x pitch, y yaw, z roll) with the legs tucked by `t`.
func tucked_inertia(t: float) -> Vector3:
	var base := _stance_inertia if _stance_inertia != Vector3.ZERO else inertia
	var off := Vector3.ZERO
	for i: int in 3:
		var pair: Vector2 = leg_inertia[["pitch", "yaw", "roll"][i]]
		off[i] = (pair.x - pair.y) * t
	return Vector3(maxf(base.x - off.x, base.x * 0.2), maxf(base.y - off.y, base.y * 0.2), maxf(base.z - off.z, base.z * 0.2))


# --- physics -----------------------------------------------------------------------------------


func _integrate_forces(state: PhysicsDirectBodyState3D) -> void:
	var dt := state.step
	_read_input(dt)
	if bench != null:
		bench.set("drive_force_n", Vector3.ZERO)
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

	# Stride grows with speed (Emerson 2026-09-30: at a sprint the legs trailed metres behind, went
	# straight and the body sagged). A foot lands _stride_half ahead of its rest spot and steps again
	# once as far behind, so it spends a whole swing of the other pair planted; past the legs' reach
	# (feet.stride_half_max_m) the cadence quickens instead.
	var fdef: Dictionary = _t.get("feet", {})
	var planar := v - up * v.dot(up)
	var speed := planar.length()
	var cap := float(fdef.get("stride_half_max_m", 1.3))
	var half_min := float(fdef.get("stride_half_min_m", 0.45))
	_stride_half = clampf(speed * _step_s * 0.5, half_min, cap)
	_swing_now = _step_s
	if speed * _step_s > 2.0 * _stride_half:
		_swing_now = maxf(2.0 * _stride_half / speed, float(fdef.get("swing_min_s", 0.14)))
	if bench_on() and legs.size() > 0:
		# Real hips swing the foot at their own pace (lane B6): the step takes as long as the joints need.
		_swing_now = maxf(_swing_now, float(bench.call("min_swing_s", 2.0 * _stride_half, float(legs[0]["upper_len"]) + float(legs[0]["lower_len"]))))
	var lead := planar.normalized() * _stride_half if speed > 0.3 else Vector3.ZERO
	# The rear legs splay back and the fronts forward, so at speed each stride is gathered in under
	# the body, as in the anime run: rears land further forward (feet.gather_rear_m), fronts a little
	# further back (feet.gather_front_m). A rear foot trailing behind its rest spot runs out of reach
	# much sooner than a front one, hence the bigger share.
	# Gathered at least as far as the stride needs (lane A3 part 4, item 4): a long stride centred on the
	# rest spot overreaches the front legs forward and the rears back, so the gather follows the stride
	# length as well as the run speed (while speeding up, or slowed by a jump charge, it lagged behind).
	var reach_share := clampf((_stride_half - half_min) / maxf(cap - half_min, 0.01), 0.0, 1.0)
	var run_dir := planar.normalized() * maxf(_run_fraction(state), reach_share) if speed > 0.3 else Vector3.ZERO
	var gather_rear := run_dir * float(fdef.get("gather_rear_m", 0.0))
	var gather_front := -run_dir * float(fdef.get("gather_front_m", 0.0))
	var load_margin := float(sus.get("load_margin_m", 0.05))
	# Crouching compresses the legs, but never so far that the belly meets the ground (lane A3 part 4:
	# the full crouch and the jump charge sat the pod on the dirt, the springs unloaded and it slid on
	# its belly; Emerson's "scraping the bottom"). suspension.max_drop_m caps crouch + run drop.
	var crouch_drop := crouch * float(sus.get("crouch_fraction", 0.45)) * float(legs[0]["rest_len"]) if legs.size() > 0 else 0.0
	crouch_drop = clampf(crouch_drop, 0.0, maxf(float(sus.get("max_drop_m", INF)) - run_drop, 0.0))
	grounded_legs = 0
	var normal_sum := Vector3.ZERO
	for leg: Dictionary in legs:
		var out_w := xf.basis.x * signf((leg["hip"] as Vector3).x) * splay
		var cast_w := xf * (leg["spring_at"] as Vector3) + out_w
		var shift := _within_reach(leg, xf, out_w + lead + (gather_front if leg["front"] else gather_rear))
		_cast_sole(leg, space, xf, _keep_apart_shift(leg, xf, shift), margin)
		var rest := float(leg["rest_len"]) - crouch_drop - run_drop
		rest += (tilt + run_tilt) if leg["front"] else -(tilt + run_tilt)
		var query := PhysicsRayQueryParameters3D.create(cast_w, cast_w - up * (rest + margin), RAY_MASK, [get_rid()])
		var hit := space.intersect_ray(query)
		# The long ray only places the feet; a leg carries load (and counts as grounded) when the
		# ground is within its rest length plus a few centimetres, or, after a launch, only once
		# it is actually compressed again. So a mech just off the ground cannot drive or steer.
		leg["contact"] = not hit.is_empty()
		leg["loaded"] = false
		leg["ground_force_n"] = 0.0
		leg["ground_demand_n"] = 0.0
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
			leg["ground_demand_n"] = force
			# Test bench: a leg cannot push harder than its weakest joint can hold (it folds instead).
			if bench_on():
				leg["ground_demand_n"] = float(bench.call("shock_demand", force, compression, rest, -point_v.dot(up), mass / legs.size()))
				force = minf(force, float(bench.call("leg_force_cap", leg, point_v.dot(up) > 0.05)))
			leg["ground_force_n"] = force
			state.apply_force(up * force, cast_w - xf.origin)

	ground_normal = normal_sum.normalized() if grounded_legs > 0 else Vector3.UP
	var on_ground := grounded_legs >= 2 and _no_spring_s <= 0.0
	if on_ground:
		_since_ground = 0.0
		_on_ground_s += dt
		if airborne and _air_s > 0.15:
			_on_landed(-_fall_speed)
		airborne = false
		flipping = false
		_air_s = 0.0
		_stuck_s = 0.0
		_update_slide(v, dt)
		_drive(state, v)
		_turn(state, xf.basis, w, dt)
		_steady(state, w, 0.0)
	else:
		_air_s += dt
		_since_ground += dt
		_on_ground_s = 0.0
		if grounded_legs == 0:
			airborne = true
		_fall_speed = v.dot(Vector3.UP)
		_tuck_body(state, dt, airborne and Input.is_action_pressed("crouch"))
		if airborne and air_control_on():
			_air_legs(state, dt)
		else:
			_aim_yaw = _yaw_of(xf.basis)
		skidding = false
		slide_amount = 0.0
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
	if not airborne:
		_settle_legs(state, dt)
		if _body_tuck > 0.0:
			_tuck_body(state, dt, false)
	_air_drag(state, v)
	_keel(state, w)
	_pitch_aim(dt)


func air_control_on() -> bool:
	return not bench_mode() and not hauling and Settings.get_b("gameplay.air_control")


## Leg-swing turning in the air (lane A3 part 4, Emerson 2026-09-30: air movement "only based on
## the movement of legs or whatever in real life would give the movement; small is fine; some
## mechanic of direction change; no teleportation"). Nothing outside pushes or turns the body in
## flight; the pilot has the legs. Swinging the outstretched legs one way turns the body the other way
## (the legs take angular momentum, the body gives it up), and bringing them back tucked turns it back
## by less, because tucked legs have a smaller moment of inertia; so each sweep-tuck-return-untuck
## cycle leaves the body turned a little, the way a cat or an astronaut turns. Yaw is the hips'
## side-to-side swing, pitch the fore-aft swing, towards the aim (mouse / right stick) and the aim
## pitch. The reaction is an internal torque impulse equal and opposite to the change in the legs'
## angular momentum, so body + legs keep the angular momentum they left the ground with. The swing is
## limited by air.swing_max_deg and by the hip motors' rate and acceleration (air.swing_deg_s,
## air.swing_accel_deg_s2; 4 legs x ~1,000 kg m^2 at 1,200 deg/s^2 is about 20 kN m a hip, inside the
## hip_yaw actuator's rated 30 kN m).
func _air_legs(state: PhysicsDirectBodyState3D, dt: float) -> void:
	var a: Dictionary = _t.get("air", {})
	var basis := state.transform.basis.orthonormalized()
	var aim_cfg: Dictionary = Registry.tune("aim", {})
	_aim_yaw -= deg_to_rad(float(_t.get("turn", {}).get("rate_deg_s", 90.0))) * _aim.x * dt
	_aim_yaw -= deg_to_rad(float(aim_cfg.get("mouse_turn_deg_per_px", 0.09))) * _mouse.x
	var yaw := _yaw_of(basis)
	var lead := deg_to_rad(float(a.get("yaw_lead_deg", 90.0)))
	var diff := wrapf(_aim_yaw - yaw, -PI, PI)
	if absf(diff) > lead:
		_aim_yaw = yaw + clampf(diff, -lead, lead)
	var want := Basis(Vector3.UP, _aim_yaw) * Basis(Vector3.RIGHT, deg_to_rad(aim_pitch_deg))
	var err_q := (basis.inverse() * want).get_rotation_quaternion()
	var angle := err_q.get_angle()
	if angle > PI:
		angle -= TAU
	var err_axis := err_q.get_axis() if absf(angle) > 0.0001 else Vector3.ZERO
	var err := err_axis * angle  # body frame: y = yaw still to go, x = pitch still to go
	var e2 := Vector2(err.y, 0.0 if flipping else err.x)
	_step_air_swing(e2, a, dt)
	var tuck := air_tuck
	var i_yaw: Vector2 = leg_inertia["yaw"]
	var i_pitch: Vector2 = leg_inertia["pitch"]
	var local := Vector3(lerpf(i_pitch.x, i_pitch.y, tuck) * _swing_w.y, lerpf(i_yaw.x, i_yaw.y, tuck) * _swing_w.x, 0.0)
	var now := basis * local
	state.apply_torque_impulse(-(now - leg_momentum))
	leg_momentum = now


## One tick of the sweep-tuck-return-untuck cycle. e2 is the turn still wanted (x yaw, y pitch, body
## frame, radians); the legs sweep the opposite way, outstretched, across their whole range (from
## -swing_max to +swing_max along the sweep), then tuck and come back tucked to the far side for the
## next sweep (or to the middle when the turn is done).
func _step_air_swing(e2: Vector2, a: Dictionary, dt: float) -> void:
	var limit := deg_to_rad(float(a.get("swing_max_deg", 35.0)))
	var rate := deg_to_rad(float(a.get("swing_deg_s", 170.0)))
	var accel := deg_to_rad(float(a.get("swing_accel_deg_s2", 1500.0)))
	var dead := deg_to_rad(float(a.get("deadband_deg", 2.0)))
	var tuck_rate := 1.0 / maxf(float(a.get("tuck_s", 0.12)), 0.01)
	var wants := e2.length() > dead
	var goal := air_swing  # where the legs are heading this tick (staying put unless a phase moves them)
	match air_phase:
		Swing.IDLE:
			if wants:
				_swing_dir = -e2.normalized()
				air_phase = Swing.SWEEP
		Swing.SWEEP:
			goal = _swing_dir * limit if e2.dot(-_swing_dir) > dead else air_swing
			if _legs_reach(goal, accel):
				air_phase = Swing.TUCK
		Swing.TUCK:
			air_tuck = move_toward(air_tuck, 1.0, tuck_rate * dt)
			if air_tuck >= 1.0:
				air_phase = Swing.RETURN
				if wants:
					_swing_dir = -e2.normalized()
		Swing.RETURN:
			goal = -_swing_dir * limit if wants else Vector2.ZERO
			if _legs_reach(goal, accel):
				air_phase = Swing.UNTUCK
		Swing.UNTUCK:
			air_tuck = move_toward(air_tuck, 0.0, tuck_rate * dt)
			if air_tuck <= 0.0:
				air_phase = Swing.SWEEP if wants and air_swing != Vector2.ZERO else Swing.IDLE
	var to_goal := goal - air_swing
	var stop := _swing_w.length_squared() / (2.0 * accel)
	var target_w := to_goal.normalized() * rate if to_goal.length() > stop + 0.005 else Vector2.ZERO
	_swing_w = _swing_w.move_toward(target_w, accel * dt)
	air_swing += _swing_w * dt


## True once the legs have come to rest at `goal`.
func _legs_reach(goal: Vector2, accel: float) -> bool:
	return air_swing.distance_to(goal) < 0.03 and _swing_w.length() < accel * 0.02


## Back on the ground (or with leg swing off) the legs return to their stance; whatever angular
## momentum they still carry goes back into the body through the hips, so none is made or lost.
func _settle_legs(state: PhysicsDirectBodyState3D, dt: float) -> void:
	if leg_momentum != Vector3.ZERO:
		state.apply_torque_impulse(leg_momentum)
		leg_momentum = Vector3.ZERO
	_swing_w = Vector2.ZERO
	air_swing = air_swing.move_toward(Vector2.ZERO, 3.0 * dt)
	air_tuck = move_toward(air_tuck, 0.0, 6.0 * dt)
	if air_swing == Vector2.ZERO and air_tuck == 0.0:
		air_phase = Swing.IDLE


## Air drag, F = 1/2 rho Cd A v^2 against the motion (physics.air_density, the mech's
## physics.drag_cd_area_m2): about 2 kN at 20 m/s, 0.35 m/s^2 on 5.4 t. Replaces Godot's blanket
## 0.1/s damping, which was six times that at 20 m/s.
func _air_drag(state: PhysicsDirectBodyState3D, v: Vector3) -> void:
	var p: Dictionary = Registry.tune("physics", {})
	var cda := float(p.get("drag_cd_area_m2", 7.0))
	var f := 0.5 * float(p.get("air_density", 1.2)) * cda * v.length_squared()
	if f > 0.0:
		state.apply_central_force(-v.normalized() * f)


## Game mode only (Emerson, 2026-09-30: normal play must not tip the spider over, and there are no
## fall or flail animations yet). Past upright.keep_deg of lean from the ground under it (world up
## with under two legs down), a righting torque grows with the lean, capped, and the tilting spin is
## damped, so bumps, hard turns and landings settle back instead of rolling it. Weaker with under two
## legs loaded (keep_air_factor); none at all in flight (lane A3 part 4: no torque from nowhere). Off with Balance assist off, and in bench mode, which stays raw physics.
func _keel(state: PhysicsDirectBodyState3D, w: Vector3) -> void:
	var u: Dictionary = _t.get("upright", {})
	var keep := deg_to_rad(float(u.get("keep_deg", 0.0)))
	if keep <= 0.0 or bench_mode() or not Settings.get_b("gameplay.upright_assist"):
		return
	if airborne and not hauling:
		return  # no torque from nowhere in flight: only the legs' swing (_air_legs) turns the body
	# (A ledge haul counts as airborne but the legs grip the ledge, so their righting stays.)
	var up := state.transform.basis.y
	var target := ground_normal if grounded_legs >= 2 else Vector3.UP
	# At a run the chassis is held much closer to the ground's slope (upright.keep_run_deg): with the
	# walking dead zone it pitched freely over every crest at 13 m/s and dived nose-first (Emerson,
	# 2026-09-30: "shift running breaks the legs and it hits the ground").
	var fast := _run_fraction(state)
	if grounded_legs >= 2:
		keep = lerpf(keep, deg_to_rad(float(u.get("keep_run_deg", keep))), fast)
	var lean := up.angle_to(target)
	if lean <= keep:
		return
	var axis := up.cross(target)
	if axis.length() < 0.0001:
		return
	var factor := 1.0 if grounded_legs >= 2 else float(u.get("keep_air_factor", 0.35))
	var push := float(u.get("keep_stiffness", 20.0)) * minf((lean - keep) / keep, 3.0)
	var spin := w - up * w.dot(up)
	var damping := float(u.get("keep_damping", 4.0)) * (1.0 + fast * float(u.get("run_damping_boost", 0.0)))
	var accel := (axis.normalized() * push - spin * damping) * factor
	state.apply_torque(accel * inertia.x)


## The slide (lane A3 part 4, Emerson: "a slide button that is somehow directional... the momentum
## fights it a bit"; "L2 depth sets how much grip breaks"). Above skid.min_speed_m_s the slide trigger
## (Ctrl / L2, analog) breaks the feet's grip by its depth: a light squeeze drifts, a full pull skates
## on kinetic friction. Below that speed the same trigger is the brake. Let go and the legs catch the
## body over skid.recover_s.
func _update_slide(v: Vector3, dt: float) -> void:
	var sk: Dictionary = _t.get("skid", {})
	var speed := Vector3(v.x, 0.0, v.z).length()
	var want := 0.0
	if _brake > 0.05 and speed > 1.0 and (slide_amount > 0.0 or speed > float(sk.get("min_speed_m_s", 4.0))):
		want = _brake
	var rate := 8.0 if want > slide_amount else 1.0 / maxf(float(sk.get("recover_s", 0.35)), 0.01)
	slide_amount = move_toward(slide_amount, want, rate * dt)
	var was := skidding
	skidding = slide_amount > 0.3
	if is_player and skidding != was:
		if skidding:
			Rumble.play("skid")
		else:
			Rumble.stop("skid")


## The legs' drive: toward the stick's speed, limited by the feet's grip and by the drive's peak power
## (drive.peak_power_w: speeding up at v takes F v; 600 kW gives 0-50 km/h in about 1.3 s on 5.4 t).
## Sliding, it blends (by the trigger's depth) into kinetic friction (Settings "Slide friction",
## mu x g) whose direction the stick's sideways part tilts: the path bends toward the stick at the
## cost of drag, so momentum fights it; with no sideways stick it just drags the slide down.
func _drive(state: PhysicsDirectBodyState3D, v: Vector3) -> void:
	var d: Dictionary = _t.get("drive", {})
	var n := ground_normal
	var fwd := _flat(-state.transform.basis.z, n)
	var right := _flat(state.transform.basis.x, n)
	var top := float(d.get("run_m_s", 12.0)) if running else float(d.get("walk_m_s", 7.0))
	var back := float(d.get("run_back_m_s", 5.0)) if running else float(d.get("reverse_m_s", 5.0))
	var side := float(d.get("run_side_m_s", 5.0)) if running else float(d.get("strafe_m_s", 5.0))
	top *= speed_scale
	back *= speed_scale
	side *= speed_scale
	if bench_mode():
		var cap := _bench_speed_cap * (float(bench.call("speed_factor")) if bench_on() else 1.0)
		top = minf(top, cap)
		back = minf(back, cap)
		side = minf(side, cap)
	var target := fwd * (_move.y * (top if _move.y >= 0.0 else back)) + right * (_move.x * side)
	target = target.limit_length(maxf(top if _move.y >= 0.0 else back, side))
	var planar := v - n * v.dot(n)
	var speed := planar.length()
	var dv := target - planar
	var limit := float(d.get("accel_m_s2", 9.0))
	var power := float(d.get("peak_power_w", 0.0))
	var gaining := planar.dot(dv)
	if power > 0.0 and gaining > 0.0 and speed > 0.5:
		limit = minf(limit, power / (mass * speed))
	var grip := float(d.get("grip_m_s2", 16.0)) * grounded_legs / maxf(legs.size(), 1)
	if slide_amount <= 0.0 and _brake > 0.05:
		dv = -planar
		limit = float(d.get("brake_m_s2", 20.0)) * _brake
	if bench_on():
		# Test bench: the push is also bounded by the torque the joints have left after holding the body up,
		# and by the power the bus has left after the legs' own draw.
		limit = minf(limit, float(bench.call("drive_force_cap", dv)) / mass)
		if gaining > 0.0 and speed > 0.5:
			limit = minf(limit, float(bench.call("drive_power_w")) / (mass * speed))
	var acc := (dv * 6.0).limit_length(minf(limit, grip))
	if slide_amount > 0.0 and speed > 0.1:
		# Skating feet: the ground force is kinetic friction, mu x g, always there. The legs can only
		# tilt it: the stick's sideways part (against the path) bends the path that way, at the
		# cost of drag; straight ahead or none, it is all drag.
		var skate := slide_friction() * 9.81 * grounded_legs / maxf(legs.size(), 1)
		var v_dir := planar / speed
		var push := fwd * _move.y + right * _move.x
		var lat := push - v_dir * push.dot(v_dir)
		var u := (-v_dir + lat * float(_t.get("skid", {}).get("bend", 1.2))).normalized()
		acc = acc.lerp(u * minf(skate, speed * 6.0), slide_amount)
	# The legs push on the ground, so the drive also turns the body the way a push where the loaded
	# feet meet the ground would (Emerson 2026-10-01: walking and running "feel like an animation,
	# not physics"): below the centre of mass, speeding up squats the body onto its rear legs,
	# slowing dips the nose and a turn leans it out, all through the leg springs. drive.at_feet is
	# the share of that lever the legs do not hold back (0 = the old push with no moment).
	var at := Vector3.ZERO
	var loaded := 0
	for leg: Dictionary in legs:
		if leg["loaded"]:
			at += leg["hit"] as Vector3
			loaded += 1
	# Touching down, the legs' controllers are busy taking the landing; on fewer than three loaded
	# legs, or charging a jump (the legs hold the body level for a clean launch), they add nothing.
	# The share fades in over drive.at_feet_settle_s after landing.
	var share := float(d.get("at_feet", 0.0)) * clampf(_on_ground_s / maxf(float(d.get("at_feet_settle_s", 0.4)), 0.01), 0.0, 1.0)
	if grounded_legs < 3 or charging or loaded == 0:
		share = 0.0
	var com := state.transform * center_of_mass
	var moment := Vector3.ZERO
	if share > 0.0:
		var drop := (com - at / loaded).dot(n)
		moment = (-n * drop).cross(acc * mass) * share
	# Actuators cannot change their torque at once: the moment is smoothed over drive.at_feet_lag_s,
	# so the steady squat, dip and lean come through but the jolts of grip coming and going over rough
	# ground do not (unsmoothed, they rocked the body 40 deg/s and the score route's running jump
	# launched mid-rock and tumbled).
	var lag := maxf(float(d.get("at_feet_lag_s", 0.25)), 0.01)
	_drive_moment += (moment - _drive_moment) * minf(state.step / lag, 1.0)
	state.apply_central_force(acc * mass)
	state.apply_torque(_drive_moment)
	_drive_force = acc * mass
	if bench != null:
		bench.set("drive_force_n", _drive_force)


## The feet's mean horizontal reach from the centre of mass (the lever the slide's friction spins on).
func _feet_reach() -> float:
	var r := 0.0
	for leg: Dictionary in legs:
		var d := (leg["sole_stance"] as Vector3) - center_of_mass
		r += Vector2(d.x, d.z).length()
	return r / maxf(legs.size(), 1)


## Kinetic friction of the feet skating on the ground (mu; Settings > Gameplay > Movement).
func slide_friction() -> float:
	return Settings.get_f("gameplay.slide_friction") if is_player else float(_t.get("skid", {}).get("friction", 0.4))


func _turn(state: PhysicsDirectBodyState3D, basis: Basis, w: Vector3, dt: float) -> void:
	var tt: Dictionary = _t.get("turn", {})
	var aim_cfg: Variant = Registry.tune("aim", {})
	var turn_input := _aim.x
	var yaw := _yaw_of(basis)
	var rate := float(tt.get("run_rate_deg_s", 70.0)) if running else float(tt.get("rate_deg_s", 95.0))
	var stick_rate := float(tt.get("rate_deg_s", 90.0))
	var accel := float(tt.get("accel_deg_s2", 420.0))
	# Sliding, the body turns only as the pilot asks (right stick / mouse), up to the slide turn rate
	# at a full slide: pure sideways drift with no turn input, a fast pivot at full deflection.
	if slide_amount > 0.0:
		var slide_rate := Settings.get_f("gameplay.slide_turn_deg_s") if is_player else float(tt.get("skid_rate_deg_s", 200.0))
		rate = lerpf(rate, slide_rate, slide_amount)
		stick_rate = lerpf(stick_rate, slide_rate, slide_amount)
		# The spin comes from the skating feet's friction: at most mu m g r about the centre of mass
		# (r = the feet's mean reach), about 220 deg/s^2 at mu 0.4 on the Juggernaut.
		var spin := rad_to_deg(slide_friction() * 9.81 * _feet_reach() * mass / maxf(inertia.y, 1.0))
		accel = lerpf(accel, spin, slide_amount)
	_aim_yaw -= deg_to_rad(stick_rate) * turn_input * dt
	_aim_yaw -= deg_to_rad(float((aim_cfg as Dictionary).get("mouse_turn_deg_per_px", 0.09))) * _mouse.x
	var diff := wrapf(_aim_yaw - yaw, -PI, PI)
	var lead := deg_to_rad(75.0)
	if absf(diff) > lead:
		_aim_yaw = yaw + clampf(diff, -lead, lead)
		diff = clampf(diff, -lead, lead)
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
## 0 at a walk, 1 at full run speed (for the tuning that firms up at speed).
func _run_fraction(state: PhysicsDirectBodyState3D) -> float:
	var d: Dictionary = _t.get("drive", {})
	var walk := float(d.get("walk_m_s", 7.0))
	var run := float(d.get("run_m_s", 12.0))
	var v := state.linear_velocity
	return clampf((Vector3(v.x, 0.0, v.z).length() - walk) / maxf(run - walk, 0.1), 0.0, 1.0)


func _steady(state: PhysicsDirectBodyState3D, w: Vector3, recover: float) -> void:
	if not Settings.get_b("gameplay.upright_assist"):
		return
	var u: Dictionary = _t.get("upright", {})
	var tilt_w := w - ground_normal * w.dot(ground_normal)
	var boost := 1.0 + _run_fraction(state) * float(u.get("run_damping_boost", 0.0)) if not bench_mode() else 1.0
	var torque := -tilt_w * float(u.get("damping", 2.0)) * boost
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


## Looking and aiming up and down (mouse or right stick). The look pitch goes from aim.look_min_deg
## to look_max_deg (the camera and the wire anchors follow it; lane A3 part 4, so the anchor can aim
## high); the body tilts after it on its legs, within aim.pitch_min/max_deg, when gameplay.aim_tilt is
## on, and eases back level when it is off.
func _pitch_aim(dt: float) -> void:
	var a: Dictionary = Registry.tune("aim", {})
	var look_min := float(a.get("look_min_deg", -25.0))
	var look_max := float(a.get("look_max_deg", 75.0))
	var tilt_min := float(a.get("pitch_min_deg", -8.0))
	var tilt_max := float(a.get("pitch_max_deg", 18.0))
	var mouse_deg := -_mouse.y * float(a.get("mouse_pitch_deg_per_px", 0.05))
	if Settings.get_s("gameplay.aim_mode") == "angle":
		# Analog first: the stick's deflection is the angle (full up is the top of the range, half is half,
		# letting go springs back level), the mouse still moves the aim in steps and the stick adds to it.
		# The body tilts to its own, shorter range in proportion; the aim line (camera, wire) gets the long one.
		_mouse_pitch = clampf(_mouse_pitch + mouse_deg, look_min, look_max)
		var s := _aim_deflection
		var follow := 1.0 - exp(-float(a.get("angle_follow_per_s", 10.0)) * dt)
		look_pitch_deg = lerpf(look_pitch_deg, clampf(_mouse_pitch + s * (look_max if s > 0.0 else -look_min), look_min, look_max), follow)
		if not Settings.get_b("gameplay.aim_tilt"):
			aim_pitch_deg = move_toward(aim_pitch_deg, 0.0, 40.0 * dt)
			return
		aim_pitch_deg = lerpf(aim_pitch_deg, clampf(_mouse_pitch + s * (tilt_max if s > 0.0 else -tilt_min), tilt_min, tilt_max), follow)
		return
	_mouse_pitch = look_pitch_deg
	look_pitch_deg += _aim.y * float(a.get("look_rate_deg_s", 60.0)) * dt + mouse_deg
	look_pitch_deg = clampf(look_pitch_deg, look_min, look_max)
	if not Settings.get_b("gameplay.aim_tilt"):
		aim_pitch_deg = move_toward(aim_pitch_deg, 0.0, 40.0 * dt)
		return
	aim_pitch_deg = clampf(look_pitch_deg, tilt_min, tilt_max)


## The look direction in the world: the body's heading, pitched by look_pitch_deg.
func look_direction() -> Vector3:
	return (Basis(Vector3.UP, _yaw_of(global_transform.basis)) * Basis(Vector3.RIGHT, deg_to_rad(look_pitch_deg)) * Vector3.FORWARD).normalized()


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
			# not tucked in: ANALYSIS.md's airborne legs), swung and tucked by _air_legs.
			target_world = xf * _keep_apart(leg, xf, _air_foot(leg))
		var t := float(leg["step_t"])
		if t >= 0.0:
			t += delta / _swing_now
			leg["step_t"] = t
			# Lifted, the foot travels with the body: its lift-off spot is kept in the body's frame
			# (item 4: held in the world, at 70 km/h the body ran ~1 m away from it in the first
			# tenth of the swing and the leg went straight).
			var from: Vector3 = xf * (leg["step_from_local"] as Vector3)
			var to: Vector3 = leg["step_to"] if not on_ground else target_world
			var foot := from.lerp(to, minf(t, 1.0)) + xf.basis.y * sin(minf(t, 1.0) * PI) * float(leg["step_lift"])
			leg["foot"] = xf * _keep_apart(leg, xf, xf.affine_inverse() * _clear_of_hip(leg, xf, foot))
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
				# Eased in the body's frame, so the feet travel with the mech: eased in world space
				# they were left behind at speed and a running jump dragged the legs straight.
				var local := xf.affine_inverse() * (leg["planted"] as Vector3)
				leg["planted"] = xf * local.lerp(xf.affine_inverse() * target_world, minf(delta * 20.0, 1.0))
				leg["planted_normal"] = target_normal
				leg["needs_seat"] = true
			elif _overreaching(leg, xf) or (gap.length() > maxf(0.9, 2.0 * _stride_half) or absf(gap.dot(xf.basis.y)) > reseat or seat) and (not _partner_stepping(str(leg["name"])) or gap.length() > 1.4 * maxf(0.9, 2.0 * _stride_half)):
				# Step when the foot has drifted too far from where it should stand, is left
				# hovering above (or sunk into) the ground, or has just come down from the air (a
				# landing, or the drop at spawn) and is not yet where its sole belongs. A short
				# re-seat step lifts the foot less than a full stride. A foot badly overdue (1.4x the
				# stride behind) goes even out of turn rather than be dragged until the leg is straight.
				leg["step_from_local"] = xf.affine_inverse() * (leg["planted"] as Vector3)
				leg["step_to"] = target_world
				leg["step_t"] = 0.0
				leg["step_lift"] = _step_lift_m * clampf(gap.length() / 0.9, 0.3, 1.0)
				leg["needs_seat"] = false
			elif gap.length() <= 0.05:
				leg["needs_seat"] = false
			leg["foot"] = leg["planted"]
		# The foot pivots about its sole on the ground; the IK chain ends at its ankle above that.
		var planted := float(leg["step_t"]) < 0.0 and on_ground
		var tilt := Basis(Quaternion(Vector3.UP, _foot_up(leg, xf, planted, max_tilt, delta)))
		leg["end_local"] = to_local(leg["foot"]) + tilt * (leg["end_offset"] as Vector3)
		leg["tilt"] = tilt
	# Second pass: with every foot placed, swivel each knee about its hip-ankle line clear of the other legs.
	for leg: Dictionary in legs:
		var tilt: Basis = leg["tilt"]
		var end: Vector3 = leg["end_local"]
		var pose := MechBuilder.pose_segments(leg, end, tilt, _leg_scale, _knee_swivel(leg, end, delta))
		leg["knee_local"] = pose["knee"]
		leg["ankle_local"] = pose["end"]
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


## Where a hanging foot is in the body frame: its stance spot swung about the leg's hip pivot by the
## air swing (yaw about the body's up, pitch about its side axis) and drawn in by the tuck.
func _air_foot(leg: Dictionary) -> Vector3:
	var pivot: Vector3 = leg["pivot"]
	var reach := ((leg["sole_stance"] as Vector3) - pivot) * lerpf(1.0, float(_t.get("air", {}).get("tuck_scale", 0.55)), air_tuck)
	return pivot + Basis(Vector3.UP, air_swing.x) * (Basis(Vector3.RIGHT, air_swing.y) * reach)


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
	var had: Vector3 = leg["foot_up"]
	# Nearly parallel vectors make slerp's float32 axis miss unit length (engine error), so snap.
	var up := want if had.angle_to(want) < 0.002 else had.slerp(want, minf(delta * 12.0, 1.0)).normalized()
	leg["foot_up"] = up
	return up


## The foot target's shift from its stance spot (splay, stride lead, gather; world frame), shortened
## so the target stays inside feet.target_reach of the leg's reach from the hip pivot and no closer
## than feet.min_reach to it (horizontally): at a gallop the lead follows the momentum, which after a
## hard turn points well off to the side, outward or in under the body (item 4).
func _within_reach(leg: Dictionary, xf: Transform3D, shift_w: Vector3) -> Vector3:
	var fdef: Dictionary = _t.get("feet", {})
	var leg_len := (float(leg["upper_len"]) + float(leg["lower_len"])) * _leg_scale
	var reach := leg_len * float(fdef.get("target_reach", 0.88))
	var near := leg_len * float(fdef.get("min_reach", 0.0))
	var pivot: Vector3 = leg["pivot"]
	var sole: Vector3 = leg["sole_stance"]
	var shift := xf.basis.inverse() * shift_w
	var t := 1.0
	while t > 0.0:
		var d := sole + shift * t - pivot
		if d.length() <= reach and Vector2(d.x, d.z).length() >= near:
			break
		t -= 0.1
	return shift_w * maxf(t, 0.0)


## A planted foot about to pull its leg straight (the ankle past feet.overreach of the leg's reach
## from the hip pivot), or drifted in under the hip (closer than feet.min_reach, horizontally), steps
## now, even out of turn (lane A3 part 5, item 4; and, lane A4 part 5, one that has drifted too close to another leg's foot or past its hip, see _keep_apart): after a sprinting turn the body keeps yawing while
## its momentum carries it sideways, and a foot drifting sideways runs out of reach (or under the body)
## long before it is a stride's length from its target.
func _overreaching(leg: Dictionary, xf: Transform3D) -> bool:
	var reach := (float(leg["upper_len"]) + float(leg["lower_len"])) * _leg_scale
	var ankle := xf.affine_inverse() * (leg["planted"] as Vector3) + (leg["end_offset"] as Vector3)
	var d := ankle - (leg["pivot"] as Vector3)
	var fdef: Dictionary = _t.get("feet", {})
	var apart_at := xf.affine_inverse() * (leg["planted"] as Vector3)
	return d.length() > reach * float(fdef.get("overreach", 0.93)) or Vector2(d.x, d.z).length() < reach * float(fdef.get("min_reach", 0.0)) or _keep_apart(leg, xf, apart_at).distance_to(apart_at) > 0.05


## A swinging foot kept at least feet.min_reach of the leg's reach from its hip, horizontally: a swing
## from under the body out to the side went straight past the hip and the knee flipped (item 4).
func _clear_of_hip(leg: Dictionary, xf: Transform3D, foot_w: Vector3) -> Vector3:
	var min_r := (float(leg["upper_len"]) + float(leg["lower_len"])) * _leg_scale * float(_t.get("feet", {}).get("min_reach", 0.0))
	if min_r <= 0.0:
		return foot_w
	var pivot: Vector3 = leg["pivot"]
	var local := xf.affine_inverse() * foot_w
	var flat := Vector2(local.x - pivot.x, local.z - pivot.z)
	if flat.length() >= min_r:
		return foot_w
	var out := flat.normalized() if flat.length() > 0.01 else Vector2(signf(pivot.x), 0.0)
	var pushed := out * min_r
	# Still inside the leg's reach in 3D: a lifted foot pushed out comes up or down toward hip height.
	var reach := (float(leg["upper_len"]) + float(leg["lower_len"])) * _leg_scale * 0.95
	var dy := local.y - pivot.y
	var max_dy := sqrt(maxf(reach * reach - min_r * min_r, 0.0))
	return xf * Vector3(pivot.x + pushed.x, pivot.y + clampf(dy, -max_dy, max_dy), pivot.z + pushed.y)


## How far (rad) leg `leg`'s knee is swivelled about its hip-ankle line this tick, eased towards the
## smallest swivel that keeps its bones feet.swivel_clear_m from every other leg's (or, failing that, the
## clearest one in +-feet.swivel_max_deg). The legs fold up and out like a spider's; in a tuck, a yawed
## air swing or a gallop's gathered stride two knees end up in the same place (lane A4 part 5, note 8).
func _knee_swivel(leg: Dictionary, end: Vector3, delta: float) -> float:
	var fdef: Dictionary = _t.get("feet", {})
	var clear := float(fdef.get("swivel_clear_m", 0.0))
	if clear <= 0.0:
		return 0.0
	var upper := float(leg["upper_len"]) * _leg_scale
	var lower := float(leg["lower_len"]) * _leg_scale
	var pivot: Vector3 = leg["pivot"]
	var reach := LegIK.reachable(pivot, end, upper, lower)
	var limit := deg_to_rad(float(fdef.get("swivel_max_deg", 55.0)))
	var steps := int(fdef.get("swivel_steps", 3))
	var best := 0.0
	var best_gap := -INF
	for i in range(0, 2 * steps + 1):
		var a := 0.0 if i == 0 else limit * ceili(i / 2.0) / steps * (1.0 if i % 2 == 1 else -1.0)
		var knee := LegIK.knee(pivot, reach, upper, lower, LegIK.swivelled(pivot, reach, leg["pole"], a))
		var gap := _clearance(leg, pivot, knee, reach)
		if gap >= clear:
			best = a
			best_gap = gap
			break
		if gap > best_gap + 0.02:
			best = a
			best_gap = gap
	var now := float(leg.get("swivel", 0.0))
	now = move_toward(now, best, float(fdef.get("swivel_rate", 8.0)) * delta)
	leg["swivel"] = now
	return now


## The closest any bone of leg `leg`, were it posed with this hip, knee and ankle, comes to another leg's.
func _clearance(leg: Dictionary, pivot: Vector3, knee: Vector3, ankle: Vector3) -> float:
	var d := INF
	for other: Dictionary in legs:
		if other == leg or not other.has("knee_local"):
			continue
		var op: Vector3 = other["pivot"]
		var ok: Vector3 = other["knee_local"]
		var oe: Vector3 = other["ankle_local"]
		d = minf(d, minf(minf(LegIK.segment_distance(pivot, knee, op, ok), LegIK.segment_distance(pivot, knee, ok, oe)), minf(LegIK.segment_distance(knee, ankle, op, ok), LegIK.segment_distance(knee, ankle, ok, oe))))
	return d


## `at` (a foot's spot in the body frame) moved the least it takes to keep the feet.apart_m between this
## leg's foot and every other leg's foot (where it is, and where it is going while it steps), in the
## order the hips are in: a rear foot stays behind the front foot on its side, a right foot to the right of
## the left ones. Two feet in the wrong order mean the legs cross (lane A4 part 5, Emerson's note 8: at a
## gallop a rear foot gathered forward past a front foot gathered back, and the bones passed through
## each other; the same in version 009, found by tests/test_leg_gap.gd). 0 turns it off.
func _keep_apart(leg: Dictionary, xf: Transform3D, at: Vector3) -> Vector3:
	var gap := float(_t.get("feet", {}).get("apart_m", 0.0))
	if gap <= 0.0:
		return at
	var inv := xf.affine_inverse()
	var hip: Vector3 = leg["hip"]
	var past := float(_t.get("feet", {}).get("hip_pass_m", 1000.0))
	for other: Dictionary in legs:
		if other == leg:
			continue
		var refs: Array = [other["foot"]]
		if float(other["step_t"]) >= 0.0:
			refs.append(other["step_to"])
		var oh: Vector3 = other["hip"]
		if signf(oh.x) == signf(hip.x):
			at.z = minf(at.z, oh.z + past) if hip.z < oh.z else maxf(at.z, oh.z - past)
		for ref_w: Vector3 in refs:
			var ref := inv * ref_w
			if signf(oh.x) == signf(hip.x):
				at.z = minf(at.z, ref.z - gap) if hip.z < oh.z else maxf(at.z, ref.z + gap)
			else:
				at.x = maxf(at.x, ref.x + gap) if hip.x > oh.x else minf(at.x, ref.x - gap)
	return at


## The same for a foot target given as a shift from its stance spot (world frame).
func _keep_apart_shift(leg: Dictionary, xf: Transform3D, shift_w: Vector3) -> Vector3:
	var sole: Vector3 = leg["sole_stance"]
	var at := sole + xf.basis.inverse() * shift_w
	return xf.basis * (_keep_apart(leg, xf, at) - sole)


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
		"slide": snappedf(slide_amount, 0.01),
		"charging": charging,
		"crouch": snappedf(crouch, 0.01),
		"hip_clearance_m": snappedf(clearance / maxf(n, 1), 0.01),
		"mass_kg": snappedf(mass, 0.1),
		"last_launch_m_s": snappedf(last_launch_speed, 0.01),
		"physics_mode": Settings.get_s("gameplay.physics_mode"),
		"bench": bench.call("telemetry") if bench_on() else {},
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
