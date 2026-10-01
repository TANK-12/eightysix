class_name MissionEnd
extends CanvasLayer
## Win or lose screen for a mission (lane A4 part 2): a few seconds after the end (so the last wreck
## or your own falls in view) the game pauses and a card shows the result, the time, the Legion
## destroyed and the waves, with Restart mission and Main menu.

const DELAY_S := 3.0

var won := false
var summary: Dictionary = {}
var _left := DELAY_S
var _shown := false


static func clock(seconds: float) -> String:
	return "%d:%02d" % [int(seconds) / 60, int(seconds) % 60]


func _ready() -> void:
	layer = 55
	process_mode = Node.PROCESS_MODE_ALWAYS


func _process(delta: float) -> void:
	if _shown:
		return
	_left -= delta
	if _left <= 0.0:
		show_now()


func show_now() -> void:
	if _shown:
		return
	_shown = true
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var root := Control.new()
	root.name = "EndCard"
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	UiTheme.adopt(root)
	add_child(root)
	var shade := ColorRect.new()
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.color = Color(UiTheme.color("bg"), 0.6)
	root.add_child(shade)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(center)
	var card := PanelContainer.new()
	card.theme_type_variation = "CardPanel"
	card.custom_minimum_size = Vector2(560, 0)
	center.add_child(card)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	card.add_child(box)
	var title := Label.new()
	title.text = "Mission complete" if won else "Juggernaut lost"
	title.theme_type_variation = "TitleLabel"
	box.add_child(title)
	var label := str(Registry.entry("missions", str(summary.get("mission", ""))).get("label", ""))
	var sub := Label.new()
	sub.theme_type_variation = "DimLabel"
	sub.text = "%s · %s" % [label, str(Registry.entry("maps", Game.current_map).get("label", ""))] if Game.current_map != "" else label
	box.add_child(sub)
	var stats := Label.new()
	stats.text = "Time %s\nLegion destroyed %d\nWave %d of %d" % [clock(float(summary.get("time_s", 0.0))), int(summary.get("kills", 0)), int(summary.get("wave", 0)), int(summary.get("waves", 0))]
	box.add_child(stats)
	var gap := Control.new()
	gap.custom_minimum_size.y = 14
	box.add_child(gap)
	var restart := _button(box, "Restart mission", Game.restart_map)
	_button(box, "Main menu", Game.goto_main_menu)
	restart.grab_focus.call_deferred()


func _button(box: Control, text: String, action: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = "MainMenuButton"
	b.add_theme_font_size_override("font_size", UiTheme.size("button") + 4)
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.pressed.connect(action)
	box.add_child(b)
	return b
