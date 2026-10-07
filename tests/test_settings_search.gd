extends "res://tests/lib/test_case.gd"
## Settings search (lane A7): typing in the box lists every matching setting from every section, best
## first, each a working row; key bindings match by action name; clearing the box puts the page back.

const SCREEN := preload("res://scripts/ui/settings_screen.gd")
const SEARCH := preload("res://scripts/ui/settings_search.gd")


func test_find_ranks_label_matches_first_and_spans_sections() -> void:
	var found: Array = SEARCH.find("fog")
	assert_gt(found.size(), 2, "fog finds several settings")
	assert_eq(found[0]["kind"], "item")
	var top := str(Settings.item(str(found[0]["key"])).get("label", "")).to_lower()
	assert_true(top.contains("fog"), "a setting with fog in its name comes first, not one that only mentions it")
	var sections := {}
	for r: Dictionary in SEARCH.find("volume"):
		sections[r["section"]] = true
	assert_gt(sections.size(), 1, "volume matches in more than one section (graphics fog volume, audio volume)")


func test_every_word_must_match() -> void:
	var both: Array = SEARCH.find("fog detail")
	assert_gt(both.size(), 0)
	for r: Dictionary in both:
		var it := Settings.item(str(r["key"]))
		var text := (str(it.get("label", "")) + " " + str(it.get("help", ""))).to_lower()
		assert_true(text.contains("fog") or str(r["path"]).to_lower().contains("fog"), "%s mentions fog" % r["key"])
	assert_eq(SEARCH.find("zzqqxx").size(), 0, "nonsense finds nothing")
	assert_eq(SEARCH.find("f").size(), 0, "one letter is too short to search")


func test_bindings_and_options_match() -> void:
	var jump := SEARCH.find("jump").filter(func(r: Dictionary) -> bool: return r["kind"] == "action")
	assert_gt(jump.size(), 0, "jump finds the Jump binding")
	assert_eq(jump[0]["section"], "controls")
	var borderless := SEARCH.find("borderless")
	assert_eq(borderless.size(), 1, "an option label (Borderless window) finds its setting")
	assert_eq(borderless[0]["key"], "graphics.window_mode")


func test_hidden_settings_stay_hidden() -> void:
	var before := Settings.get_b("controls.hardcore_mode")
	Settings.set_value("controls.hardcore_mode", false, false)
	for r: Dictionary in SEARCH.find("leg"):
		assert_ne(r["page"], "hardcore_bindings", "the hardcore page is hidden while its toggle is off")
	Settings.set_value("controls.hardcore_mode", before, false)


func test_screen_lists_matches_and_clears() -> void:
	var screen: Control = SCREEN.new()
	tree.root.add_child(screen)
	screen.show_page("audio", "")
	await tree.process_frame
	var page_rows: Array = screen._rows.keys()
	screen.search("fog")
	await tree.process_frame
	assert_has(screen._rows, "graphics.fog_volume_size", "a graphics setting shows while on the audio section")
	var want := SEARCH.find("fog").filter(func(r: Dictionary) -> bool: return r["kind"] == "item").size()
	assert_eq(screen._rows.size(), want, "one row per matching setting")
	# a row found by search still works
	var key := "graphics.fog_volume_size"
	var before: Variant = Settings.get_value(key)
	(screen._rows[key]["control"] as Button).pressed.emit()
	assert_ne(Settings.get_value(key), before, "the found selector changes the setting")
	Settings.set_value(key, before, false)
	screen.search("")
	await tree.process_frame
	assert_eq(screen._rows.keys(), page_rows, "clearing the box puts the page back")
	screen.search("jump")
	await tree.process_frame
	var slots := 0
	for b in screen.find_children("*", "Button", true, false):
		if b.has_meta("binding") and b.get_meta("binding")[0] == "jump":
			slots += 1
	assert_eq(slots, 3, "the Jump binding row (two keys and the pad) shows in the results")
	screen.show_page("graphics", "world")
	await tree.process_frame
	assert_eq(screen._search.text, "", "opening a page clears the search")
	screen.queue_free()
