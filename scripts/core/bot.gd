extends Node
## Scripted runs for checks: plays a timed input file, saves screenshots, measures frame rates,
## samples the player mech and writes report.json, then quits. Inert unless the game is started
## with user arguments after "--":
##   --bot=res://tools/bot/smoke.json   the script (see tools/bot/README.md for the step types)
##   --out=/abs/folder                  where screenshots and report.json go
##   --preset=low|medium|high|ultra     graphics preset for the run (optional)
##   --size=1920x1080                   window size (optional, default 1920x1080)
## tools/bot_run.sh and tools/fps_log.sh wrap this.

const LEVEL_TIMEOUT_S := 90

var active := false
var script_path := ""
var out_dir := ""
var preset := ""
var window_size := Vector2i(1920, 1080)
var steps: Array = []
var report: Dictionary = {}
var _meter: MoveMeter

var _clock := -1.0
var _next := 0
var _holds: Dictionary = {}
var _measure: Dictionary = {}
var _errors: PackedStringArray = []
var _waiting_level := false
var _waited_s := 0.0
# Main-thread timing for the current frame (microseconds): physics ticks run first, then process,
# then the frame is drawn. These bracket the work and leave out the wait for the swapchain.
var _physics_start_us := -1
var _process_start_us := -1
var _frame_physics_us := 0
var _heartbeat_s := 0.0


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
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
	get_tree().physics_frame.connect(_on_physics_frame)
	get_tree().process_frame.connect(_on_process_frame)
	RenderingServer.frame_pre_draw.connect(_on_frame_pre_draw)
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


func _on_waited_level(_level: Node) -> void:
	_waiting_level = false


func _process(delta: float) -> void:
	if not active:
		return
	_heartbeat_s -= delta
	if _heartbeat_s <= 0.0:
		_heartbeat_s = 1.0
		_write_heartbeat()
	if _clock < 0.0:
		return
	if _waiting_level:
		_waited_s += delta
		if _waited_s > LEVEL_TIMEOUT_S:
			_waiting_level = false
			_fail("the level did not load within %d s" % LEVEL_TIMEOUT_S)
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
		if _waiting_level:
			break


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
		_measure = {"label": str(step.get("label", "fps")), "until": _clock + float(step["measure"]), "frames": [], "gpu": [], "cpu": []}
	elif step.has("sample"):
		_sample(str(step["sample"]))
	elif step.has("setting"):
		Settings.set_value(str(step["setting"]), step.get("value"), false)
	elif step.has("goto"):
		_goto(str(step["goto"]))
	elif step.has("call"):
		# On the current scene, or with "group" on the first node in that group (e.g. "squad", "handler_view").
		var scene: Node = get_tree().current_scene
		if step.has("group"):
			scene = get_tree().get_first_node_in_group(str(step["group"]))
		if scene != null and scene.has_method(str(step["call"])):
			scene.callv(str(step["call"]), step.get("args", []))
		else:
			_errors.append("no method %s on %s" % [step["call"], step.get("group", "the current scene")])
	elif step.has("wait"):
		# {"wait": "level"}: the clock stops until the map being loaded is up (at once if it already is).
		if str(step["wait"]) == "level" and (Game.level == null or not is_instance_valid(Game.level)):
			_waiting_level = true
			_waited_s = 0.0
			Game.level_ready.connect(_on_waited_level, CONNECT_ONE_SHOT)
	elif step.has("meter"):
		# {"meter": "start"}: lane A3's MoveMeter rides the player mech; its numbers go in the report
		# and in logs/score_move.json at quit (tools/scoreboard.py reads that file).
		var mech := get_tree().get_first_node_in_group("player_mech") as RigidBody3D
		if mech == null:
			_errors.append("no player mech to meter")
		else:
			_meter = MoveMeter.new()
			mech.add_child(_meter)
			_meter.watch(mech)
	elif step.has("quit"):
		_finish()


func _goto(where: String) -> void:
	if where == "menu":
		Game.goto_main_menu()
	elif where == "hangar":
		Game.goto_hangar()
	elif where == "pause":
		Game.open_pause()
	elif where == "photo":
		Game.open_photo()
	elif where == "game":
		Game.close_photo()
		Game.close_pause()
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
	# a mech's add-ons (GrimeBuildup and the like) can add their own figures to the sample
	for c: Node in mech.get_children():
		if c.has_method("bot_sample"):
			t.merge(c.call("bot_sample"))
	t["label"] = label
	t["t"] = snappedf(_clock, 0.01)
	(report["samples"] as Array).append(t)


func _finish_measure() -> void:
	var frames: Array = _measure["frames"]
	var stats := frame_stats(frames, str(_measure["label"]))
	stats.merge(uncapped_estimate(_measure["gpu"], _measure["cpu"]))
	var refresh := DisplayServer.screen_get_refresh_rate()
	stats["vsync"] = DisplayServer.window_get_vsync_mode() != DisplayServer.VSYNC_DISABLED
	stats["refresh_hz"] = snappedf(refresh, 0.1)
	stats["paced_share"] = paced_share(frames, refresh) if stats["vsync"] else 0.0
	(report["measures"] as Array).append(stats)
	_measure = {}


## What the frame rate would be with nothing holding frames back (vsync, a compositor): each frame
## takes as long as the slower of its GPU work and its main-thread work. gpu_ms and cpu_ms are
## per-frame milliseconds from the same frames. An estimate, reported beside the measured fps.
static func uncapped_estimate(gpu_ms: Array, cpu_ms: Array) -> Dictionary:
	var n := mini(gpu_ms.size(), cpu_ms.size())
	if n == 0:
		return {}
	var gpu := 0.0
	var cpu := 0.0
	var bound: Array = []
	for i in n:
		gpu += float(gpu_ms[i])
		cpu += float(cpu_ms[i])
		bound.append(maxf(float(gpu_ms[i]), float(cpu_ms[i])) / 1000.0)
	var est := frame_stats(bound, "estimate")
	return {
		"gpu_ms_avg": snappedf(gpu / n, 0.01),
		"cpu_ms_avg": snappedf(cpu / n, 0.01),
		"bound_by": "gpu" if gpu >= cpu else "cpu",
		"est_uncapped_fps": est["avg_fps"],
		"est_uncapped_p1_low_fps": est["p1_low_fps"],
	}


## The share of frames that took one refresh interval (within 0.5 ms): near 1 means vsync set the
## pace and the measured fps is a ceiling, near 0 means frames were not held back.
static func paced_share(frames: Array, refresh_hz: float) -> float:
	if frames.is_empty() or refresh_hz <= 0.0:
		return 0.0
	var interval := 1.0 / refresh_hz
	var paced := 0
	for f: float in frames:
		if absf(f - interval) <= 0.0005:
			paced += 1
	return snappedf(float(paced) / frames.size(), 0.01)


func _on_physics_frame() -> void:
	if _physics_start_us < 0:
		_physics_start_us = Time.get_ticks_usec()


func _on_process_frame() -> void:
	var now := Time.get_ticks_usec()
	_frame_physics_us = now - _physics_start_us if _physics_start_us >= 0 else 0
	_physics_start_us = -1
	_process_start_us = now


func _on_frame_pre_draw() -> void:
	if _measure.is_empty() or _process_start_us < 0:
		return
	var main_us := _frame_physics_us + (Time.get_ticks_usec() - _process_start_us)
	var rid := get_viewport().get_viewport_rid()
	var render_cpu := RenderingServer.viewport_get_measured_render_time_cpu(rid) + RenderingServer.get_frame_setup_time_cpu()
	(_measure["cpu"] as Array).append(main_us / 1000.0 + render_cpu)
	(_measure["gpu"] as Array).append(RenderingServer.viewport_get_measured_render_time_gpu(rid))


## Average fps, the 1% low (fps over the slowest 1% of frames), the worst frame and the count of hitches.
static func frame_stats(frames: Array, label: String) -> Dictionary:
	if frames.is_empty():
		return {"label": label, "frames": 0}
	var sorted := frames.duplicate()
	sorted.sort()
	var total := 0.0
	for f: float in frames:
		total += f
	var avg_ms := total / frames.size() * 1000.0
	# 1% low: the average of the slowest 1% of frames (at least one frame).
	var slow_count := maxi(1, int(sorted.size() * 0.01))
	var slow_total := 0.0
	for i in slow_count:
		slow_total += float(sorted[sorted.size() - 1 - i])
	var p1_low: float = slow_total / slow_count
	var worst: float = sorted[sorted.size() - 1]
	# Hitches: frames over 50 ms (under 20 fps for that frame), the lag spikes a player feels.
	var hitches := 0
	for f: float in frames:
		if f > 0.05:
			hitches += 1
	return {
		"label": label,
		"frames": frames.size(),
		"seconds": snappedf(total, 0.01),
		"avg_fps": snappedf(frames.size() / maxf(total, 0.0001), 0.1),
		"frame_ms_avg": snappedf(avg_ms, 0.01),
		"p1_low_fps": snappedf(1.0 / maxf(p1_low, 0.0001), 0.1),
		"min_fps": snappedf(1.0 / maxf(worst, 0.0001), 0.1),
		"hitches_over_50ms": hitches,
	}


## tools/bot_run.sh watches this file: when it stops changing, the game has stalled.
func _write_heartbeat() -> void:
	var f := FileAccess.open(out_dir.path_join("heartbeat.json"), FileAccess.WRITE)
	if f == null:
		return
	var beat := {"clock": snappedf(_clock, 0.01), "next_step": _next, "steps": steps.size()}
	beat["frames_drawn"] = Engine.get_frames_drawn()
	beat["waiting_level"] = _waiting_level
	f.store_string(JSON.stringify(beat))
	f.close()


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
	if _meter != null and is_instance_valid(_meter):
		report["move"] = _meter.results()
		var m := FileAccess.open("res://logs/score_move.json", FileAccess.WRITE)
		if m != null:
			m.store_string(JSON.stringify(report["move"], "  "))
			m.close()
	var f := FileAccess.open(out_dir.path_join("report.json"), FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(report, "  "))
		f.close()
	get_tree().quit(0 if _errors.is_empty() else 1)
