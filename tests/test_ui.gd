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
	pause.free()


func test_themes_switch_live() -> void:
	UiTheme.apply("handler_console")
	var a := UiTheme.color("accent")
	var theme_a := tree.root.theme
	UiTheme.apply("spearhead_field")
	assert_ne(UiTheme.color("accent"), a)
	assert_ne(tree.root.theme, theme_a)
	assert_true(tree.root.theme.has_stylebox("normal", "MainMenuButton"))
