extends Node
## Scripted runs for checks: plays a timed input file, saves screenshots, measures frame rates,
## samples the player mech and writes report.json, then quits. Inert unless the game is started
## with user arguments after "--":
##   --bot=res://tools/bot/smoke.json   the script (see tools/bot/README.md for the step types)
##   --out=/abs/folder                  where screenshots and report.json go
##   --preset=low|medium|high|ultra     graphics preset for the run (optional)
##   --size=1920x1080                   window size (optional, default 1920x1080)
## tools/bot_run.sh and tools/fps_log.sh wrap this.

var active := false
var script_path := ""
var out_dir := ""
var preset := ""
var window_size := Vector2i(1920, 1080)
var steps: Array = []
var report: Dictionary = {}

var _clock := -1.0
var _next := 0
var _holds: Dictionary = {}
var _measure: Dictionary = {}
var _errors: PackedStringArray = []


func _init() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--bot="):
			script_path = arg.substr(6)
		elif arg.begins_with("--out="):
			out_dir = arg.substr(6)
		elif arg.begins_with("--preset="):
			preset = arg.substr(9)
		elif arg.begins_with("--size="):
			var parts := arg.substr(7).split("x")
			if parts.size() == 2:
				window_size = Vector2i(int(parts[0]), int(parts[1]))
	active = script_path != ""


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if not active:
		return
	var parsed: Variant = parse_script(FileAccess.get_file_as_string(script_path))
	if not parsed is Dictionary:
		_fail("cannot read bot script %s" % script_path)
		return
	var script: Dictionary = parsed
	steps = script.get("steps", [])
	report = {
		"script": script_path,
		"name": script.get("name", script_path.get_file().get_basename()),
		"started": Time.get_datetime_string_from_system(),
		"preset": preset,
		"shots": [],
		"measures": [],
		"samples": [],
		"errors": [],
		"gpu": RenderingServer.get_video_adapter_name(),
		"blender_running": false,
	}
	if out_dir == "":
		out_dir = ProjectSettings.globalize_path("user://bot")
	DirAccess.make_dir_recursive_absolute(out_dir)
	if preset != "":
		Settings.set_value("graphics.preset", preset, false)
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	DisplayServer.window_set_size(window_size)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	report["resolution"] = [window_size.x, window_size.y]
	var start_map := str(script.get("map", ""))
	if start_map != "":
		Game.level_ready.connect(_on_level_ready, CONNECT_ONE_SHOT)
		Game.start_map.call_deferred(start_map)
	else:
		_clock = 0.0


## A bot script is JSON: {"name", "map" (optional), "steps": [{"at": seconds, <one action>}]}.
static func parse_script(text: String) -> Variant:
	var data: Variant = JSON.parse_string(text)
	if not data is Dictionary or not (data as Dictionary).get("steps") is Array:
		return null
	var list: Array = (data as Dictionary)["steps"]
	list.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return float(a.get("at", 0.0)) < float(b.get("at", 0.0)))
	return data


func _on_level_ready(_level: Node) -> void:
	_clock = 0.0


func _process(delta: float) -> void:
	if not active or _clock < 0.0:
		return
	_clock += delta
	if not _measure.is_empty():
		(_measure["frames"] as Array).append(delta)
		if _clock >= float(_measure["until"]):
			_finish_measure()
	for action: String in _holds.keys():
		if _clock >= float(_holds[action]):
			Input.action_release(action)
			_holds.erase(action)
	while _next < steps.size() and _clock >= float(steps[_next].get("at", 0.0)):
		_run_step(steps[_next])
		_next += 1


func _run_step(step: Dictionary) -> void:
	if step.has("press"):
		Input.action_press(str(step["press"]), float(step.get("strength", 1.0)))
		if step.has("for"):
			_holds[str(step["press"])] = _clock + float(step["for"])
	elif step.has("release"):
		Input.action_release(str(step["release"]))
	elif step.has("shot"):
		_shot(str(step["shot"]))
	elif step.has("measure"):
		_measure = {"label": str(step.get("label", "fps")), "until": _clock + float(step["measure"]), "frames": []}
	elif step.has("sample"):
		_sample(str(step["sample"]))
	elif step.has("setting"):
		Settings.set_value(str(step["setting"]), step.get("value"), false)
	elif step.has("goto"):
		_goto(str(step["goto"]))
	elif step.has("call"):
		var scene := get_tree().current_scene
		if scene != null and scene.has_method(str(step["call"])):
			scene.callv(str(step["call"]), step.get("args", []))
		else:
			_errors.append("no method %s on the current scene" % step["call"])
	elif step.has("quit"):
		_finish()


func _goto(where: String) -> void:
	if where == "menu":
		Game.goto_main_menu()
	elif where == "pause":
		Game.open_pause()
	elif where.begins_with("map:"):
		Game.start_map(where.substr(4))
	elif where.begins_with("settings:"):
		var scene := get_tree().current_scene
		var target := where.substr(9).split("/")
		if scene != null and scene.has_method("open_settings"):
			scene.call("open_settings", target[0], target[1] if target.size() > 1 else "")


func _shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	var file_name := "%02d-%s.png" % [(report["shots"] as Array).size() + 1, name]
	var path := out_dir.path_join(file_name)
	var err := img.save_png(path)
	if err != OK:
		_errors.append("could not save %s" % path)
	(report["shots"] as Array).append(file_name)


func _sample(label: String) -> void:
	var mech: Node = get_tree().get_first_node_in_group("player_mech")
	if mech == null or not mech.has_method("telemetry"):
		_errors.append("no player mech to sample at %s" % label)
		return
	var t: Dictionary = mech.call("telemetry")
	t["label"] = label
	t["t"] = snappedf(_clock, 0.01)
	(report["samples"] as Array).append(t)


func _finish_measure() -> void:
	var frames: Array = _measure["frames"]
	(report["measures"] as Array).append(frame_stats(frames, str(_measure["label"])))
	_measure = {}


## Average fps, the 1% low (fps at the 99th-percentile frame time) and the worst frame.
static func frame_stats(frames: Array, label: String) -> Dictionary:
	if frames.is_empty():
		return {"label": label, "frames": 0}
	var sorted := frames.duplicate()
	sorted.sort()
	var total := 0.0
	for f: float in frames:
		total += f
	var avg_ms := total / frames.size() * 1000.0
	var p99: float = sorted[mini(int(ceil(sorted.size() * 0.99)) - 1, sorted.size() - 1)]
	var worst: float = sorted[sorted.size() - 1]
	return {
		"label": label,
		"frames": frames.size(),
		"seconds": snappedf(total, 0.01),
		"avg_fps": snappedf(frames.size() / maxf(total, 0.0001), 0.1),
		"frame_ms_avg": snappedf(avg_ms, 0.01),
		"p1_low_fps": snappedf(1.0 / maxf(p99, 0.0001), 0.1),
		"min_fps": snappedf(1.0 / maxf(worst, 0.0001), 0.1),
	}


func _fail(message: String) -> void:
	_errors.append(message)
	push_error("Bot: " + message)
	_finish()


func _finish() -> void:
	if not _measure.is_empty():
		_finish_measure()
	report["errors"] = Array(_errors)
	report["finished"] = Time.get_datetime_string_from_system()
	report["render_scale"] = get_tree().root.scaling_3d_scale
	report["preset_used"] = Settings.get_s("graphics.preset")
	var f := FileAccess.open(out_dir.path_join("report.json"), FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(report, "  "))
		f.close()
	get_tree().quit(0 if _errors.is_empty() else 1)
