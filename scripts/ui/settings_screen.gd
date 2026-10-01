extends Control
## The settings screen, drawn entirely from data/settings.json: section tabs across the top,
## the section's pages (sub-menus) on the left, rows in the middle, help on the right.
## Every row lines up on the same three columns: name, control, value. Changes apply live.
## Pad: L1/R1 switch sections, the stick moves, left/right changes a value, Square resets it.

signal closed

const LABEL_W := 330
const CONTROL_W := 400
const VALUE_W := 150
const KEY_SLOT_W := 170
const PAD_SLOT_W := 240
const CAPTURE_TIMEOUT_S := 8.0

var _section_id := ""
var _page_id := ""
var _tabs: HBoxContainer
var _pages: VBoxContainer
var _content: VBoxContainer
var _scroll: ScrollContainer
var _help_title: Label
var _help_value: Label
var _help_text: Label
var _help_default: Label
var _help_warn: Label
var _rows: Dictionary = {}
var _focused_key := ""
var _capture: Control = null
var _capture_info: Dictionary = {}
var _capture_left := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build_frame()
	Settings.changed.connect(_on_setting_changed)
	Controls.bindings_changed.connect(_on_bindings_changed)
	UiTheme.theme_changed.connect(_on_theme_changed)
	var first: Dictionary = Settings.sections()[0]
	show_page(str(first["id"]), "")


func show_page(section_id: String, page_id: String) -> void:
	var section := _section(section_id)
	if section.is_empty():
		section = Settings.sections()[0]
	_section_id = str(section["id"])
	var visible := _visible_pages(section)
	if page_id == "" or not visible.any(func(p: Dictionary) -> bool: return p["id"] == page_id):
		page_id = str(visible[0]["id"])
	_page_id = page_id
	_rebuild_tabs()
	_rebuild_pages()
	_rebuild_content()
	_show_first_help()
	_focus_first_row.call_deferred()


func close() -> void:
	Settings.save_now()
	closed.emit()
	queue_free()


# --- frame ------------------------------------------------------------------------------------


func _build_frame() -> void:
	var shade := ColorRect.new()
	shade.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	shade.color = Color(UiTheme.color("bg"), 0.94)
	add_child(shade)
	add_child(UiTheme.make_backdrop())
	(get_child(1) as ColorRect).modulate = Color(1, 1, 1, 0.55)

	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	for side: String in ["left", "right"]:
		margin.add_theme_constant_override("margin_" + side, 80)
	margin.add_theme_constant_override("margin_top", 48)
	margin.add_theme_constant_override("margin_bottom", 40)
	add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 16)
	margin.add_child(column)

	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 28)
	column.add_child(top)
	var title := Label.new()
	title.text = "Settings"
	title.theme_type_variation = "TitleLabel"
	title.custom_minimum_size.x = 300
	top.add_child(title)
	_tabs = HBoxContainer.new()
	_tabs.add_theme_constant_override("separation", 6)
	_tabs.size_flags_horizontal = SIZE_EXPAND_FILL
	_tabs.alignment = BoxContainer.ALIGNMENT_BEGIN
	top.add_child(_tabs)
	var hint := Label.new()
	hint.theme_type_variation = "FaintLabel"
	hint.text = "Q / E  ·  L1 / R1  sections"
	hint.size_flags_vertical = SIZE_SHRINK_CENTER
	top.add_child(hint)

	column.add_child(HSeparator.new())

	var body := HBoxContainer.new()
	body.size_flags_vertical = SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 26)
	column.add_child(body)

	_pages = VBoxContainer.new()
	_pages.custom_minimum_size.x = 260
	_pages.add_theme_constant_override("separation", 4)
	body.add_child(_pages)

	var card := PanelContainer.new()
	card.theme_type_variation = "CardPanel"
	card.size_flags_horizontal = SIZE_EXPAND_FILL
	body.add_child(card)
	_scroll = ScrollContainer.new()
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.follow_focus = true
	card.add_child(_scroll)
	_content = VBoxContainer.new()
	_content.size_flags_horizontal = SIZE_EXPAND_FILL
	_content.add_theme_constant_override("separation", 4)
	_scroll.add_child(_content)

	var help := PanelContainer.new()
	help.theme_type_variation = "HelpPanel"
	help.custom_minimum_size.x = 400
	body.add_child(help)
	var help_box := VBoxContainer.new()
	help_box.add_theme_constant_override("separation", 12)
	help.add_child(help_box)
	_help_title = _label(help_box, "HeadingLabel", "")
	_help_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_help_value = _label(help_box, "AccentLabel", "")
	help_box.add_child(HSeparator.new())
	_help_text = _label(help_box, "", "")
	_help_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_help_default = _label(help_box, "DimLabel", "")
	_help_warn = _label(help_box, "WarnLabel", "")
	_help_warn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	column.add_child(HSeparator.new())
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 14)
	column.add_child(footer)
	var prompts := _label(footer, "FaintLabel", "Enter / Cross  choose   ·   Backspace / Square  reset setting   ·   Esc / Circle  back")
	prompts.size_flags_horizontal = SIZE_EXPAND_FILL
	prompts.size_flags_vertical = SIZE_SHRINK_CENTER
	var reset := Button.new()
	reset.text = "Reset page"
	reset.pressed.connect(func() -> void: Settings.reset_page(_section_id, _page_id))
	footer.add_child(reset)
	var back := Button.new()
	back.text = "Back"
	back.custom_minimum_size.x = 160
	back.pressed.connect(close)
	footer.add_child(back)


func _rebuild_tabs() -> void:
	for child in _tabs.get_children():
		child.get_parent().remove_child(child)
		child.queue_free()
	var group := ButtonGroup.new()
	for section: Dictionary in Settings.sections():
		var tab := Button.new()
		tab.text = str(section["label"])
		tab.theme_type_variation = "TabButton"
		tab.toggle_mode = true
		tab.button_group = group
		tab.focus_mode = FOCUS_NONE
		tab.button_pressed = section["id"] == _section_id
		var id := str(section["id"])
		tab.pressed.connect(func() -> void: show_page(id, ""))
		_tabs.add_child(tab)


func _rebuild_pages() -> void:
	for child in _pages.get_children():
		child.get_parent().remove_child(child)
		child.queue_free()
	var group := ButtonGroup.new()
	for page: Dictionary in _visible_pages(_section(_section_id)):
		var b := Button.new()
		b.text = str(page["label"])
		b.theme_type_variation = "PageButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = page["id"] == _page_id
		var id := str(page["id"])
		b.pressed.connect(func() -> void: show_page(_section_id, id))
		_pages.add_child(b)


func _rebuild_content() -> void:
	for child in _content.get_children():
		child.get_parent().remove_child(child)
		child.queue_free()
	_rows.clear()
	var page := _page(_section_id, _page_id)
	var first := true
	for group: Dictionary in page.get("groups", []):
		var items: Array = group.get("items", [])
		if items.is_empty():
			continue
		if not first:
			var gap := Control.new()
			gap.custom_minimum_size.y = 14
			_content.add_child(gap)
		first = false
		var header := _label(_content, "GroupLabel", str(group.get("label", "")))
		header.custom_minimum_size.y = 40
		for it: Dictionary in items:
			if str(it.get("visible_if", "")) != "" and not Settings.get_b(str(it["visible_if"])):
				continue
			if str(it.get("type", "")) == "keybinds":
				_add_keybinds(str(it.get("scheme", "standard")))
			else:
				_add_row(it)
	_scroll.scroll_vertical = 0


# --- rows ---------------------------------------------------------------------------------------


func _add_row(it: Dictionary) -> void:
	var key := str(it["key"])
	var row := PanelContainer.new()
	row.theme_type_variation = "RowPanel"
	_content.add_child(row)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 18)
	row.add_child(line)
	var name := _label(line, "", str(it.get("label", key)))
	name.custom_minimum_size.x = LABEL_W
	name.clip_text = true
	name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	name.size_flags_vertical = SIZE_SHRINK_CENTER
	var control := _make_control(it)
	control.set_meta("setting_key", key)
	control.custom_minimum_size.x = CONTROL_W
	control.size_flags_vertical = SIZE_SHRINK_CENTER
	line.add_child(control)
	var value := _label(line, "MonoLabel", "")
	value.custom_minimum_size.x = VALUE_W
	value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	value.size_flags_vertical = SIZE_SHRINK_CENTER
	_rows[key] = {"row": row, "control": control, "value": value, "item": it}
	if control.focus_mode != FOCUS_NONE:
		control.focus_entered.connect(_on_row_focus.bind(key, true))
		control.focus_exited.connect(_on_row_focus.bind(key, false))
	control.mouse_entered.connect(_show_help.bind(key))
	_refresh_row(key)


func _make_control(it: Dictionary) -> Control:
	var key := str(it["key"])
	match str(it.get("type", "")):
		"toggle":
			var toggle := CheckButton.new()
			toggle.toggled.connect(func(on: bool) -> void: Settings.set_value(key, on))
			return toggle
		"slider":
			var slider := HSlider.new()
			slider.min_value = float(it.get("min", 0.0))
			slider.max_value = float(it.get("max", 1.0))
			slider.step = float(it.get("step", 0.01))
			slider.custom_minimum_size.y = 34
			slider.value_changed.connect(func(v: float) -> void: Settings.set_value(key, v))
			return slider
		"choice":
			var sel := Button.new()
			sel.theme_type_variation = "SelectorButton"
			sel.pressed.connect(_cycle.bind(key, 1))
			sel.gui_input.connect(_selector_input.bind(key))
			return sel
		"button":
			var b := Button.new()
			b.text = str(it.get("button_text", "Run"))
			if str(it.get("action", "")).begins_with("reset"):
				b.text = "Reset"
			elif str(it.get("action", "")) == "rumble_test":
				b.text = "Test"
			b.pressed.connect(_run_action.bind(str(it.get("action", ""))))
			return b
		_:
			var info := Label.new()
			info.theme_type_variation = "DimLabel"
			info.text = str(it.get("text", ""))
			info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			return info


func _refresh_row(key: String) -> void:
	if not _rows.has(key):
		return
	var r: Dictionary = _rows[key]
	var it: Dictionary = r["item"]
	var control: Control = r["control"]
	var value: Variant = Settings.get_value(key) if Settings.has_key(key) and it.has("default") else null
	match str(it.get("type", "")):
		"toggle":
			(control as CheckButton).set_pressed_no_signal(bool(value))
		"slider":
			(control as HSlider).set_value_no_signal(float(value))
		"choice":
			(control as Button).text = "‹   %s   ›" % Settings.label_for(key, value)
	var value_label: Label = r["value"]
	if value != null and str(it.get("type", "")) == "slider":
		value_label.text = Settings.label_for(key, value)
	elif value != null and str(it.get("type", "")) == "toggle":
		value_label.text = "On" if bool(value) else "Off"
	else:
		value_label.text = ""
	if value != null and not Settings.is_default(key):
		value_label.text = ("•  " + value_label.text).strip_edges() if value_label.text != "" else "•"
	if key == _focused_key:
		_show_help(key)


func _on_row_focus(key: String, has_focus: bool) -> void:
	if not _rows.has(key):
		return
	var row: PanelContainer = _rows[key]["row"]
	row.theme_type_variation = "RowPanelFocus" if has_focus else "RowPanel"
	if has_focus:
		_focused_key = key
		_show_help(key)


func _show_help(key: String) -> void:
	var it := Settings.item(key)
	if it.is_empty() and _rows.has(key):
		it = _rows[key]["item"]
	_help_title.text = str(it.get("label", ""))
	_help_text.text = str(it.get("help", ""))
	_help_warn.text = ""
	if it.has("default"):
		var value: Variant = Settings.get_value(key)
		_help_value.text = Settings.label_for(key, value)
		_help_default.text = "Default: " + Settings.label_for(key, it["default"])
		if not Settings.is_default(key):
			_help_default.text += "   ·   changed"
	else:
		_help_value.text = ""
		_help_default.text = ""


func _cycle(key: String, direction: int) -> void:
	var options := Settings.options_for(key)
	if options.is_empty():
		return
	var current: Variant = Settings.get_value(key)
	var index := 0
	for i in options.size():
		if Settings._same(options[i][0], current):
			index = i
	index = wrapi(index + direction, 0, options.size())
	Settings.set_value(key, options[index][0])


func _selector_input(event: InputEvent, key: String) -> void:
	if event.is_action_pressed("ui_left"):
		_cycle(key, -1)
		accept_event()
	elif event.is_action_pressed("ui_right"):
		_cycle(key, 1)
		accept_event()
	elif event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
		if (event as InputEventMouseButton).button_index == MOUSE_BUTTON_RIGHT:
			_cycle(key, -1)
			accept_event()


func _run_action(action: String) -> void:
	if action.begins_with("reset_bindings:"):
		Controls.reset_scheme(action.substr(15))
	elif action == "rumble_test":
		Rumble.play("fire_main")
	elif action.contains("."):
		# "Autoload.method", e.g. "Music.skip": a settings button calls one method of an autoload
		var node := get_node_or_null("/root/" + action.get_slice(".", 0))
		if node != null:
			node.call(action.get_slice(".", 1))


# --- key bindings -------------------------------------------------------------------------------


func _add_keybinds(scheme: String) -> void:
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 12)
	_content.add_child(head)
	var titles := ["Action", "Key or mouse", "Alternate", "Controller"]
	for i in titles.size():
		var l := _label(head, "FaintLabel", titles[i])
		l.custom_minimum_size.x = [LABEL_W, KEY_SLOT_W, KEY_SLOT_W, PAD_SLOT_W][i]
	var last_group := ""
	for action in Controls.actions_for_scheme(scheme):
		var info := Controls.action_info(action)
		var group := str(info.get("group", ""))
		if group != last_group:
			last_group = group
			var g := _label(_content, "AccentLabel", group)
			g.custom_minimum_size.y = 36
			g.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
		var row := PanelContainer.new()
		row.theme_type_variation = "RowPanel"
		_content.add_child(row)
		var line := HBoxContainer.new()
		line.add_theme_constant_override("separation", 12)
		row.add_child(line)
		var name := _label(line, "", str(info.get("label", action)))
		name.custom_minimum_size.x = LABEL_W - 14
		name.size_flags_vertical = SIZE_SHRINK_CENTER
		var b := Controls.bindings(action, scheme)
		for slot_def: Array in [["keys", 0], ["keys", 1], ["pad", 0]]:
			var slot := str(slot_def[0])
			var index := int(slot_def[1])
			var list: Array = b[slot]
			var binding := str(list[index]) if index < list.size() else ""
			var btn := Button.new()
			btn.theme_type_variation = "SlotButton"
			btn.custom_minimum_size.x = PAD_SLOT_W if slot == "pad" else KEY_SLOT_W
			btn.set_meta("binding", [action, scheme, binding])
			btn.text = Controls.binding_label(binding)
			btn.clip_text = true
			btn.pressed.connect(_start_capture.bind(action, scheme, slot, index))
			btn.focus_entered.connect(_on_slot_focus.bind(row, action, scheme, binding, true))
			btn.focus_exited.connect(_on_slot_focus.bind(row, action, scheme, binding, false))
			line.add_child(btn)


func _on_slot_focus(row: PanelContainer, action: String, scheme: String, binding: String, has_focus: bool) -> void:
	if not is_instance_valid(row):
		return
	row.theme_type_variation = "RowPanelFocus" if has_focus else "RowPanel"
	if not has_focus:
		return
	_show_binding_help(action, scheme, binding)


## The help panel describes the control that gets focus first, straight away: focus arrives a
## frame later (deferred), or never while the window is in the background.
func _show_first_help() -> void:
	var target := _first_target()
	if target == null:
		return
	if target.has_meta("setting_key"):
		_focused_key = str(target.get_meta("setting_key"))
		_show_help(_focused_key)
	elif target.has_meta("binding"):
		var b: Array = target.get_meta("binding")
		_show_binding_help(str(b[0]), str(b[1]), str(b[2]))


func _show_binding_help(action: String, scheme: String, binding: String) -> void:
	_focused_key = ""
	var info := Controls.action_info(action)
	_help_title.text = str(info.get("label", action))
	_help_value.text = Controls.binding_label(binding)
	_help_text.text = "Choose a slot and press the new key, mouse button or controller button. Escape cancels; Delete clears the slot."
	_help_default.text = "Scheme: " + scheme
	var clash := Controls.conflicts(action, scheme, binding) if binding != "" else PackedStringArray()
	_help_warn.text = ("Also bound to: " + ", ".join(_labels_of(clash))) if clash.size() > 0 else ""


func _start_capture(action: String, scheme: String, slot: String, index: int) -> void:
	_capture_info = {"action": action, "scheme": scheme, "slot": slot, "index": index}
	_capture_left = CAPTURE_TIMEOUT_S
	_capture = Control.new()
	_capture.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	add_child(_capture)
	var shade := ColorRect.new()
	shade.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	shade.color = Color(0, 0, 0, 0.6)
	_capture.add_child(shade)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	_capture.add_child(center)
	var card := PanelContainer.new()
	card.theme_type_variation = "CardPanel"
	center.add_child(card)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 14)
	card.add_child(box)
	var what := "a key or mouse button" if slot == "keys" else "a controller button, trigger or stick direction"
	_label(box, "HeadingLabel", str(Controls.action_info(action).get("label", action)))
	_label(box, "", "Press %s." % what)
	_label(box, "FaintLabel", "Escape cancels  ·  Delete clears  ·  cancels itself after %d s" % int(CAPTURE_TIMEOUT_S))


func _end_capture() -> void:
	if _capture != null:
		_capture.queue_free()
	_capture = null
	_capture_info = {}


func _input(event: InputEvent) -> void:
	if _capture == null:
		return
	get_viewport().set_input_as_handled()
	if event is InputEventKey and event.is_pressed() and not event.is_echo():
		var code := (event as InputEventKey).physical_keycode
		if code == KEY_ESCAPE:
			_end_capture()
			return
		if code == KEY_DELETE:
			_finish_capture("")
			return
	var binding := ""
	if _capture_info["slot"] == "keys":
		if (event is InputEventKey or event is InputEventMouseButton) and event.is_pressed() and not event.is_echo():
			binding = Controls.binding_of(event)
	else:
		if event is InputEventJoypadButton and event.is_pressed():
			binding = Controls.binding_of(event)
		elif event is InputEventJoypadMotion and absf((event as InputEventJoypadMotion).axis_value) > 0.6:
			binding = Controls.binding_of(event)
	if binding != "":
		_finish_capture(binding)


func _finish_capture(binding: String) -> void:
	var info := _capture_info.duplicate()
	_end_capture()
	Controls.set_binding(info["action"], info["scheme"], info["slot"], info["index"], binding)
	var clash := Controls.conflicts(info["action"], info["scheme"], binding) if binding != "" else PackedStringArray()
	_help_warn.text = ("Also bound to: " + ", ".join(_labels_of(clash))) if clash.size() > 0 else ""


func _labels_of(actions: PackedStringArray) -> PackedStringArray:
	var out := PackedStringArray()
	for a in actions:
		out.append(str(Controls.action_info(a).get("label", a)))
	return out


# --- input and updates --------------------------------------------------------------------------


func _process(delta: float) -> void:
	if _capture != null:
		_capture_left -= delta
		if _capture_left <= 0.0:
			_end_capture()


func _unhandled_input(event: InputEvent) -> void:
	if _capture != null:
		return
	if event.is_action_pressed("ui_back") or event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		close()
	elif event.is_action_pressed("ui_tab_next") or event.is_action_pressed("ui_tab_prev"):
		get_viewport().set_input_as_handled()
		var ids: Array = Settings.sections().map(func(s: Dictionary) -> String: return str(s["id"]))
		var step := 1 if event.is_action_pressed("ui_tab_next") else -1
		show_page(str(ids[wrapi(ids.find(_section_id) + step, 0, ids.size())]), "")
	elif event.is_action_pressed("ui_reset") and _focused_key != "":
		get_viewport().set_input_as_handled()
		Settings.reset(_focused_key)


func _on_setting_changed(key: String, _value: Variant) -> void:
	_refresh_row(key)
	for page: Dictionary in _section(_section_id).get("pages", []):
		if str(page.get("visible_if", "")) == key:
			_rebuild_pages()
	for r: Dictionary in _rows.values():
		if str(r["item"].get("visible_if", "")) == key:
			_rebuild_content()
			return


func _on_bindings_changed(_scheme: String) -> void:
	if _capture == null and _page_id.contains("bindings"):
		var focused := get_viewport().gui_get_focus_owner()
		var path := _content.get_path_to(focused) if focused != null and _content.is_ancestor_of(focused) else NodePath()
		_rebuild_content()
		if path != NodePath():
			_refocus.call_deferred(path)


func _refocus(path: NodePath) -> void:
	var node := _content.get_node_or_null(path)
	if node is Control:
		(node as Control).grab_focus()


func _on_theme_changed() -> void:
	for child in get_children():
		if child is ColorRect and (child as ColorRect).material != null:
			UiTheme.style_backdrop(child)


func _focus_first_row() -> void:
	var target := _first_target()
	if target != null:
		target.grab_focus()


func _first_target() -> Control:
	for child in _content.get_children():
		var target := _first_focusable(child)
		if target != null:
			return target
	return null


func _first_focusable(node: Node) -> Control:
	if node is Control and (node as Control).focus_mode == FOCUS_ALL and not node is ScrollContainer:
		return node
	for child in node.get_children():
		var found := _first_focusable(child)
		if found != null:
			return found
	return null


func _section(id: String) -> Dictionary:
	for s: Dictionary in Settings.sections():
		if s["id"] == id:
			return s
	return {}


func _page(section_id: String, page_id: String) -> Dictionary:
	for p: Dictionary in _section(section_id).get("pages", []):
		if p["id"] == page_id:
			return p
	return {}


func _visible_pages(section: Dictionary) -> Array:
	return section.get("pages", []).filter(
		func(p: Dictionary) -> bool:
			return str(p.get("visible_if", "")) == "" or Settings.get_b(str(p["visible_if"]))
	)


func _label(parent: Node, variation: String, text: String) -> Label:
	var l := Label.new()
	l.text = text
	if variation != "":
		l.theme_type_variation = variation
	parent.add_child(l)
	return l
