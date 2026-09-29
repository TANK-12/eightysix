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


func _ready() -> void:
	add_to_group("game_camera")
	top_level = true
	current = true
	view = Settings.get_s("gameplay.default_view")
	_noise.frequency = 1.7


func follow(node: Node3D) -> void:
	target = node
	_started = false
	if node.has_signal("landed"):
		node.connect("landed", func(impact: float) -> void: add_shake(clampf(impact / 12.0, 0.1, 1.0)))
	if node.has_signal("stepped"):
		node.connect("stepped", func(_leg: String) -> void: add_shake(0.06))


func add_shake(amount: float) -> void:
	if Settings.get_b("accessibility.reduce_motion"):
		return
	_shake = maxf(_shake, amount * Settings.get_f("gameplay.camera_shake"))


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("camera_view"):
		view = "cockpit" if view == "third" else "third"
		_started = false


func _process(delta: float) -> void:
	if target == null or not is_instance_valid(target):
		return
	var cfg: Dictionary = Registry.tune("camera.third_person", {})
	var body_xf := target.global_transform
	_shake = move_toward(_shake, 0.0, delta * 2.5)
	_shake_t += delta
	var jitter := Vector3(_noise.get_noise_2d(_shake_t * 60.0, 0.0), _noise.get_noise_2d(0.0, _shake_t * 60.0), 0.0) * _shake * 0.35

	if view == "cockpit":
		var eye: Array = target.get("def").get("cameras", {}).get("cockpit", [0.0, 0.4, -1.5])
		fov = Settings.get_f("gameplay.fov_cockpit")
		global_transform = body_xf * Transform3D(Basis.IDENTITY, Vector3(eye[0], eye[1], eye[2]))
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
	var offset := Basis(Vector3.UP, yaw) * (Basis(Vector3.RIGHT, -_orbit.y) * Vector3(0.0, height, dist))
	var velocity: Vector3 = target.get("linear_velocity") if "linear_velocity" in target else Vector3.ZERO
	var look := body_xf.origin + Vector3(0.0, float(cfg.get("look_height_m", 1.5)), 0.0)
	look += Vector3(velocity.x, 0.0, velocity.z) * float(cfg.get("look_ahead_s", 0.25))
	var desired := body_xf.origin + offset

	var weight := Settings.get_f("gameplay.camera_weight")
	var rate := float(cfg.get("follow_rate", 5.5)) * lerpf(2.2, 0.55, weight)
	if not _started:
		_pos = desired
		_look = look
		_started = true
	_pos = _pos.lerp(desired, 1.0 - exp(-rate * delta))
	_look = _look.lerp(look, 1.0 - exp(-rate * 1.6 * delta))

	var final := _pos
	var space := get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(_look, _pos, 1)
	var hit := space.intersect_ray(query)
	if not hit.is_empty():
		final = (hit["position"] as Vector3) + (hit["normal"] as Vector3) * float(cfg.get("collision_margin_m", 0.4))
	fov = Settings.get_f("gameplay.fov_third")
	global_position = final + jitter
	if global_position.distance_to(_look) > 0.01:
		look_at(_look, Vector3.UP)
