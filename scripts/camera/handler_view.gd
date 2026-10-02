class_name HandlerView
extends CanvasLayer
## The Handler command view (lane A5): the Para-RAID commander's screen. A high tactical camera over the
## squad with markers for every Juggernaut (callsign, armour, order) and the Legion the squad can see
## (only what a Processor has a line of sight to, as the Para-RAID shares it). The game keeps running.
## Order keys work as in the field; a left click on the ground sends the addressed members there (on a Legion
## marker: attack that one), the
## wheel or L1/R1 picks who is addressed, and the view key (Tab) goes back to the field camera.

const HEIGHT_MIN_M := 110.0
const BACK_RATIO := 0.55  # how far behind the squad the camera sits for its height, so it looks down at an angle
const SIGHT_REFRESH_S := 0.25
const PICK_PX := 22.0  # a click this close to a Legion marker picks that Legion
const LEGION_COLOUR := Color(0.95, 0.25, 0.2)
const LEADER_COLOUR := Color(0.95, 0.95, 0.9)

var squad: Squad
var is_open := false
var camera: Camera3D
var seen_legion: Array[Node3D] = []
var _overlay: Control
var _previous: Camera3D
var _sight_s := 0.0
var _font: Font
var _hidden: Array[CanvasLayer] = []  # the field HUDs hidden while the view is open


func _ready() -> void:
	add_to_group("handler_view")
	layer = 40  # over the field HUDs (10-12), under pause (50), mission end (55) and photo mode (60)
	visible = false
	camera = Camera3D.new()
	camera.name = "HandlerCamera"
	camera.fov = 50.0
	camera.far = 6000.0
	add_child(camera)
	_overlay = Control.new()
	_overlay.name = "Overlay"
	_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_overlay.draw.connect(_draw_overlay)
	add_child(_overlay)
	_font = ThemeDB.fallback_font


func toggle() -> void:
	if is_open:
		close()
	else:
		open()


func open() -> void:
	if is_open:
		return
	is_open = true
	visible = true
	_previous = get_viewport().get_camera_3d()
	_place_camera(1.0)
	camera.make_current()
	_refresh_sight()
	# The field HUDs (every lower CanvasLayer) hide, as in photo mode: this screen is the Handler's picture.
	_hidden.clear()
	for cl: Node in get_tree().root.find_children("*", "CanvasLayer", true, false):
		if cl != self and (cl as CanvasLayer).visible and (cl as CanvasLayer).layer < layer:
			(cl as CanvasLayer).visible = false
			_hidden.append(cl)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func close() -> void:
	if not is_open:
		return
	is_open = false
	visible = false
	camera.clear_current(false)
	for cl: CanvasLayer in _hidden:
		if is_instance_valid(cl):
			cl.visible = true
	_hidden.clear()
	if _previous != null and is_instance_valid(_previous):
		_previous.make_current()
	if squad.level != null and squad.level.has_method("capture_mouse"):
		squad.level.call("capture_mouse")


## The middle of the leader and the living squad, and how far they are spread (flat metres).
func centre() -> Array:
	var points: Array[Vector3] = []
	if squad.leader != null and is_instance_valid(squad.leader):
		points.append(squad.leader.global_position)
	for p: SquadPilot in squad.pilots:
		if p.alive():
			points.append(p.mech.global_position)
	if points.is_empty():
		return [Vector3.ZERO, 0.0]
	var mid := Vector3.ZERO
	for v in points:
		mid += v
	mid /= points.size()
	var spread := 0.0
	for v in points:
		spread = maxf(spread, SquadPilot._flat(v - mid).length())
	return [mid, spread]


func _place_camera(blend: float) -> void:
	var c := centre()
	var mid: Vector3 = c[0]
	var height := maxf(HEIGHT_MIN_M, float(c[1]) * 2.4)
	var heading := Basis(Vector3.UP, SquadPilot._yaw(squad.leader.global_transform.basis)) if squad.leader != null else Basis.IDENTITY
	var want := mid + Vector3.UP * height + heading * Vector3(0.0, 0.0, height * BACK_RATIO)
	camera.global_position = camera.global_position.lerp(want, blend)
	camera.look_at(mid, Vector3.UP)


func _process(delta: float) -> void:
	if not is_open:
		return
	_place_camera(1.0 - exp(-delta * 3.0))
	_sight_s -= delta
	if _sight_s <= 0.0:
		_sight_s = SIGHT_REFRESH_S
		_refresh_sight()
	_overlay.queue_redraw()


func _refresh_sight() -> void:
	seen_legion.clear()
	for n: Node in get_tree().get_nodes_in_group("legion"):
		var u := n as Node3D
		if SquadPilot._legion_alive(u) and squad.seen(u):
			seen_legion.append(u)


## The left click: on a Legion marker (within PICK_PX) an attack on that Legion, otherwise a move to the ground.
func click_at(screen: Vector2) -> String:
	var best: Node3D = null
	var best_px := PICK_PX
	for u: Node3D in seen_legion:
		if not SquadPilot._legion_alive(u):
			continue
		var px := _screen(u.global_position).distance_to(screen)
		if px < best_px:
			best = u
			best_px = px
	if best != null:
		squad.give_order("attack", null, best)
		return "attack"
	return "move" if order_move_at(screen) else ""


## Sends the addressed members to the ground under a screen point. Returns whether it hit ground.
func order_move_at(screen: Vector2) -> bool:
	var from := camera.project_ray_origin(screen)
	var to := from + camera.project_ray_normal(screen) * 8000.0
	var hit := camera.get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(from, to, 1))
	if hit.is_empty():
		return false
	squad.give_order("move", hit["position"] as Vector3)
	return true


func _unhandled_input(event: InputEvent) -> void:
	if not is_open:
		return
	var click := event as InputEventMouseButton
	if click != null and click.pressed and click.button_index == MOUSE_BUTTON_LEFT:
		get_viewport().set_input_as_handled()
		click_at(click.position)


# --- the overlay ---------------------------------------------------------------------------------


func _draw_overlay() -> void:
	var size := _overlay.size
	_overlay.draw_rect(Rect2(Vector2.ZERO, size), Color(0.02, 0.05, 0.08, 0.18))
	_text(Vector2(24, 58), "Para-RAID  ·  Spearhead squadron  ·  Handler view", 20, Color(0.75, 0.9, 1.0))
	var who := "whole squad" if squad.selected < 0 else squad.callsign(squad.selected)
	_text(Vector2(24, 84), "Orders to: %s    Last order: %s" % [who, Squad.ORDER_WORDS.get(squad.last_order, squad.last_order)], 16, Color(0.8, 0.85, 0.9))
	_text(Vector2(24, size.y - 24), "1 follow  ·  2 hold  ·  3 attack  ·  4 regroup  ·  click: move there, or attack a red marker  ·  wheel / L1 R1: pick who  ·  Tab: back to the field", 15, Color(0.75, 0.8, 0.85))
	for u: Node3D in seen_legion:
		if SquadPilot._legion_alive(u):
			_marker(u.global_position, LEGION_COLOUR, str(u.get("enemy_id")).capitalize() if u.get("enemy_id") != null else "Legion", "", true)
	if squad.leader != null and is_instance_valid(squad.leader):
		_marker(squad.leader.global_position, LEADER_COLOUR, "Undertaker", _armour(squad.leader), false)
	for i in squad.pilots.size():
		var p := squad.pilots[i]
		var e := Registry.entry("squad", p.id)
		var colour := Color.from_string(str(e.get("colour", "#ffffff")), Color.WHITE)
		if not p.alive():
			_marker(p.mech.global_position, Color(0.4, 0.4, 0.4), str(e.get("callsign", p.id)), "lost", false)
			continue
		var line := "%s  ·  %s" % [_armour(p.mech), p.order]
		_marker(p.mech.global_position, colour, str(e.get("callsign", p.id)), line, false, i == squad.selected)
		if p.order in ["move", "hold"]:
			var a := _screen(p.mech.global_position)
			var b := _screen(p.order_point)
			if a.x > -1e5 and b.x > -1e5:
				_overlay.draw_dashed_line(a, b, colour, 1.5, 8.0)
				_overlay.draw_arc(b, 8.0, 0.0, TAU, 20, colour, 1.5)


func _marker(world: Vector3, colour: Color, label: String, sub: String, enemy: bool, picked: bool = false) -> void:
	var at := _screen(world)
	if at.x < -1e5:
		return
	if enemy:
		var r := 8.0
		_overlay.draw_colored_polygon(PackedVector2Array([at + Vector2(0, -r), at + Vector2(r, 0), at + Vector2(0, r), at + Vector2(-r, 0)]), colour)
	else:
		_overlay.draw_circle(at, 7.0, colour)
		_overlay.draw_arc(at, 11.0, 0.0, TAU, 24, colour, 1.5)
	if picked:
		_overlay.draw_arc(at, 17.0, 0.0, TAU, 24, Color(1, 1, 1), 2.0)
	_text(at + Vector2(14, -4), label, 15, colour)
	if sub != "":
		_text(at + Vector2(14, 14), sub, 13, colour.lerp(Color.WHITE, 0.3))


func _screen(world: Vector3) -> Vector2:
	if camera.is_position_behind(world):
		return Vector2(-1e6, -1e6)
	return camera.unproject_position(world)


func _text(at: Vector2, text: String, size: int, colour: Color) -> void:
	_overlay.draw_string_outline(_font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, 4, Color(0, 0, 0, 0.75))
	_overlay.draw_string(_font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, colour)


static func _armour(mech: Node) -> String:
	var combat := mech.get_node_or_null("Combat")
	if combat == null or combat.get("damage") == null:
		return ""
	return "armour %d%%" % roundi(100.0 * float(combat.damage.total_fraction()))
