extends Node
## Scene flow: main menu, the loading screen, maps from data/maps.json, pause and quit.
## A level calls Game.register_level(self) once it is built; the bot and the HUD wait on level_ready.

signal level_ready(level: Node)

const MAIN_MENU := "res://scenes/ui/main_menu.tscn"
const LOADING := "res://scenes/ui/loading_screen.tscn"
const PAUSE_MENU := "res://scenes/ui/pause_menu.tscn"
const HANGAR := "res://scenes/ui/hangar.tscn"

var pending_map := ""
var current_map := ""
var level: Node = null
var _pause_menu: Node = null
var _photo: PhotoMode


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


func can_start(map_id: String) -> bool:
	if not Registry.has_entry("maps", map_id):
		return false
	var entry := Registry.entry("maps", map_id)
	return str(entry.get("status", "")) != "planned" and ResourceLoader.exists(str(entry.get("scene", "")))


## The first map that can be played, in registry order (the small map once lane B3 lands).
func default_map() -> String:
	for id in Registry.ids("maps"):
		if can_start(id):
			return id
	return ""


func start_map(map_id: String) -> void:
	if not can_start(map_id):
		push_warning("Game: map '%s' cannot be started yet" % map_id)
		return
	_leave_level()
	pending_map = map_id
	get_tree().change_scene_to_file(LOADING)


func restart_map() -> void:
	if current_map != "":
		start_map(current_map)


func goto_main_menu() -> void:
	_leave_level()
	current_map = ""
	get_tree().change_scene_to_file(MAIN_MENU)


## The Hangar screen (scripts/ui/hangar.gd), from the main menu.
func goto_hangar() -> void:
	_leave_level()
	current_map = ""
	get_tree().change_scene_to_file(HANGAR)


func quit_game() -> void:
	Settings.save_now()
	get_tree().quit()


func register_level(node: Node) -> void:
	level = node
	current_map = pending_map
	level_ready.emit(node)


func is_paused() -> bool:
	return _pause_menu != null and is_instance_valid(_pause_menu)


func open_pause() -> void:
	if level == null or is_paused():
		return
	_pause_menu = (load(PAUSE_MENU) as PackedScene).instantiate()
	get_tree().current_scene.add_child(_pause_menu)
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func close_pause() -> void:
	if is_paused():
		_pause_menu.queue_free()
	_pause_menu = null
	get_tree().paused = false
	if level != null and level.has_method("capture_mouse"):
		level.call("capture_mouse")


## Photo / inspect mode (scripts/camera/photo_mode.gd): time frozen, free camera round the player's mech.
func is_photo() -> bool:
	return _photo != null and is_instance_valid(_photo)


func open_photo() -> void:
	if level == null or is_photo() or not ("mech" in level) or level.get("mech") == null:
		return
	if is_paused():
		_pause_menu.queue_free()
		_pause_menu = null
	_photo = PhotoMode.new()
	get_tree().current_scene.add_child(_photo)
	get_tree().paused = true
	_photo.open(level.get("mech") as Node3D)


func close_photo() -> void:
	if is_photo():
		_photo.close()
	_photo = null
	get_tree().paused = false
	if level != null and level.has_method("capture_mouse"):
		level.call("capture_mouse")


func _leave_level() -> void:
	get_tree().paused = false
	_pause_menu = null
	_photo = null
	level = null
	Rumble.stop_all()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _unhandled_input(event: InputEvent) -> void:
	if level != null and not is_paused() and not is_photo() and event.is_action_pressed("pause"):
		get_viewport().set_input_as_handled()
		open_pause()
	elif level != null and not is_paused() and not is_photo() and event.is_action_pressed("photo_mode"):
		get_viewport().set_input_as_handled()
		open_photo()
