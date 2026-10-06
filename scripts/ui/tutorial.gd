class_name Tutorial
extends Control
## Tutorial stub (lane A6, the plan: "a tutorial only as a stub that is off by default; he decides after
## testing"). data/tutorial.json lists the steps; one shows at a time at the top of the screen until every
## item of its "done_when" holds over MoveHints' state (plus step_s, seconds on this step). Nothing runs
## while Settings > Menus and theme > Learning > Tutorial is off.

const FADE_S := 0.4

var hints: MoveHints
var step := 0
var step_s := 0.0
var _ids: Array = []
var _text := ""


func watch(source: MoveHints) -> void:
	hints = source


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ids = ordered(Registry.file("tutorial").get("entries", {}))


## The step ids by "order".
static func ordered(entries: Dictionary) -> Array:
	var ids: Array = entries.keys()
	ids.sort_custom(func(a: Variant, b: Variant) -> bool: return float((entries[a] as Dictionary).get("order", 1000.0)) < float((entries[b] as Dictionary).get("order", 1000.0)))
	return ids


## The step to show next: `index` + 1 when step `index` is finished for `state`, else `index`.
static func advance(ids: Array, entries: Dictionary, index: int, state: Dictionary) -> int:
	if index >= ids.size():
		return index
	if MoveHints.matches((entries[ids[index]] as Dictionary).get("done_when", []), state):
		return index + 1
	return index


func finished() -> bool:
	return step >= _ids.size()


func current_id() -> String:
	return "" if finished() else str(_ids[step])


func _process(delta: float) -> void:
	if not Settings.get_b("gameplay.tutorial") or hints == null or finished():
		if _text != "":
			_text = ""
			queue_redraw()
		return
	if Game.is_paused() or hints.mech == null or not is_instance_valid(hints.mech):
		return
	step_s += delta
	var state := hints.state()
	state["step_s"] = step_s
	var entries: Dictionary = Registry.file("tutorial").get("entries", {})
	var next := advance(_ids, entries, step, state)
	if next != step:
		step = next
		step_s = 0.0
	_text = "" if finished() else MoveHints.bind_text(str((entries[current_id()] as Dictionary).get("text", "")))
	queue_redraw()


func _draw() -> void:
	if _text == "":
		return
	var alpha := clampf(step_s / FADE_S, 0.0, 1.0)
	var font := UiTheme.font("body")
	var size_px := 20
	var width := minf(size.x - 160.0, 820.0)
	var lines := font.get_multiline_string_size(_text, HORIZONTAL_ALIGNMENT_LEFT, width - 40.0, size_px)
	width = minf(width, maxf(lines.x, 260.0) + 44.0)
	var head := "Tutorial %d / %d" % [step + 1, _ids.size()]
	var rect := Rect2((size.x - width) * 0.5, size.y * 0.2, width, lines.y + 52.0)  # below the mission banner
	draw_rect(rect, Color(UiTheme.color("panel"), 0.9 * alpha))
	draw_rect(rect, Color(UiTheme.color("line"), alpha), false, 1.0)
	draw_rect(Rect2(rect.position, Vector2(rect.size.x, 2.0)), Color(UiTheme.color("accent"), alpha))
	var mono := UiTheme.font("mono")
	draw_string(mono, rect.position + Vector2(20.0, 10.0 + mono.get_ascent(14)), head, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(UiTheme.color("text_dim"), alpha))
	draw_multiline_string(font, rect.position + Vector2(20.0, 36.0 + font.get_ascent(size_px)), _text, HORIZONTAL_ALIGNMENT_LEFT, width - 40.0, size_px, -1, Color(UiTheme.color("text"), alpha))
