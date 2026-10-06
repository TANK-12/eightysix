extends Camera3D
## The basic third-person camera with weight, plus a simple cockpit view (lane A5 builds the real
## cockpit). It trails the chassis, settles after turns, looks a little ahead of the motion, pulls in
## when terrain is in the way and shakes on footfalls, landings and (later) hits. "Free look" orbits
## it without turning the chassis; in "camera" mouse mode the mouse always orbits it.

var target: Node3D
var view := "third"
var _orbit := Vector2.ZERO
var _pos := Vector3.ZERO
var _look := Vector3.ZERO
var _shake := 0.0
var _shake_t := 0.0
var _noise := FastNoiseLite.new()
var _started := false
var _skip: Array[RID] = []  # the followed mech's own bodies, left out of the camera sweep
## The gunner's optics (Emerson's note 20 after 012): index into camera.third_person.optics_steps; 0 is no optics.
var zoom_i := 0
var _last_zoom_i := 1
var _inside := false  # the eye is in the pod: the mech's pod shell is not drawn and casts no shadow


func _ready() -> void:
	add_to_group("game_camera")
	top_level = true
	current = true
	view = Settings.get_s("gameplay.default_view")
	Settings.changed.connect(_on_setting_changed)
	_noise.frequency = 1.7


func follow(node: Node3D) -> void:
	target = node
	_started = false
	_inside = false
	_skip = _own_rids()
	if node.has_signal("landed"):
		node.connect("landed", func(impact: float) -> void: add_shake(clampf(impact / 12.0, 0.1, 1.0)))
	if node.has_signal("stepped"):
		node.connect("stepped", func(_leg: String) -> void: add_shake(0.06))
	# Lane A3: the 57 mm kicks the view, a hit taken jolts it (the Combat child is added with the mech).
	var combat := node.get_node_or_null("Combat")
	if combat != null:
		combat.connect("fired", func(_w: String, _a: String) -> void: add_shake(0.45))
		combat.connect("hit_taken", func(_k: String, dealt: float, _i: Dictionary) -> void: add_shake(clampf(dealt / 900.0, 0.15, 0.8)))


## Changing "Starting view" mid-game switches to it now (and bot scripts can pick the view).
func _on_setting_changed(key: String, value: Variant) -> void:
	if key == "gameplay.default_view":
		view = str(value)


func add_shake(amount: float) -> void:
	if Settings.get_b("accessibility.reduce_motion"):
		return
	_shake = maxf(_shake, amount * Settings.get_f("gameplay.camera_shake"))


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("camera_view"):
		view = "cockpit" if view == "third" else "third"
		_started = false
	if not current:
		return  # the Handler view owns the wheel while it is up
	if event.is_action_pressed("optics_zoom_in"):
		step_zoom(1)
	elif event.is_action_pressed("optics_zoom_out"):
		step_zoom(-1)
	elif event.is_action_pressed("zoom_optics"):
		toggle_optics()


## The optics magnification now (1 = no optics).
func zoom() -> float:
	var steps: Array = Registry.tune("camera.third_person", {}).get("optics_steps", [1])
	return float(steps[clampi(zoom_i, 0, steps.size() - 1)])


func step_zoom(by: int) -> void:
	var steps: Array = Registry.tune("camera.third_person", {}).get("optics_steps", [1])
	zoom_i = clampi(zoom_i + by, 0, steps.size() - 1)
	if zoom_i > 0:
		_last_zoom_i = zoom_i
	_started = false


## Middle mouse: straight into the optics at the last magnification, or back out.
func toggle_optics() -> void:
	zoom_i = 0 if zoom_i > 0 else _last_zoom_i
	_started = false


func _process(delta: float) -> void:
	if target == null or not is_instance_valid(target):
		return
	var cfg: Dictionary = Registry.tune("camera.third_person", {})
	var body_xf := target.global_transform
	if bool(target.get("skidding")) and (target.get("linear_velocity") as Vector3).length() > 3.0:
		add_shake(0.18)  # the skid grinds: a steady rumble while it slides
	_shake = move_toward(_shake, 0.0, delta * 2.5)
	_shake_t += delta
	var jitter := Vector3(_noise.get_noise_2d(_shake_t * 60.0, 0.0), _noise.get_noise_2d(0.0, _shake_t * 60.0), 0.0) * _shake * 0.35

	var optics := zoom_i > 0
	var inside := view == "cockpit" or optics
	cull_mask = 0xFFFFF & ~CombatFx.COCKPIT_SHELL_LAYER if inside else 0xFFFFF
	if inside != _inside:
		_inside = inside
		var pod := target.get_node_or_null("Combat")
		if pod != null:
			pod.call("set_cockpit_view", inside)
	if optics:
		# Down the 57 mm's bore from the cockpit: the middle of the view is where the gun points.
		var eye_at := eye_point(target)
		var combat := target.get_node_or_null("Combat")
		var bore: Vector3 = combat.call("gun_direction") if combat != null else -body_xf.basis.z
		fov = Settings.get_f("gameplay.fov_cockpit") / zoom()
		global_position = body_xf * eye_at
		look_at(global_position + bore, body_xf.basis.y if absf(bore.dot(body_xf.basis.y)) < 0.99 else Vector3.UP)
		return
	if view == "cockpit":
		var eye := eye_point(target)
		fov = Settings.get_f("gameplay.fov_cockpit")
		global_transform = body_xf * Transform3D(Basis.IDENTITY, eye)
		global_position += global_transform.basis * jitter * Settings.get_f("gameplay.head_bob")
		return

	var free := Input.is_action_pressed("free_look") or Settings.get_s("controls.mouse_mode") == "camera"
	if free:
		var turn := Controls.stick("aim") * deg_to_rad(float(cfg.get("free_look_deg_s", 140.0))) * delta
		var mouse := Controls.take_mouse_delta() * 0.005
		_orbit.x -= turn.x + mouse.x
		_orbit.y = clampf(_orbit.y - turn.y - mouse.y, -0.5, 0.9)
	else:
		_orbit = _orbit.lerp(Vector2.ZERO, 1.0 - exp(-delta * 3.0))

	var forward := -body_xf.basis.z
	var yaw := atan2(-forward.x, -forward.z) + _orbit.x
	var dist := float(cfg.get("distance_m", 12.0)) * Settings.get_f("gameplay.camera_distance")
	var height := float(cfg.get("height_m", 4.0))
	# Aiming up or down tilts the whole chassis (gameplay.aim_tilt), so the camera drops behind and
	# looks up the same line (aim_follow of the aim pitch), keeping the reticle near the middle.
	# Lane A3 part 4: the camera follows the look pitch (up to 75 deg, for aiming the wire anchor),
	# which the body tilt follows only as far as the legs allow.
	var aim_p := 0.0
	if "look_pitch_deg" in target:
		aim_p = deg_to_rad(float(target.get("look_pitch_deg"))) * float(cfg.get("aim_follow", 0.8))
	elif "aim_pitch_deg" in target:
		aim_p = deg_to_rad(float(target.get("aim_pitch_deg"))) * float(cfg.get("aim_follow", 0.8))
	var offset := Basis(Vector3.UP, yaw) * (Basis(Vector3.RIGHT, -_orbit.y + aim_p) * Vector3(0.0, height, dist))
	var velocity: Vector3 = target.get("linear_velocity") if "linear_velocity" in target else Vector3.ZERO
	var look := body_xf.origin + Vector3(0.0, float(cfg.get("look_height_m", 1.5)), 0.0)
	look += Vector3.UP * sin(aim_p) * dist
	look += Vector3(velocity.x, 0.0, velocity.z) * float(cfg.get("look_ahead_s", 0.25))
	var desired := body_xf.origin + offset

	var weight := Settings.get_f("gameplay.camera_weight")
	var rate := float(cfg.get("follow_rate", 5.5)) * lerpf(2.2, 0.55, weight)
	# The weighty lag is right at walking pace; at grapple-swing speeds (70 km/h) it let the mech fly
	# into the camera, so the follow tightens with speed.
	rate *= 1.0 + velocity.length() / maxf(float(cfg.get("fast_follow_m_s", 15.0)), 0.1)
	if not _started:
		_pos = desired
		_look = look
		_started = true
	_pos = _pos.lerp(desired, 1.0 - exp(-rate * delta))
	_look = _look.lerp(look, 1.0 - exp(-rate * 1.6 * delta))

	# Emerson's note 18 (after 012): the camera went into the ground. A sphere (not a thin ray) is swept from the
	# look point out to the camera, so the near plane never grazes the terrain; when the room behind is shorter
	# than min_clear_m (the camera would sit in the hull) it rises over the mech's back instead of being pushed
	# back out through the hill or wall it just avoided. Legion bodies are not counted: it passes through them.
	# Relay 38 (Emerson after 015, "the camera keeps slipping through the floor"): aiming down drops the look point
	# by sin(pitch) x distance, 1.8 m into flat ground at -30 deg with free look down, and a sweep that starts in the
	# solid stayed there. So the sweep starts from the look point as far as it can be reached in open air from the
	# mech, and the camera still looks at the real look point.
	var radius := float(cfg.get("collision_radius_m", 0.5))
	var clear := float(cfg.get("min_clear_m", 6.0))
	var start := _swept(_anchor(body_xf, float(cfg.get("look_height_m", 1.5)), radius), _look, radius)
	var final := _swept(start, _pos, radius)
	if final.distance_to(body_xf.origin) < clear:
		var back := Vector3(offset.x, 0.0, offset.z).normalized() * clear * 0.35
		var over := body_xf.origin + Vector3.UP * clear + back
		final = _swept(start, over, radius)
		_pos = final
	fov = Settings.get_f("gameplay.fov_third")
	global_position = final + jitter
	if global_position.distance_to(_look) > 0.01:
		look_at(_look, Vector3.UP)


## The farthest point from `from` towards `to` that a ball of `radius` reaches without touching the world.
func _swept(from: Vector3, to: Vector3, radius: float) -> Vector3:
	var ball := SphereShape3D.new()
	ball.radius = radius
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = ball
	q.transform = Transform3D(Basis.IDENTITY, from)
	q.motion = to - from
	q.collision_mask = 1
	q.exclude = _skip
	var space := get_world_3d().direct_space_state
	if not space.intersect_shape(q, 1).is_empty():
		return from  # the look point itself is in the solid: stay on it rather than sweep from inside
	var safe: PackedFloat32Array = space.cast_motion(q)
	return from + (to - from) * safe[0]


## A point at the mech in open air to start the camera sweeps from: above the hull's centre, or the first
## free spot straight up from it when a roll has put that in a bank or under the mech's own side.
func _anchor(body_xf: Transform3D, look_height: float, radius: float) -> Vector3:
	var q := PhysicsShapeQueryParameters3D.new()
	var ball := SphereShape3D.new()
	ball.radius = radius
	q.shape = ball
	q.collision_mask = 1
	q.exclude = _skip
	var space := get_world_3d().direct_space_state
	for up: float in [look_height, 0.0, look_height * 2.0, look_height * 4.0, look_height * 8.0]:
		var at := body_xf.origin + Vector3.UP * up
		q.transform = Transform3D(Basis.IDENTITY, at)
		if space.intersect_shape(q, 1).is_empty():
			return at
	return body_xf.origin + Vector3.UP * look_height


## The followed mech's own bodies (hull and leg hitboxes): the look point sits inside them.
func _own_rids() -> Array[RID]:
	var out: Array[RID] = []
	if target is CollisionObject3D:
		out.append((target as CollisionObject3D).get_rid())
	for n: Node in target.find_children("*", "CollisionObject3D", true, false):
		out.append((n as CollisionObject3D).get_rid())
	return out


## Where the first-person eye sits on `mech`, in its body frame: the camera socket Settings > Gameplay >
## Cockpit view from picks (mechs.json "cameras"; Emerson after 015: from the pilot seat under the gun the
## view was "really close"), the pilot seat if the mech has no such socket.
static func eye_point(mech: Node) -> Vector3:
	var cams: Dictionary = mech.get("def").get("cameras", {})
	var e: Array = cams.get(Settings.get_s("gameplay.cockpit_eye"), cams.get("cockpit", [0.0, 0.4, -1.5]))
	return Vector3(e[0], e[1], e[2])
