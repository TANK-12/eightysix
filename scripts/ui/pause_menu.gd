extends CanvasLayer
## Pause overlay: resume, settings (the same screen as the main menu's), restart, main menu, quit.

const SETTINGS_SCRIPT := preload("res://scripts/ui/settings_screen.gd")

var _root: Control
var _buttons: VBoxContainer
var _settings: Control = null


func _ready() -> void:
	layer = 50
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	UiTheme.adopt(_root)
	add_child(_root)
	var shade := ColorRect.new()
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.color = Color(UiTheme.color("bg"), 0.72)
	_root.add_child(shade)

	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.add_child(center)
	var card := PanelContainer.new()
	card.theme_type_variation = "CardPanel"
	card.custom_minimum_size = Vector2(520, 0)
	center.add_child(card)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	card.add_child(box)
	var title := Label.new()
	title.text = "Paused"
	title.theme_type_variation = "TitleLabel"
	box.add_child(title)
	var where := Label.new()
	where.theme_type_variation = "DimLabel"
	where.text = str(Registry.entry("maps", Game.current_map).get("label", ""))
	box.add_child(where)
	var gap := Control.new()
	gap.custom_minimum_size.y = 18
	box.add_child(gap)
	_buttons = VBoxContainer.new()
	_buttons.add_theme_constant_override("separation", 2)
	box.add_child(_buttons)
	_add("Resume", Game.close_pause)
	_add("Settings", _open_settings)
	_add("Restart map", Game.restart_map)
	_add("Main menu", Game.goto_main_menu)
	_add("Quit to desktop", Game.quit_game)
	(_buttons.get_child(0) as Button).grab_focus.call_deferred()


func open_settings(section_id: String = "", page_id: String = "") -> void:
	_open_settings()
	if section_id != "":
		_settings.call("show_page", section_id, page_id)


func _add(text: String, action: Callable) -> void:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = "MainMenuButton"
	b.add_theme_font_size_override("font_size", UiTheme.size("button") + 4)
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.pressed.connect(action)
	_buttons.add_child(b)


func _open_settings() -> void:
	if _settings != null:
		return
	_settings = SETTINGS_SCRIPT.new()
	_root.add_child(_settings)
	_settings.closed.connect(
		func() -> void:
			_settings = null
			(_buttons.get_child(1) as Button).grab_focus()
	)


func _unhandled_input(event: InputEvent) -> void:
	if _settings != null:
		return
	if event.is_action_pressed("pause") or event.is_action_pressed("ui_back"):
		get_viewport().set_input_as_handled()
		Game.close_pause()
