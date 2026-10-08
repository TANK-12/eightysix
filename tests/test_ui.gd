extends "res://tests/lib/test_case.gd"
## The menus build from the registries without errors: main menu, every settings page (including
## the hidden hardcore one), the pause menu and both themes.


func after_each() -> void:
	Settings.reset_all_quietly()
	UiTheme.apply(Settings.get_s("interface.theme"))


func test_main_menu_and_every_settings_page() -> void:
	var menu: Control = (load("res://scenes/ui/main_menu.tscn") as PackedScene).instantiate()
	tree.root.add_child(menu)
	await tree.process_frame
	menu.call("open_settings")
	await tree.process_frame
	var screen: Control = menu.get("_settings")
	assert_not_null(screen)
	Settings.set_value("controls.hardcore_mode", true, false)
	var pages := 0
	for section: Dictionary in Settings.sections():
		for page: Dictionary in section["pages"]:
			screen.call("show_page", section["id"], page["id"])
			await tree.process_frame
			var content: VBoxContainer = screen.get("_content")
			assert_gt(content.get_child_count(), 0, "%s/%s has rows" % [section["id"], page["id"]])
			pages += 1
	assert_gt(pages, 15, "deep menus")
	screen.call("show_page", "controls", "bindings")
	await tree.process_frame
	var slots := screen.find_children("*", "Button", true, false).filter(
		func(b: Button) -> bool: return b.theme_type_variation == "SlotButton"
	)
	assert_gt(slots.size(), 60, "a key, alternate and pad slot per action")
	Settings.set_value("controls.hardcore_mode", false, false)
	menu.free()


func test_pause_menu_builds() -> void:
	var pause: CanvasLayer = (load("res://scenes/ui/pause_menu.tscn") as PackedScene).instantiate()
	tree.root.add_child(pause)
	await tree.process_frame
	assert_gt(pause.find_children("*", "Button", true, false).size(), 4)
	# A CanvasLayer cuts Godot's theme inheritance, so the pause root must carry the theme itself.
	var root: Control = pause.get("_root")
	assert_eq(root.theme, UiTheme.theme, "pause menu is themed")
	UiTheme.apply("spearhead_field")
	assert_eq(root.theme, UiTheme.theme, "and follows a theme switch")
	_assert_fills_window(root, "pause root")
	pause.free()


## Screens built in code must fill the window: set_anchors_preset alone keeps a new node's zero size.
func test_screens_fill_the_window() -> void:
	var menu: Control = (load("res://scenes/ui/main_menu.tscn") as PackedScene).instantiate()
	tree.root.add_child(menu)
	menu.call("open_settings", "controls", "bindings")
	await tree.process_frame
	await tree.process_frame
	var screen: Control = menu.get("_settings")
	_assert_fills_window(screen, "settings screen")
	var window := tree.root.get_visible_rect()
	for b: Button in screen.find_children("*", "Button", true, false):
		if b.text == "Back" or b.text == "Reset page":
			assert_true(window.encloses(b.get_global_rect()), "%s button is on screen (%s)" % [b.text, str(b.get_global_rect())])
	var status: Label = menu.get("_status")
	assert_true(window.encloses(status.get_global_rect()), "main menu status line is on screen")
	menu.free()


func test_help_follows_the_page() -> void:
	var menu: Control = (load("res://scenes/ui/main_menu.tscn") as PackedScene).instantiate()
	tree.root.add_child(menu)
	menu.call("open_settings", "controls", "bindings")
	await tree.process_frame
	var screen: Control = menu.get("_settings")
	var title: Label = screen.get("_help_title")
	for target: Array in [["accessibility", "display"], ["audio", "volume"], ["graphics", "quality"]]:
		screen.call("show_page", target[0], target[1])
		await tree.process_frame
		var rows: Dictionary = screen.get("_rows")
		var first: Dictionary = rows[rows.keys()[0]]["item"]
		assert_eq(title.text, str(first.get("label", "")), "help shows %s/%s's first row" % target)
	screen.call("show_page", "controls", "bindings")
	await tree.process_frame
	assert_eq(title.text, str(Controls.action_info(Controls.actions_for_scheme("standard")[0]).get("label", "")), "bindings help shows the first action")
	menu.free()


func test_hud_is_themed() -> void:
	var hud: CanvasLayer = load("res://scripts/ui/test_hud.gd").new()
	tree.root.add_child(hud)
	await tree.process_frame
	var root: Control = hud.get("_root")
	assert_eq(root.theme, UiTheme.theme)
	_assert_fills_window(root, "hud root")
	hud.free()


func _assert_fills_window(c: Control, what: String) -> void:
	var window := tree.root.get_visible_rect()
	assert_almost_eq(c.get_global_rect().size.x, window.size.x, 1.0, what + " width")
	assert_almost_eq(c.get_global_rect().size.y, window.size.y, 1.0, what + " height")


func test_themes_switch_live() -> void:
	UiTheme.apply("handler_console")
	var a := UiTheme.color("accent")
	var theme_a := tree.root.theme
	UiTheme.apply("spearhead_field")
	assert_ne(UiTheme.color("accent"), a)
	assert_ne(tree.root.theme, theme_a)
	assert_true(tree.root.theme.has_stylebox("normal", "MainMenuButton"))


## Emerson after 014: the map list ran off the bottom of the screen under the graphics and
## controller status line. It must sit on screen, clear of the status line, with every map in it.
func test_map_list_fits_above_the_status_line() -> void:
	var menu: Control = (load("res://scenes/ui/main_menu.tscn") as PackedScene).instantiate()
	tree.root.add_child(menu)
	await tree.process_frame
	menu.call("open_maps")
	await tree.process_frame
	await tree.process_frame
	var panel: Control = menu.get("_maps_panel")
	var status: Label = menu.get("_status")
	var window := tree.root.get_visible_rect()
	assert_true(window.encloses(panel.get_global_rect()), "map list on screen (%s)" % str(panel.get_global_rect()))
	assert_false(panel.get_global_rect().intersects(status.get_global_rect()), "map list clear of the status line")
	var labels := panel.find_children("*", "Button", true, false).map(func(b: Button) -> String: return b.text)
	for id in Registry.ids("maps"):
		assert_true(labels.any(func(t: String) -> bool: return t.begins_with(str(Registry.entry("maps", id).get("label", id)))), "%s listed" % id)
	assert_true(panel.find_children("*", "Button", true, false).any(func(b: Button) -> bool: return b.has_focus()), "a map has the focus for the pad")
	menu.free()


## L2/R2 (Z/C) step through the pages in the settings' left column like L1/R1 step the sections:
## one page per pull of the analog trigger, however many motion events the pull sends.
func test_triggers_step_the_left_column() -> void:
	var menu: Control = (load("res://scenes/ui/main_menu.tscn") as PackedScene).instantiate()
	tree.root.add_child(menu)
	menu.call("open_settings", "graphics", "")
	await tree.process_frame
	var screen: Control = menu.get("_settings")
	var pages: Array = (screen.call("_visible_pages", screen.call("_section", "graphics")) as Array).map(func(p: Dictionary) -> String: return str(p["id"]))
	assert_gt(pages.size(), 2, "graphics has several pages")
	assert_eq(screen.get("_page_id"), pages[0])
	for v: float in [0.2, 0.7, 0.9, 1.0, 0.8]:
		screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_RIGHT, v))
	assert_eq(screen.get("_page_id"), pages[1], "one R2 pull = one page down")
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_RIGHT, 0.0))
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_RIGHT, 1.0))
	assert_eq(screen.get("_page_id"), pages[2], "released and pulled again = the next page")
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_LEFT, 1.0))
	assert_eq(screen.get("_page_id"), pages[1], "L2 = one page up")
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_LEFT, 0.0))
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_LEFT, 1.0))
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_LEFT, 0.0))
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_LEFT, 1.0))
	assert_eq(screen.get("_page_id"), pages[-1], "past the top wraps to the last page")
	assert_eq(screen.get("_section_id"), "graphics", "the section stays")
	screen.call("_unhandled_input", _trigger(JOY_AXIS_TRIGGER_RIGHT, 0.0))
	var key := InputEventKey.new()
	key.physical_keycode = KEY_C
	key.pressed = true
	screen.call("_unhandled_input", key)
	assert_eq(screen.get("_page_id"), pages[0], "C on the keyboard = next page (wraps)")
	menu.free()


func _trigger(axis: JoyAxis, value: float) -> InputEventJoypadMotion:
	var ev := InputEventJoypadMotion.new()
	ev.axis = axis
	ev.axis_value = value
	return ev


func test_the_menu_subtitle_shows_the_project_version() -> void:
	# alpha 0.1.1: the subtitle said "Alpha 0.1" by hand; it follows project.godot's config/version now
	var menu_script: GDScript = load("res://scripts/ui/main_menu.gd")
	assert_eq(menu_script.version_label("0.1.1-alpha"), "Alpha 0.1.1")
	assert_eq(menu_script.version_label("0.2.0-beta"), "Beta 0.2.0")
	assert_eq(menu_script.version_label("1.0"), "1.0")
	var v := str(ProjectSettings.get_setting("application/config/version"))
	assert_eq(menu_script.version_label(v), "Alpha 0.1.1", "project.godot says " + v)
