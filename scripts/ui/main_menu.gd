extends Control
## Main menu: the title block and menu column on the Handler's map table, a map chooser, and the
## settings screen on top when opened. Maps come from data/maps.json; planned ones show greyed.

const SETTINGS_SCRIPT := preload("res://scripts/ui/settings_screen.gd")
## The map card's top edge, and the room it leaves above the bottom of the screen (the status line).
const MAPS_TOP := 150.0
const MAPS_BOTTOM_GAP := 130.0

## "0.1.1-alpha" (project.godot's config/version) as the subtitle shows it: "Alpha 0.1.1".
static func version_label(version: String) -> String:
	var parts := version.split("-", false, 1)
	if parts.size() < 2:
		return version
	return parts[1].capitalize() + " " + parts[0]


var _backdrop: ColorRect
var _menu: VBoxContainer
var _maps_panel: PanelContainer
var _status: Label
var _prompt: Label
var _settings: Control = null
var _stage: HangarStage = null
var _scrim: TextureRect


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	_build()
	Settings.changed.connect(_on_setting_changed)
	UiTheme.theme_changed.connect(_on_theme_changed)
	Controls.device_changed.connect(func(_kind: String) -> void: _refresh_status())
	Input.joy_connection_changed.connect(func(_d: int, _c: bool) -> void: _refresh_status())
	_refresh_status()
	_focus_menu.call_deferred()


func open_settings(section_id: String = "", page_id: String = "") -> void:
	if _settings == null:
		_settings = SETTINGS_SCRIPT.new()
		add_child(_settings)
		_settings.closed.connect(_on_settings_closed)
	if section_id != "":
		_settings.call("show_page", section_id, page_id)


func open_maps() -> void:
	_maps_panel.visible = not _maps_panel.visible
	if _maps_panel.visible:
		_fit_maps_panel()
		# the first map that can start takes the focus, so a pad lands in the list
		for child in _maps_panel.find_children("*", "Button", true, false):
			if not (child as Button).disabled:
				(child as Button).grab_focus()
				return


## The map card is as tall as its list, up to the room between the top corner marks and the status
## line (Emerson after 014: it ran off the bottom of the screen under the status text); a longer
## list scrolls.
func _fit_maps_panel() -> void:
	var room := get_viewport_rect().size.y - MAPS_TOP - MAPS_BOTTOM_GAP
	var scroll := _maps_panel.get_child(0) as ScrollContainer
	var list := scroll.get_child(0) as Control
	var frame := _maps_panel.get_combined_minimum_size().y - scroll.get_combined_minimum_size().y
	scroll.custom_minimum_size.y = minf(list.get_combined_minimum_size().y, room - frame)
	_maps_panel.offset_bottom = _maps_panel.offset_top
	_maps_panel.reset_size()


func _on_settings_closed() -> void:
	_settings = null
	_refresh_status()
	_focus_menu()


func _build() -> void:
	_backdrop = UiTheme.make_backdrop()
	add_child(_backdrop)
	_scrim = TextureRect.new()
	_scrim.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	_scrim.mouse_filter = MOUSE_FILTER_IGNORE
	_scrim.stretch_mode = TextureRect.STRETCH_SCALE
	_scrim.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	add_child(_scrim)
	_update_showcase()

	var frame := Control.new()
	frame.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	frame.mouse_filter = MOUSE_FILTER_IGNORE
	frame.draw.connect(_draw_frame.bind(frame))
	add_child(frame)

	var left := VBoxContainer.new()
	left.position = Vector2(150, 150)
	left.custom_minimum_size = Vector2(760, 0)
	left.add_theme_constant_override("separation", 0)
	add_child(left)

	var mark := Label.new()
	mark.text = "86"
	mark.theme_type_variation = "HugeLabel"
	mark.add_theme_constant_override("line_spacing", -40)
	left.add_child(mark)
	var title := Label.new()
	title.text = "Eighty Six"
	title.theme_type_variation = "TitleLabel"
	title.add_theme_font_override("font", UiTheme.spaced_font("heading", 6))
	left.add_child(title)
	var sub := Label.new()
	sub.text = version_label(str(ProjectSettings.get_setting("application/config/version"))) + "  ·  Juggernaut field test"
	sub.theme_type_variation = "DimLabel"
	left.add_child(sub)

	var rule := ColorRect.new()
	rule.custom_minimum_size = Vector2(440, 1)
	rule.color = UiTheme.color("line")
	var rule_box := MarginContainer.new()
	rule_box.add_theme_constant_override("margin_top", 34)
	rule_box.add_theme_constant_override("margin_bottom", 26)
	rule_box.add_child(rule)
	left.add_child(rule_box)

	_menu = VBoxContainer.new()
	_menu.add_theme_constant_override("separation", 2)
	_menu.custom_minimum_size.x = 440
	left.add_child(_menu)
	_add_entry("Deploy", _deploy, Game.default_map() == "")
	_add_entry("Select map", open_maps)
	_add_entry("Hangar", Game.goto_hangar, not MechBuilder.can_build("juggernaut_m2"), "Look at the Juggernaut: orbit it, point at its parts, change the light.")
	_add_entry("Settings", func() -> void: open_settings())
	_add_entry("Quit to desktop", Game.quit_game)

	# right-hand column, sized to its list by _fit_maps_panel()
	_maps_panel = PanelContainer.new()
	_maps_panel.theme_type_variation = "CardPanel"
	_maps_panel.visible = false
	_maps_panel.set_anchors_preset(PRESET_TOP_RIGHT)
	_maps_panel.offset_left = -900
	_maps_panel.offset_right = -150
	_maps_panel.offset_top = MAPS_TOP
	_maps_panel.grow_horizontal = GROW_DIRECTION_BEGIN
	add_child(_maps_panel)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	_maps_panel.add_child(scroll)
	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", 10)
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	var head := Label.new()
	head.text = "Maps"
	head.theme_type_variation = "HeadingLabel"
	list.add_child(head)
	for id in Registry.ids("maps"):
		var entry := Registry.entry("maps", id)
		var b := Button.new()
		b.theme_type_variation = "PageButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		var note := ""
		if not Game.can_start(id):
			note = "   ·   arrives in lane %s" % str(entry.get("owner_lane", "later"))
		b.text = str(entry.get("label", id)) + note
		b.tooltip_text = str(entry.get("description", ""))
		b.disabled = not Game.can_start(id)
		var map_id := id
		b.pressed.connect(func() -> void: Game.start_map(map_id))
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		list.add_child(row)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(b)
		# Free roam (Emerson's note 19 after 012): the same map with no Legion, to explore with the squad.
		if Game.can_start(id) and str(entry.get("mission", "")) != "":
			var free := Button.new()
			free.theme_type_variation = "PageButton"
			free.text = "Free roam"
			free.tooltip_text = "The same map with no Legion: explore it with your squad."
			free.pressed.connect(func() -> void: Game.start_map(map_id, true))
			row.add_child(free)
		var desc := Label.new()
		desc.text = str(entry.get("blurb", entry.get("description", "")))
		desc.tooltip_text = str(entry.get("description", ""))
		desc.mouse_filter = Control.MOUSE_FILTER_PASS
		desc.theme_type_variation = "FaintLabel"
		desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		desc.custom_minimum_size.x = 640
		list.add_child(desc)

	_prompt = Label.new()
	_prompt.theme_type_variation = "FaintLabel"
	_prompt.position = Vector2(150, 1000)
	add_child(_prompt)
	_status = Label.new()
	_status.theme_type_variation = "MonoLabel"
	_status.modulate = Color(1, 1, 1, 0.6)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_status.set_anchors_and_offsets_preset(PRESET_BOTTOM_RIGHT)
	_status.offset_left = -1150
	_status.offset_top = -80
	_status.offset_right = -150  # clear of the corner bracket, mirroring the prompt's 150 on the left
	_status.offset_bottom = -44
	_status.grow_horizontal = GROW_DIRECTION_BEGIN
	_status.clip_text = true
	add_child(_status)

	var link := Label.new()
	link.text = "Para-RAID  ·  standing by"
	link.theme_type_variation = "DimLabel"
	link.set_anchors_and_offsets_preset(PRESET_TOP_RIGHT)
	link.offset_left = -420
	link.offset_right = -80
	link.offset_top = 60
	link.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	add_child(link)


func _add_entry(text: String, action: Callable, disabled: bool = false, why: String = "") -> void:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = "MainMenuButton"
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.disabled = disabled
	b.tooltip_text = why
	b.focus_mode = FOCUS_ALL
	b.pressed.connect(func() -> void:
		Rumble.play("ui_confirm")
		action.call()
	)
	_menu.add_child(b)


func _deploy() -> void:
	Game.start_map(Game.default_map())


func _focus_menu() -> void:
	for child in _menu.get_children():
		if child is Button and not (child as Button).disabled:
			(child as Button).grab_focus()
			return


func _refresh_status() -> void:
	var pad := Controls.pad_name()
	var preset := Settings.label_for("graphics.preset", Settings.get_value("graphics.preset"))
	var parts := PackedStringArray(["Graphics: " + preset])
	parts.append(("Controller: " + pad) if pad != "" else "No controller connected")
	var v := Engine.get_version_info()
	parts.append("Godot %d.%d.%d" % [v["major"], v["minor"], v["patch"]])
	_status.text = "   ·   ".join(parts)
	var on_pad := Controls.last_device == "pad"
	_prompt.text = ("Cross  choose   ·   Circle  back" if on_pad else "Enter  choose   ·   Esc  back")


func _unhandled_input(event: InputEvent) -> void:
	if _settings != null:
		return
	if _maps_panel.visible and (event.is_action_pressed("ui_back") or event.is_action_pressed("ui_cancel")):
		_maps_panel.visible = false
		_focus_menu()
		get_viewport().set_input_as_handled()


func _on_theme_changed() -> void:
	UiTheme.style_backdrop(_backdrop)
	_scrim.texture = _scrim_texture()
	queue_redraw()


func _on_setting_changed(key: String, value: Variant) -> void:
	if key == "interface.menu_showcase":
		_update_showcase()
	elif key == "hangar.light" and _stage != null:
		_stage.set_light(str(value))


## The Juggernaut standing in the hangar behind the buttons (HangarStage in showcase mode: a slow sway
## of the camera), when Settings > Gameplay > Menus and theme > "Juggernaut behind the menu" is on and
## the model can be built; otherwise the plain backdrop. The stage is a 3D node under this Control: the
## 3D picture draws first, the menu on top of it.
func _update_showcase() -> void:
	var want := Settings.get_b("interface.menu_showcase")
	if want and _stage == null:
		var menu: Dictionary = Registry.file("hangar").get("menu", {})
		var stage := HangarStage.new()
		stage.showcase = true
		stage.shift_x = float(menu.get("shift_x", 0.2))
		add_child(stage)
		move_child(stage, 0)
		if stage.set_mech(str(menu.get("mech", "juggernaut_m2"))):
			_stage = stage
		else:
			stage.queue_free()
	elif not want and _stage != null:
		_stage.queue_free()
		_stage = null
	_backdrop.visible = _stage == null
	_scrim.visible = _stage != null
	_scrim.texture = _scrim_texture()


## A dark wash from the left edge, so the title and buttons read over the picture.
func _scrim_texture() -> GradientTexture2D:
	var bg := UiTheme.color("bg")
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.3, 0.55])
	g.colors = PackedColorArray([Color(bg, 0.92), Color(bg, 0.6), Color(bg, 0.0)])
	var tex := GradientTexture2D.new()
	tex.gradient = g
	tex.fill_from = Vector2(0.0, 0.5)
	tex.fill_to = Vector2(1.0, 0.5)
	tex.width = 256
	tex.height = 8
	return tex


func _draw_frame(frame: Control) -> void:
	var c := UiTheme.color("line")
	var s := frame.size
	var m := 48.0
	var arm := 60.0
	for corner: Vector2 in [Vector2(m, m), Vector2(s.x - m, m), Vector2(m, s.y - m), Vector2(s.x - m, s.y - m)]:
		var dx := arm if corner.x < s.x / 2.0 else -arm
		var dy := arm if corner.y < s.y / 2.0 else -arm
		frame.draw_line(corner, corner + Vector2(dx, 0), c, 2.0)
		frame.draw_line(corner, corner + Vector2(0, dy), c, 2.0)
	var accent := UiTheme.color("warn")
	frame.draw_rect(Rect2(Vector2(150, s.y - 118), Vector2(84, 3)), accent)
