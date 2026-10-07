extends Node3D
## Final-kill cam (lane A7): when the last Legion of a mission goes down, time drops to a quarter speed
## and a camera swings round the wreck for a few seconds behind letterbox bars, with a caption ("Final
## kill · Löwe · 412 m"), before the end card. The other HUD layers hide meanwhile (the Handler radio
## stays). Any of Enter, Escape, Cross or Circle skips it. Settings > Gameplay > Camera > Final kill cam.

signal finished

const DURATION_S := 3.4  # real seconds, whatever the time scale
const SLOW := 0.25
const AUDIO_SLOW := 0.6
const RADIUS_M := 15.0
const HEIGHT_M := 4.5
const SWEEP_DEG := 75.0
const BAR_SHARE := 0.11

var focus := Vector3.ZERO
var caption := ""
var running := false
var camera: Camera3D
var _target: Node3D
var _t := 0.0
var _start_dir := Vector3.BACK
var _prev_cam: Camera3D
var _hidden: Array[CanvasLayer] = []
var _bars: CanvasLayer
var _top: ColorRect
var _bottom: ColorRect


## Starts on `target` (the wreck), from the side `viewer` (the player) looks at it.
func begin(target: Node3D, viewer: Vector3, text: String) -> void:
	_target = target
	focus = target.global_position + Vector3.UP * 1.5
	caption = text
	var flat := viewer - focus
	flat.y = 0.0
	_start_dir = flat.normalized() if flat.length() > 0.5 else Vector3.BACK
	_start_dir = _start_dir.rotated(Vector3.UP, deg_to_rad(-SWEEP_DEG * 0.5))
	_prev_cam = get_viewport().get_camera_3d()
	camera = Camera3D.new()
	camera.name = "KillCamera"
	camera.fov = 55.0
	camera.far = 4000.0
	add_child(camera)
	_place(0.0)
	camera.make_current()
	for layer: Node in get_tree().root.find_children("*", "CanvasLayer", true, false):
		var cl := layer as CanvasLayer
		if cl.visible and cl.layer < 50 and not cl.is_in_group("handler_radio"):
			cl.visible = false
			_hidden.append(cl)
	_build_bars()
	Engine.time_scale = SLOW
	AudioServer.playback_speed_scale = AUDIO_SLOW
	running = true


func _process(delta: float) -> void:
	if not running:
		return
	_t += delta / maxf(Engine.time_scale, 0.01)
	if _target != null and is_instance_valid(_target):
		focus = focus.lerp(_target.global_position + Vector3.UP * 1.5, 0.2)
	var k := clampf(_t / DURATION_S, 0.0, 1.0)
	_place(k)
	var bar := minf(_t / 0.35, 1.0) * minf((DURATION_S - _t) / 0.35 + 0.0001, 1.0)
	var h := get_viewport().get_visible_rect().size.y * BAR_SHARE * clampf(bar, 0.0, 1.0)
	_top.offset_bottom = h
	_bottom.offset_top = -h
	if _t >= DURATION_S:
		end()


func _input(event: InputEvent) -> void:
	if running and (event.is_action_pressed("ui_accept") or event.is_action_pressed("ui_cancel")):
		get_viewport().set_input_as_handled()
		end()


## Puts time, sound, the camera and the HUD back and says so. Safe to call twice.
func end() -> void:
	if not running:
		return
	running = false
	_restore()
	finished.emit()
	queue_free()


func _exit_tree() -> void:
	if running:  # the level went away mid-shot (restart, main menu): never leave the game in slow motion
		running = false
		_restore()


func _restore() -> void:
	Engine.time_scale = 1.0
	AudioServer.playback_speed_scale = 1.0
	for cl in _hidden:
		if is_instance_valid(cl):
			cl.visible = true
	_hidden.clear()
	if _prev_cam != null and is_instance_valid(_prev_cam):
		_prev_cam.make_current()


## The camera on its arc at `k` (0..1) of the sweep, eased, pulled in when ground or a wall is between.
func _place(k: float) -> void:
	var eased := k * k * (3.0 - 2.0 * k)
	var dir := _start_dir.rotated(Vector3.UP, deg_to_rad(SWEEP_DEG * eased))
	var radius := lerpf(RADIUS_M, RADIUS_M * 0.75, eased)
	var want := focus + dir * radius + Vector3.UP * HEIGHT_M
	if is_inside_tree():
		var q := PhysicsRayQueryParameters3D.create(focus, want)
		q.collision_mask = 1
		var hit := get_world_3d().direct_space_state.intersect_ray(q)
		if not hit.is_empty():
			want = focus.lerp(hit["position"], 0.85)
	camera.global_position = want
	if want.distance_to(focus) > 0.1:
		camera.look_at(focus, Vector3.UP)


func _build_bars() -> void:
	_bars = CanvasLayer.new()
	_bars.layer = 60
	add_child(_bars)
	_top = ColorRect.new()
	_top.color = Color.BLACK
	_top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	_top.offset_bottom = 0.0
	_bars.add_child(_top)
	_bottom = ColorRect.new()
	_bottom.color = Color.BLACK
	_bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	_bottom.offset_top = 0.0
	_bars.add_child(_bottom)
	var label := Label.new()
	label.text = caption
	UiTheme.adopt(label)
	label.theme_type_variation = "HeadingLabel"
	label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_bottom.add_child(label)
