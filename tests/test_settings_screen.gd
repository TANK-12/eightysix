extends "res://tests/lib/test_case.gd"
## Settings screen (lane B4 part 3): a selector reads "‹ value ›"; a click on its left half steps back,
## on its right half forward, the right mouse button back, and pad/keys left and right both ways.

const SCREEN := preload("res://scripts/ui/settings_screen.gd")


## What a click delivers (headless runs do not route the mouse to controls): the press reaches the
## selector's gui_input, and for the left button the Button then emits pressed.
func _click(control: Button, x: float, button := MOUSE_BUTTON_LEFT) -> void:
	var down := InputEventMouseButton.new()
	down.button_index = button
	down.pressed = true
	down.position = Vector2(x, control.size.y * 0.5)
	control.gui_input.emit(down)
	if button == MOUSE_BUTTON_LEFT:
		control.pressed.emit()


func test_selector_arrows_step_both_ways() -> void:
	var screen: Control = SCREEN.new()
	tree.root.add_child(screen)
	screen.show_page("graphics", "")
	await tree.process_frame
	await tree.process_frame
	var key := ""
	for k: String in screen._rows:
		if str(screen._rows[k]["item"].get("type", "")) == "choice" and Settings.options_for(k).size() >= 3:
			key = k
			break
	assert_true(key != "", "a choice row with three or more options")
	var sel := screen._rows[key]["control"] as Button
	var options := Settings.options_for(key)
	var before: Variant = Settings.get_value(key)
	var index := func() -> int:
		for i in options.size():
			if Settings._same(options[i][0], Settings.get_value(key)):
				return i
		return -1
	var start: int = index.call()
	_click(sel, sel.size.x * 0.9)
	await tree.process_frame
	assert_eq(index.call(), wrapi(start + 1, 0, options.size()), "right half steps forward once")
	_click(sel, sel.size.x * 0.1)
	await tree.process_frame
	assert_eq(index.call(), start, "left half steps back once")
	_click(sel, sel.size.x * 0.1)
	await tree.process_frame
	assert_eq(index.call(), wrapi(start - 1, 0, options.size()), "and again, past the start")
	_click(sel, sel.size.x * 0.5 + 4.0, MOUSE_BUTTON_RIGHT)
	await tree.process_frame
	assert_eq(index.call(), wrapi(start - 2, 0, options.size()), "the right button steps back")
	sel.pressed.emit()
	assert_eq(index.call(), wrapi(start - 1, 0, options.size()), "Cross or Enter (no click) steps forward")
	Settings.set_value(key, before, false)
	screen.queue_free()
