class_name MissionHud
extends CanvasLayer
## The mission's objective at the top left (lane A4 part 2): what to do, the wave and how many Legion
## are left, and a banner across the top for a moment whenever the objective changes. When the
## mission ends it opens the end screen (MissionEnd).

const BANNER_S := 3.5

var mission: Mission
var _root: Control
var _objective: Label
var _count: Label
var _banner: Label
var _banner_s := 0.0


func watch(m: Mission) -> void:
	mission = m
	m.objective_changed.connect(_on_objective)
	m.ended.connect(_on_ended)
	_on_objective(m.objective)


func _ready() -> void:
	layer = 12
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	UiTheme.adopt(_root)
	add_child(_root)
	var panel := PanelContainer.new()
	panel.theme_type_variation = "HelpPanel"
	panel.position = Vector2(40, 36)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	panel.add_child(box)
	var head := Label.new()
	head.text = "Objective"
	head.theme_type_variation = "DimLabel"
	box.add_child(head)
	_objective = Label.new()
	_objective.add_theme_font_size_override("font_size", UiTheme.size("button"))
	box.add_child(_objective)
	_count = Label.new()
	_count.theme_type_variation = "DimLabel"
	box.add_child(_count)
	_banner = Label.new()
	_banner.theme_type_variation = "TitleLabel"
	_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_banner.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	_banner.offset_top = 120
	_banner.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_banner.modulate.a = 0.0
	_root.add_child(_banner)


func _process(delta: float) -> void:
	if mission == null or not is_instance_valid(mission):
		return
	if mission.state == "running":
		_count.text = "Wave %d of %d · %d Legion left" % [mission.wave + 1, mission.waves_total(), mission.alive()]
	_banner_s = maxf(_banner_s - delta, 0.0)
	_banner.modulate.a = clampf(_banner_s / 0.6, 0.0, 1.0)


func _on_objective(text: String) -> void:
	_objective.text = text
	_banner.text = text
	_banner_s = BANNER_S


func _on_ended(won: bool) -> void:
	_count.text = "%d Legion destroyed in %s" % [mission.kills, MissionEnd.clock(mission.elapsed_s)]
	var end := MissionEnd.new()
	end.won = won
	end.summary = mission.summary()
	add_child(end)
