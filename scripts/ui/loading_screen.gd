extends Control
## Loading screen: loads Game.pending_map's scene on a background thread, shows progress, the map's
## description and a tip, then swaps to the map. Stays up at least MIN_SHOW_S so it reads.

const MIN_SHOW_S := 0.9

var _path := ""
var _elapsed := 0.0
var _bar: ProgressBar
var _status: Label
var _failed := false


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	add_child(UiTheme.make_backdrop())
	var entry := Registry.entry("maps", Game.pending_map)
	_path = str(entry.get("scene", ""))

	var box := VBoxContainer.new()
	box.position = Vector2(150, 640)
	box.custom_minimum_size = Vector2(1000, 0)
	box.add_theme_constant_override("separation", 12)
	add_child(box)
	var kicker := Label.new()
	kicker.text = "Deploying to"
	kicker.theme_type_variation = "DimLabel"
	box.add_child(kicker)
	var title := Label.new()
	title.text = str(entry.get("label", Game.pending_map))
	title.theme_type_variation = "TitleLabel"
	box.add_child(title)
	var desc := Label.new()
	desc.text = str(entry.get("description", ""))
	desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc.custom_minimum_size.x = 1000
	box.add_child(desc)
	_bar = ProgressBar.new()
	_bar.custom_minimum_size = Vector2(1000, 6)
	_bar.show_percentage = false
	box.add_child(_bar)
	_status = Label.new()
	_status.theme_type_variation = "MonoLabel"
	box.add_child(_status)
	var tip := Label.new()
	tip.theme_type_variation = "DimLabel"
	tip.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tip.custom_minimum_size.x = 1000
	tip.text = "Tip: " + _pick_tip(entry)
	box.add_child(tip)

	if _path == "" or ResourceLoader.load_threaded_request(_path, "", true) != OK:
		_fail("Could not start loading %s." % _path)


func _pick_tip(entry: Dictionary) -> String:
	var tips: Array = entry.get("tips", []).duplicate()
	for id in Registry.ids("tips"):
		tips.append(Registry.entry("tips", id).get("text", ""))
	return str(tips.pick_random()) if tips.size() > 0 else ""


func _process(delta: float) -> void:
	if _failed:
		return
	_elapsed += delta
	var progress: Array = []
	var state := ResourceLoader.load_threaded_get_status(_path, progress)
	match state:
		ResourceLoader.THREAD_LOAD_IN_PROGRESS:
			_bar.value = float(progress[0]) * 100.0 if progress.size() > 0 else 0.0
			_status.text = "Loading  %d%%" % int(_bar.value)
		ResourceLoader.THREAD_LOAD_LOADED:
			_bar.value = 100.0
			_status.text = "Building the ground and bringing the Juggernaut online"
			if _elapsed >= MIN_SHOW_S:
				var scene := ResourceLoader.load_threaded_get(_path) as PackedScene
				set_process(false)
				get_tree().change_scene_to_packed(scene)
		_:
			_fail("Loading %s failed." % _path)


func _fail(message: String) -> void:
	_failed = true
	_status.text = message + "  Press Esc or Circle for the main menu."
	push_error("Loading: " + message)


func _unhandled_input(event: InputEvent) -> void:
	if _failed and (event.is_action_pressed("ui_back") or event.is_action_pressed("ui_cancel")):
		Game.goto_main_menu()
