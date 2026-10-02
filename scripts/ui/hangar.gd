extends Control
## The Hangar screen (lane A4 part 7; PLAN "Show off the Juggernaut"): the Juggernaut standing in a lit
## hangar that you orbit, zoom and pan with the mouse or the pad; the variants, their loadouts, the
## paint, light presets; point at a part (mouse, or the centre of the screen on a pad) for its name and
## realistic mass, click it to pin it, or pick it from the parts list. The 3D part is HangarStage.
## Esc / circle goes back to the main menu; F12 saves a clean picture; O hides the panels.

const STAGE := preload("res://scripts/ui/hangar_stage.gd")
const DRAG_PX := 5.0

var stage: HangarStage
var pinned: Dictionary = {}
var hovered: Dictionary = {}

var _ui: Control
var _left: PanelContainer
var _right: PanelContainer
var _title: Label
var _variant_box: VBoxContainer
var _loadout_box: VBoxContainer
var _light_button: Button
var _finish_button: Button
var _emblem_button: Button
var _total_label: Label
var _size_label: Label
var _scroll: ScrollContainer
var _groups_box: VBoxContainer
var _group_rows: Dictionary = {}  # group id -> {"header": Button, "rows": VBoxContainer, "label": String}
var _part_buttons: Dictionary = {}  # part id -> Button
var _card: PanelContainer
var _card_title: Label
var _card_body: Label
var _tip: PanelContainer
var _tip_label: Label
var _hint: Label
var _reticle: Control
var _variant_buttons: Dictionary = {}
var _drag_from := Vector2.ZERO
var _dragging := false
var _down := false
var _hidden_ui := false
var last_saved := ""
var _parts_note := ""
var _sized := false


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	stage = STAGE.new()
	add_child(stage)
	stage.shift_x = 0.0
	_build_ui()
	var first := _variant_ids()
	var wanted := str(Registry.file("hangar").get("menu", {}).get("mech", "juggernaut_m2"))
	show_variant(wanted if wanted in first else (first[0] if not first.is_empty() else ""))
	stage.light_changed.connect(_on_light_changed)
	_on_light_changed(stage.light_id)
	UiTheme.theme_changed.connect(queue_redraw)
	Controls.device_changed.connect(func(_kind: String) -> void: _refresh_hint())
	_refresh_hint()
	if not _variant_buttons.is_empty():
		(_variant_buttons.values()[0] as Button).grab_focus.call_deferred()


# --- the data the screen shows -----------------------------------------------------------------


## Mechs that can be shown: built from the data, not a test stand-in.
static func _variant_ids() -> PackedStringArray:
	var out := PackedStringArray()
	for id in Registry.ids("mechs"):
		var def := Registry.entry("mechs", id)
		if str(def.get("status", "")) in ["planned", "test_only"] or not MechBuilder.can_build(id):
			continue
		out.append(id)
	return out


## A mass the way a spec sheet writes it: "468.8 kg", "5,564 kg".
static func kg(value: float) -> String:
	if value >= 1000.0:
		var whole := str(roundi(value))
		return whole.insert(whole.length() - 3, ",") + " kg"
	if value >= 100.0:
		return "%d kg" % roundi(value)
	return "%.1f kg" % value


func show_variant(id: String) -> void:
	if id == "" or not stage.set_mech(id):
		return
	pinned = {}
	hovered = {}
	var def := Registry.entry("mechs", id)
	_title.text = str(def.get("label", id))
	for key: String in _variant_buttons:
		(_variant_buttons[key] as Button).set_pressed_no_signal(key == id)
	_sized = false
	_fill_loadout(def)
	_fill_parts()
	_size_label.text = _parts_note
	_show_card({})


## Puts the camera at an exact view (degrees, metres): for the bot and for tests.
func view(yaw_deg: float, pitch_deg: float, distance_m: float) -> void:
	stage.yaw = deg_to_rad(yaw_deg)
	stage.pitch = deg_to_rad(pitch_deg)
	stage.distance = distance_m
	stage.zoom(1.0)
	stage.orbit(0.0, 0.0)


## Lights the stage with a preset without remembering it as the setting (the bot's way in).
func preview_light(id: String) -> void:
	stage.set_light(id)


func show_light(id: String) -> void:
	stage.set_light(id)
	Settings.set_value("hangar.light", stage.light_id)
	_refresh_selector(_light_button)


func cycle_light(step: int) -> void:
	var ids := stage.light_ids()
	if ids.is_empty():
		return
	var at := ids.find(stage.light_id)
	show_light(ids[posmod(at + step, ids.size())])


## Pins a part (by id): its card opens, its mesh lights up and the parts list scrolls to it.
func pin_part(part_id: String) -> void:
	if part_id == "":
		pinned = {}
		stage.clear_highlight()
		_show_card({})
		return
	pinned = stage.part_info(part_id)
	stage.highlight(part_id)
	_show_card(pinned)
	var group := str(pinned["group"])
	if _group_rows.has(group):
		_set_group_open(group, true)
	if _part_buttons.has(part_id):
		_scroll.ensure_control_visible.call_deferred(_part_buttons[part_id])


# --- building the panels -----------------------------------------------------------------------


func _build_ui() -> void:
	_ui = Control.new()
	_ui.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	_ui.mouse_filter = MOUSE_FILTER_IGNORE
	add_child(_ui)

	_left = PanelContainer.new()
	_left.theme_type_variation = "CardPanel"
	_left.set_anchors_and_offsets_preset(PRESET_LEFT_WIDE)
	_left.offset_left = 48
	_left.offset_top = 48
	_left.offset_bottom = -96
	_left.offset_right = 48 + 440
	_ui.add_child(_left)
	var left_scroll := ScrollContainer.new()
	left_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_left.add_child(left_scroll)
	var col := VBoxContainer.new()
	col.size_flags_horizontal = SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 6)
	left_scroll.add_child(col)
	var back := Button.new()
	back.text = "‹  Main menu"
	back.theme_type_variation = "PageButton"
	back.alignment = HORIZONTAL_ALIGNMENT_LEFT
	back.pressed.connect(go_back)
	col.add_child(back)
	var head := Label.new()
	head.text = "Hangar"
	head.theme_type_variation = "TitleLabel"
	col.add_child(head)
	_title = Label.new()
	_title.theme_type_variation = "DimLabel"
	col.add_child(_title)

	col.add_child(_heading("Variant"))
	_variant_box = VBoxContainer.new()
	_variant_box.add_theme_constant_override("separation", 2)
	col.add_child(_variant_box)
	for id in _variant_ids():
		var b := Button.new()
		b.text = str(Registry.entry("mechs", id).get("label", id))
		b.theme_type_variation = "PageButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.toggle_mode = true
		b.tooltip_text = str(Registry.entry("mechs", id).get("description", ""))
		b.pressed.connect(show_variant.bind(id))
		_variant_box.add_child(b)
		_variant_buttons[id] = b

	col.add_child(_heading("Loadout"))
	_loadout_box = VBoxContainer.new()
	_loadout_box.add_theme_constant_override("separation", 2)
	col.add_child(_loadout_box)

	col.add_child(_heading("Look"))
	_light_button = _selector("hangar.light", "Lighting")
	_light_button.pressed.connect(func() -> void: stage.set_light(Settings.get_s("hangar.light")))
	col.add_child(_light_button)
	_finish_button = _selector("mech.finish", "Finish")
	col.add_child(_finish_button)
	_emblem_button = _selector("mech.emblem", "Emblem")
	col.add_child(_emblem_button)

	_right = PanelContainer.new()
	_right.theme_type_variation = "CardPanel"
	_right.set_anchors_and_offsets_preset(PRESET_RIGHT_WIDE)
	_right.offset_right = -48
	_right.offset_left = -48 - 470
	_right.offset_top = 48
	_right.offset_bottom = -96
	_ui.add_child(_right)
	var rcol := VBoxContainer.new()
	rcol.add_theme_constant_override("separation", 6)
	_right.add_child(rcol)
	rcol.add_child(_heading("Mass"))
	_total_label = Label.new()
	_total_label.theme_type_variation = "TitleLabel"
	rcol.add_child(_total_label)
	_size_label = Label.new()
	_size_label.theme_type_variation = "DimLabel"
	rcol.add_child(_size_label)
	_card = PanelContainer.new()
	_card.theme_type_variation = "HelpPanel"
	rcol.add_child(_card)
	var card_box := VBoxContainer.new()
	card_box.add_theme_constant_override("separation", 4)
	_card.add_child(card_box)
	_card_title = Label.new()
	_card_title.theme_type_variation = "HeadingLabel"
	_card_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	card_box.add_child(_card_title)
	_card_body = Label.new()
	_card_body.theme_type_variation = "DimLabel"
	_card_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_card_body.custom_minimum_size.x = 400
	card_box.add_child(_card_body)
	rcol.add_child(_heading("Parts"))
	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = SIZE_EXPAND_FILL
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	rcol.add_child(_scroll)
	_groups_box = VBoxContainer.new()
	_groups_box.size_flags_horizontal = SIZE_EXPAND_FILL
	_groups_box.add_theme_constant_override("separation", 2)
	_scroll.add_child(_groups_box)

	# the label that follows the pointer over a part
	_tip = PanelContainer.new()
	_tip.theme_type_variation = "HelpPanel"
	_tip.mouse_filter = MOUSE_FILTER_IGNORE
	_tip.visible = false
	_tip.z_index = 10
	_ui.add_child(_tip)
	_tip_label = Label.new()
	_tip_label.theme_type_variation = "BodyLabel"
	_tip.add_child(_tip_label)

	_hint = Label.new()
	_hint.theme_type_variation = "FaintLabel"
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.set_anchors_and_offsets_preset(PRESET_BOTTOM_WIDE)
	_hint.offset_top = -72
	_hint.offset_bottom = -40
	_ui.add_child(_hint)

	# a pad has no pointer: a small cross at the centre of the picture picks the part there
	_reticle = Control.new()
	_reticle.set_anchors_and_offsets_preset(PRESET_CENTER)
	_reticle.mouse_filter = MOUSE_FILTER_IGNORE
	_reticle.draw.connect(_draw_reticle)
	_reticle.visible = false
	_ui.add_child(_reticle)


func _heading(text: String) -> Control:
	var box := MarginContainer.new()
	box.add_theme_constant_override("margin_top", 14)
	var l := Label.new()
	l.text = text
	l.theme_type_variation = "HeadingLabel"
	box.add_child(l)
	return box


## A "Name  ‹ value ›" button for a choice setting: pressing it steps to the next option.
func _selector(key: String, label: String) -> Button:
	var b := Button.new()
	b.theme_type_variation = "SelectorButton"
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.set_meta("key", key)
	b.set_meta("label", label)
	b.pressed.connect(_step_selector.bind(b))
	_refresh_selector(b)
	return b


func _refresh_selector(b: Button) -> void:
	var key := str(b.get_meta("key"))
	b.text = "%s:  %s  ›" % [b.get_meta("label"), Settings.label_for(key, Settings.get_value(key))]


func _step_selector(b: Button) -> void:
	var key := str(b.get_meta("key"))
	var options := Settings.options_for(key)
	if options.is_empty():
		return
	var at := 0
	for i in options.size():
		if options[i][0] == Settings.get_value(key):
			at = i
	Settings.set_value(key, (options[(at + 1) % options.size()] as Array)[0])
	_refresh_selector(b)


func _fill_loadout(def: Dictionary) -> void:
	for child in _loadout_box.get_children():
		_loadout_box.remove_child(child)
		child.queue_free()
	var slots: Dictionary = Registry.file("hangar").get("slots", {})
	var loadout: Dictionary = def.get("loadout", {})
	for slot: String in loadout:
		var weapon := Registry.entry("weapons", str(loadout[slot]))
		var row := HBoxContainer.new()
		var name_label := Label.new()
		name_label.text = str(slots.get(slot, slot.replace("_", " ").capitalize()))
		name_label.theme_type_variation = "DimLabel"
		name_label.custom_minimum_size.x = 150
		row.add_child(name_label)
		var gun := Label.new()
		gun.text = str(weapon.get("label", loadout[slot]))
		gun.theme_type_variation = "BodyLabel"
		gun.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		gun.size_flags_horizontal = SIZE_EXPAND_FILL
		row.add_child(gun)
		_loadout_box.add_child(row)


func _fill_parts() -> void:
	for child in _groups_box.get_children():
		_groups_box.remove_child(child)
		child.queue_free()
	_group_rows.clear()
	_part_buttons.clear()
	var total := stage.total_mass_kg()
	_total_label.text = kg(total)
	var groups: Dictionary = Registry.file("hangar").get("groups", {})
	var order: Array = groups.keys()
	order.sort_custom(func(a: Variant, b: Variant) -> bool: return float(groups[a].get("order", 99)) < float(groups[b].get("order", 99)))
	order.append("other")
	var rows := stage.part_rows()
	var count := 0
	for group_id: String in order:
		var members := rows.filter(func(r: Dictionary) -> bool: return str(r["group"]) == group_id)
		if members.is_empty():
			continue
		members.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return float(a["mass_kg"]) > float(b["mass_kg"]))
		var sum := 0.0
		for m: Dictionary in members:
			sum += float(m["mass_kg"])
		var label := str(groups.get(group_id, {}).get("label", "Other"))
		var header := Button.new()
		header.theme_type_variation = "PageButton"
		header.alignment = HORIZONTAL_ALIGNMENT_LEFT
		header.pressed.connect(func() -> void: _set_group_open(group_id, not (_group_rows[group_id]["rows"] as Control).visible))
		_groups_box.add_child(header)
		var list := VBoxContainer.new()
		list.add_theme_constant_override("separation", 0)
		list.visible = false
		_groups_box.add_child(list)
		_group_rows[group_id] = {"header": header, "rows": list, "label": label, "mass": sum, "count": members.size()}
		for m: Dictionary in members:
			var b := Button.new()
			b.theme_type_variation = "PageButton"
			b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.text = "%s    %s" % [m["label"], kg(float(m["mass_kg"]))]
			b.add_theme_font_size_override("font_size", 18)
			var part_id := str(m["id"])
			b.pressed.connect(pin_part.bind(part_id))
			list.add_child(b)
			_part_buttons[part_id] = b
			count += 1
		_set_group_open(group_id, false)
	_parts_note = "%d weighed parts, summed into the total" % count


func _set_group_open(group_id: String, open: bool) -> void:
	var g: Dictionary = _group_rows[group_id]
	(g["rows"] as Control).visible = open
	(g["header"] as Button).text = "%s  %s  ·  %s  ·  %d" % ["▾" if open else "▸", g["label"], kg(float(g["mass"])), int(g["count"])]


func _show_card(info: Dictionary) -> void:
	if info.is_empty():
		_card_title.text = "Point at a part"
		_card_body.text = "Its name and mass show here. Click to pin it."
		return
	var total := maxf(stage.total_mass_kg(), 1.0)
	_card_title.text = str(info["label"])
	var lines := PackedStringArray(["Mass  %s  (%.1f%% of the Juggernaut)" % [kg(float(info["mass_kg"])), float(info["mass_kg"]) / total * 100.0]])
	if float(info["health"]) > 0.0:
		lines.append("Health  %d   ·   Armour  %d mm" % [roundi(float(info["health"])), roundi(float(info["armour_mm"]))])
	if str(info["note"]) != "":
		lines.append(str(info["note"]))
	_card_body.text = "\n".join(lines)


# --- input -------------------------------------------------------------------------------------


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if b.button_index == MOUSE_BUTTON_WHEEL_UP and b.pressed:
			stage.zoom(float(Registry.file("hangar")["stage"]["orbit"].get("zoom_step", 0.9)))
		elif b.button_index == MOUSE_BUTTON_WHEEL_DOWN and b.pressed:
			stage.zoom(1.0 / float(Registry.file("hangar")["stage"]["orbit"].get("zoom_step", 0.9)))
		elif b.button_index == MOUSE_BUTTON_LEFT:
			_down = b.pressed
			if b.pressed:
				_drag_from = b.position
				_dragging = false
			elif not _dragging:
				_click_at(b.position)
			_dragging = false
	elif event is InputEventMouseMotion and _down:
		var m := event as InputEventMouseMotion
		if not _dragging and m.position.distance_to(_drag_from) > DRAG_PX:
			_dragging = true
		if _dragging:
			var step := float(Registry.file("hangar")["stage"]["orbit"].get("mouse_orbit_rad_px", 0.006))
			if Input.is_key_pressed(KEY_SHIFT):
				stage.pan(-m.relative.x * 0.01, m.relative.y * 0.01)
			else:
				stage.orbit(-m.relative.x * step, -m.relative.y * step)
	elif event is InputEventMouseMotion and (event as InputEventMouseMotion).button_mask & (MOUSE_BUTTON_MASK_MIDDLE | MOUSE_BUTTON_MASK_RIGHT) != 0:
		var m2 := event as InputEventMouseMotion
		if (m2.button_mask & MOUSE_BUTTON_MASK_MIDDLE) != 0:
			stage.pan(-m2.relative.x * 0.01, m2.relative.y * 0.01)
		else:
			stage.orbit(-m2.relative.x * 0.006, -m2.relative.y * 0.006)
	elif event.is_action_pressed("screenshot"):
		save_photo.call_deferred()
	elif event.is_action_pressed("photo_mode"):
		set_panels_hidden(not _hidden_ui)
	elif event.is_action_pressed("ui_tab_prev"):
		cycle_light(-1)
	elif event.is_action_pressed("ui_tab_next"):
		cycle_light(1)
	elif event.is_action_pressed("ui_reset"):
		stage.reset_view()
	elif event.is_action_pressed("ui_cancel") or event.is_action_pressed("ui_back"):
		get_viewport().set_input_as_handled()
		go_back()


func _click_at(point: Vector2) -> void:
	var hit := stage.pick(point)
	pin_part(str(hit["id"]) if not hit.is_empty() else "")


func go_back() -> void:
	Game.goto_main_menu()


func set_panels_hidden(hide_them: bool) -> void:
	_hidden_ui = hide_them
	_ui.visible = not hide_them


## Saves the picture with no panels in it, to Pictures/Eighty Six; the panels come back after.
func save_photo() -> String:
	var was_hidden := _hidden_ui
	set_panels_hidden(true)
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	set_panels_hidden(was_hidden)
	if image == null or image.is_empty():
		return ""
	var path := PhotoMode.photo_path()
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	if image.save_png(path) == OK:
		last_saved = path
	return last_saved


func _process(delta: float) -> void:
	var on_pad := Controls.last_device == "pad"
	_reticle.visible = on_pad and not _hidden_ui
	var cfg: Dictionary = Registry.file("hangar")["stage"]["orbit"]
	var rate := deg_to_rad(float(cfg.get("stick_orbit_deg_s", 100.0))) * delta
	var aim := Controls.stick("aim")
	if aim.length() > 0.0:
		stage.orbit(-aim.x * rate, -aim.y * rate)
	var move := Controls.stick("move")
	if move.length() > 0.0:
		var pan_rate := float(cfg.get("pan_m_s", 3.0)) * delta
		stage.pan(move.x * pan_rate, -move.y * pan_rate)
	var z := Controls.trigger("fire_main") - Controls.trigger("brake")
	if absf(z) > 0.05:
		stage.zoom(1.0 - z * delta)
	if not _sized and stage.settled():
		_sized = true
		var box := stage.model_size()
		_size_label.text = "%s\nStanding %.1f m long, %.1f m wide, %.1f m high" % [_parts_note, box.z, box.x, box.y]
	_update_hover(on_pad)


func _update_hover(on_pad: bool) -> void:
	if _hidden_ui or _dragging or not stage.settled():
		_tip.visible = false
		return
	var point := get_viewport().get_visible_rect().size * 0.5 if on_pad else get_viewport().get_mouse_position()
	var over_panel := false
	if not on_pad:
		var hover := get_viewport().gui_get_hovered_control()
		over_panel = hover != null and hover != self
	var hit := {} if over_panel else stage.pick(point)
	var id := str(hit.get("id", ""))
	if id != str(hovered.get("id", "")):
		hovered = hit
		if pinned.is_empty():
			if id == "":
				stage.clear_highlight()
			else:
				stage.highlight(id)
		if pinned.is_empty():
			_show_card(hit)
	if hit.is_empty():
		_tip.visible = false
		return
	_tip_label.text = "%s   %s" % [hit["label"], kg(float(hit["mass_kg"]))]
	_tip.visible = true
	_tip.reset_size()
	var size := get_viewport().get_visible_rect().size
	_tip.position = (point + Vector2(22, 18)).clamp(Vector2.ZERO, size - _tip.size)


func _on_light_changed(_id: String) -> void:
	_refresh_selector(_light_button)


func _refresh_hint() -> void:
	if Controls.last_device == "pad":
		_hint.text = "Right stick  orbit   ·   Left stick  move   ·   L2 / R2  zoom   ·   L1 / R1  lighting   ·   Square  reset view   ·   Circle  back"
	else:
		_hint.text = "Drag  orbit   ·   Wheel  zoom   ·   Shift + drag or middle drag  move   ·   Click a part  pin it   ·   Q / E  lighting   ·   Backspace  reset view   ·   O  hide panels   ·   F12  photo   ·   Esc  back"


func _draw_reticle() -> void:
	var c := UiTheme.color("text")
	_reticle.draw_arc(Vector2.ZERO, 11.0, 0.0, TAU, 28, Color(0, 0, 0, 0.6), 4.0)
	_reticle.draw_arc(Vector2.ZERO, 11.0, 0.0, TAU, 28, c, 2.0)
