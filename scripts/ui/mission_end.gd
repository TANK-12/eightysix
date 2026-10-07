class_name MissionEnd
extends CanvasLayer
## Win or lose screen for a mission (lane A4 part 2): a few seconds after the end (so the last wreck
## or your own falls in view) the game pauses and a card shows the result, the time, the Legion
## destroyed and the waves, with Keep exploring (a win), Restart mission and Main menu.
## Lane A7: the after-action report beside a big grade letter: accuracy, parts shot off, the longest
## kill, damage taken, and which personal bests this sortie beat (Mission.report, SortieLog).

const DELAY_S := 3.0

var won := false
var summary: Dictionary = {}
var _left := DELAY_S
var _shown := false


## The squad's part of the stats: one line each, "Werewolf  armour 82 %  · 14 shots" or "Laughing Fox  lost".
static func squad_lines(rows: Array) -> String:
	var out := ""
	for row: Dictionary in rows:
		if bool(row.get("alive", false)):
			out += "\n%s  armour %d %%  ·  %d shots" % [row.get("callsign", ""), roundi(100.0 * float(row.get("armour", 0.0))), int(row.get("shots", 0))]
		else:
			out += "\n%s  lost" % row.get("callsign", "")
	return out


const BEST_NAMES := {"score": "grade score", "time_s": "time", "accuracy": "accuracy", "longest_kill_m": "longest kill"}


## The report's lines under the grade: "Accuracy 38 %  (14 of 37)" and the rest; empty without a report.
static func report_lines(report: Dictionary) -> PackedStringArray:
	var out := PackedStringArray()
	if report.is_empty():
		return out
	out.append("Accuracy %d %%  (%d of %d)" % [roundi(100.0 * float(report.get("accuracy", 0.0))), int(report.get("hits", 0)), int(report.get("shots", 0))])
	out.append("Your kills %d  ·  parts shot off %d" % [int(report.get("kills_by_you", 0)), int(report.get("parts_off", 0))])
	if float(report.get("longest_kill_m", 0.0)) > 0.0:
		out.append("Longest kill %d m" % roundi(float(report.get("longest_kill_m", 0.0))))
	out.append("Damage taken %d  ·  armour left %d %%" % [roundi(float(report.get("damage_taken", 0.0))), roundi(100.0 * float(report.get("armour_left", 1.0)))])
	return out


## "New best: time, accuracy" for the records this sortie beat, or "".
static func bests_line(report: Dictionary) -> String:
	var names := PackedStringArray()
	for b: Variant in report.get("bests", []):
		names.append(str(BEST_NAMES.get(str(b), str(b))))
	return ("New best: " + ", ".join(names)) if not names.is_empty() else ""


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
	card.custom_minimum_size = Vector2(640, 0)
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
	stats.text += squad_lines(summary.get("squad", []))
	var report: Dictionary = summary.get("report", {})
	if report.is_empty():
		box.add_child(stats)
	else:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 28)
		box.add_child(row)
		var grade := Label.new()
		grade.name = "Grade"
		grade.text = str(report.get("grade", "D"))
		grade.theme_type_variation = "TitleLabel"
		grade.add_theme_font_size_override("font_size", 120)
		grade.add_theme_color_override("font_color", UiTheme.color("accent"))
		grade.custom_minimum_size.x = 120
		grade.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		grade.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		row.add_child(grade)
		var col := VBoxContainer.new()
		col.add_theme_constant_override("separation", 4)
		row.add_child(col)
		col.add_child(stats)
		var more := Label.new()
		more.text = "\n".join(report_lines(report))
		col.add_child(more)
		var best := bests_line(report)
		if best != "":
			var b := Label.new()
			b.name = "Bests"
			b.text = best
			b.theme_type_variation = "AccentLabel"
			box.add_child(b)
	var gap := Control.new()
	gap.custom_minimum_size.y = 14
	box.add_child(gap)
	# Emerson's note 19 after 012: after beating every wave, keep playing on the live map with the squad.
	var first: Button = _button(box, "Keep exploring", keep_exploring) if won else null
	var restart := _button(box, "Restart mission", Game.restart_map)
	_button(box, "Main menu", Game.goto_main_menu)
	(first if first != null else restart).grab_focus.call_deferred()


## Closes the card and plays on: the map stays live with the squad, and no more waves come.
func keep_exploring() -> void:
	get_tree().paused = false
	if Game.level != null and is_instance_valid(Game.level) and Game.level.has_method("capture_mouse"):
		Game.level.call("capture_mouse")
	else:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	queue_free()


func _button(box: Control, text: String, action: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = "MainMenuButton"
	b.add_theme_font_size_override("font_size", UiTheme.size("button") + 4)
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.pressed.connect(action)
	box.add_child(b)
	return b
