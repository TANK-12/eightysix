class_name PhotoMode
extends CanvasLayer
## Photo / inspect mode (Emerson, 2026-09-30, PLAN "Raising the bar": "I want to be able to look at it,
## in the game"; lane A4's list, built in A3 part 5 by track A). From the field (Photo mode key) or the
## pause menu: time freezes (the tree is paused), the HUD hides, and a free camera orbits the player's
## Juggernaut: mouse drag or right stick orbits, wheel or the triggers zoom, WASD or the left stick
## moves the point it circles (within photo.max_pan_m of the mech), Screenshot (F12 / cross) saves a
## PNG to the Pictures folder, Back (Esc / circle / the Photo mode key) returns to the game.

signal closed

const HINT := "orbit: mouse / right stick   zoom: wheel / triggers   move: WASD / left stick   photo: F12 / cross   back: Esc / circle"

var target: Node3D
var camera: Camera3D
var yaw := 0.0
var pitch := -0.2
var distance := 14.0
var focus_offset := Vector3.ZERO
var last_saved := ""
var _cfg: Dictionary = {}
var _hint: Label
var _flash_s := 0.0
var _hidden: Array[CanvasLayer] = []
var _previous_camera: Camera3D


func _ready() -> void:
	layer = 60
	process_mode = Node.PROCESS_MODE_ALWAYS
	_cfg = Registry.tune("photo", {})
	distance = float(_cfg.get("start_distance_m", 14.0))
	_hint = Label.new()
	_hint.text = HINT
	_hint.theme_type_variation = "DimLabel"
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.add_theme_constant_override("outline_size", 6)
	_hint.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.75))
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	UiTheme.adopt(root)
	add_child(root)
	root.add_child(_hint)
	_hint.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	_hint.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_hint.offset_top = -64.0
	_hint.offset_bottom = -40.0


## Starts orbiting `node`, hiding every other CanvasLayer (the HUDs) until close().
func open(node: Node3D) -> void:
	target = node
	_previous_camera = get_viewport().get_camera_3d()
	if _previous_camera != null:
		var from := _previous_camera.global_position - node.global_position
		yaw = atan2(from.x, from.z)
		distance = clampf(from.length(), float(_cfg.get("min_distance_m", 5.0)), float(_cfg.get("max_distance_m", 40.0)))
	for layer_node: Node in get_tree().root.find_children("*", "CanvasLayer", true, false):
		var cl := layer_node as CanvasLayer
		if cl != self and cl.visible and cl.layer < layer:
			cl.visible = false
			_hidden.append(cl)
	camera = Camera3D.new()
	camera.name = "PhotoCamera"
	camera.fov = Settings.get_f("gameplay.fov_third")
	add_child(camera)
	camera.make_current()
	_place_camera()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func close() -> void:
	for cl in _hidden:
		if is_instance_valid(cl):
			cl.visible = true
	_hidden.clear()
	if _previous_camera != null and is_instance_valid(_previous_camera):
		_previous_camera.make_current()
	closed.emit()
	queue_free()


## Turns the camera round the focus (radians): yaw about world up, pitch clamped.
func orbit(d_yaw: float, d_pitch: float) -> void:
	yaw += d_yaw
	pitch = clampf(pitch + d_pitch, deg_to_rad(float(_cfg.get("min_pitch_deg", -80.0))), deg_to_rad(float(_cfg.get("max_pitch_deg", 30.0))))
	_place_camera()


func zoom(factor: float) -> void:
	distance = clampf(distance * factor, float(_cfg.get("min_distance_m", 5.0)), float(_cfg.get("max_distance_m", 40.0)))
	_place_camera()


## Moves the focus point in the camera's ground plane, kept within photo.max_pan_m of the mech.
func pan(right: float, forward: float) -> void:
	var basis := Basis(Vector3.UP, yaw)
	focus_offset += basis * Vector3(right, 0.0, -forward)
	focus_offset = focus_offset.limit_length(float(_cfg.get("max_pan_m", 25.0)))
	_place_camera()


func focus_point() -> Vector3:
	return target.global_position + Vector3.UP * float(_cfg.get("focus_height_m", 1.0)) + focus_offset


func _place_camera() -> void:
	if camera == null or target == null or not is_instance_valid(target):
		return
	var f := focus_point()
	var offset := Basis(Vector3.UP, yaw) * (Basis(Vector3.RIGHT, pitch) * Vector3(0.0, 0.0, distance))
	var at := f + offset
	# Never inside the ground or a wall: stop short of whatever is between the focus and the camera.
	var q := PhysicsRayQueryParameters3D.create(f, at, 1)
	var hit := camera.get_world_3d().direct_space_state.intersect_ray(q)
	if not hit.is_empty():
		at = (hit["position"] as Vector3) + (hit["normal"] as Vector3) * 0.4
	camera.global_position = at
	if camera.global_position.distance_to(f) > 0.01:
		camera.look_at(f, Vector3.UP)


func _process(delta: float) -> void:
	if camera == null:
		return
	var rate := deg_to_rad(float(_cfg.get("stick_orbit_deg_s", 90.0))) * delta
	var aim := Controls.stick("aim")
	if aim.length() > 0.0:
		orbit(-aim.x * rate, -aim.y * rate)
	var move := Controls.stick("move")
	if move.length() > 0.0:
		pan(move.x * float(_cfg.get("pan_m_s", 8.0)) * delta, move.y * float(_cfg.get("pan_m_s", 8.0)) * delta)
	var z := Controls.trigger("fire_main") - Controls.trigger("brake")
	if absf(z) > 0.05:
		zoom(1.0 - z * delta)
	_flash_s = maxf(_flash_s - delta, 0.0)
	_hint.visible = _flash_s <= 0.0


func _unhandled_input(event: InputEvent) -> void:
	if camera == null:
		return
	if event is InputEventMouseMotion and (event.button_mask & (MOUSE_BUTTON_MASK_LEFT | MOUSE_BUTTON_MASK_RIGHT)) != 0:
		var m := event as InputEventMouseMotion
		orbit(-m.relative.x * 0.006, -m.relative.y * 0.006)
	elif event is InputEventMouseButton and event.pressed:
		var b := event as InputEventMouseButton
		if b.button_index == MOUSE_BUTTON_WHEEL_UP:
			zoom(0.9)
		elif b.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			zoom(1.1)
	elif event.is_action_pressed("screenshot") or event.is_action_pressed("jump"):
		save_photo.call_deferred()
	elif event.is_action_pressed("ui_cancel") or event.is_action_pressed("photo_mode") or event.is_action_pressed("pause"):
		get_viewport().set_input_as_handled()
		Game.close_photo()


## Saves the frame as a PNG in the Pictures folder ("Eighty Six" inside it), without the hint.
func save_photo() -> String:
	_hint.visible = false
	_flash_s = 0.6
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		return ""
	var path := photo_path()
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	if image.save_png(path) == OK:
		last_saved = path
	return last_saved


static func photo_dir() -> String:
	return OS.get_system_dir(OS.SYSTEM_DIR_PICTURES).path_join("Eighty Six")


static func photo_path() -> String:
	return photo_dir().path_join("eightysix-%s.png" % Time.get_datetime_string_from_system().replace(":", "-"))
