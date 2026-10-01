extends Node
## Runs every tests/test_*.gd (each test_* method), prints the results and writes
## logs/tests-last.json for the hub page. Exit code 0 when everything passed.
## Run: tools/run_tests.sh [filter]   (headless, no window)

const TEST_DIR := "res://tests"


func _ready() -> void:
	# lane B4 part 3: a test run must never write Emerson's own settings, key bindings or soundtrack place
	# (a full run on 2026-10-01 overwrote his settings.cfg). Everything a test saves goes to test_* files.
	Settings.save_path = "user://test_settings.cfg"
	Controls.save_path = "user://test_bindings.cfg"
	Music.position_file = "user://test_music.cfg"
	await get_tree().process_frame
	var filter := ""
	for arg in OS.get_cmdline_user_args():
		if not arg.begins_with("--"):
			filter = arg
	var started := Time.get_ticks_msec()
	var results: Array = []
	var passed := 0
	var failed := 0
	var files := Array(DirAccess.get_files_at(TEST_DIR)).filter(
		func(f: String) -> bool: return f.begins_with("test_") and f.ends_with(".gd")
	)
	files.sort()
	for file: String in files:
		var script: GDScript = load(TEST_DIR.path_join(file))
		if script == null or not script.can_instantiate():
			results.append({"name": file, "ok": false, "message": "does not compile"})
			print("  FAIL  ", file, "  does not compile")
			failed += 1
			continue
		var methods: Array = []
		for m: Dictionary in script.get_script_method_list():
			var n := str(m["name"])
			if n.begins_with("test_") and n not in methods and (filter == "" or (file + ":" + n).contains(filter)):
				methods.append(n)
		if methods.is_empty():
			continue
		var before := _state()
		var suite: RefCounted = script.new()
		suite.set("tree", get_tree())
		await suite.call("before_all")
		for n: String in methods:
			suite.set("failures", PackedStringArray())
			var at_start := get_tree().root.get_children()
			await suite.call("before_each")
			await suite.call(n)
			await suite.call("after_each")
			await _sweep(at_start)
			var fails: PackedStringArray = suite.get("failures")
			var ok := fails.is_empty()
			var name := "%s:%s" % [file, n]
			results.append({"name": name, "ok": ok, "message": "; ".join(fails)})
			if ok:
				passed += 1
				print("  ok    ", name)
			else:
				failed += 1
				print("  FAIL  ", name, "  ", "; ".join(fails))
		await suite.call("after_all")
		var left := _left_behind(before, _state())
		if not left.is_empty():
			print("  LEFT  ", file, " left behind: ", "; ".join(left))
	var seconds := (Time.get_ticks_msec() - started) / 1000.0
	print("\n%d passed, %d failed in %.1f s" % [passed, failed, seconds])
	if filter == "":
		var report := {
			"when": Time.get_datetime_string_from_system(),
			"passed": passed,
			"failed": failed,
			"seconds": snappedf(seconds, 0.1),
			"tests": results,
		}
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://logs"))
		var f := FileAccess.open("res://logs/tests-last.json", FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(report, "  "))
			f.close()
	get_tree().quit(0 if failed == 0 else 1)


## Frees what a test left under the root (shells, casings, debris, decals, particles) and lets go
## of the input actions it left held, so the next test starts on the same empty world. Before
## this, a sleeping debris body left at the origin sat where the next test built its mech and made
## test_grapple's ledge climb and test_legion fail only in the full run.
func _sweep(at_start: Array[Node]) -> void:
	for n: Node in get_tree().root.get_children():
		if n not in at_start and n != self:
			n.queue_free()
	for a: StringName in InputMap.get_actions():
		if Input.is_action_pressed(a):
			Input.action_release(a)
	await get_tree().process_frame


## What one test file can leave for the next: nodes under the root, input actions still held,
## a changed time scale or physics rate. A test that passes alone and fails in the full run is
## usually reading one of these.
func _state() -> Dictionary:
	var nodes := PackedStringArray()
	for n: Node in get_tree().root.get_children():
		nodes.append("%s (%s)" % [n.name, n.get_class()])
	var held := PackedStringArray()
	for a: StringName in InputMap.get_actions():
		if not str(a).begins_with("ui_") and Input.is_action_pressed(a):
			held.append(str(a))
	return {
		"nodes": nodes,
		"held": held,
		"time_scale": Engine.time_scale,
		"tps": Engine.physics_ticks_per_second,
	}


func _left_behind(before: Dictionary, after: Dictionary) -> PackedStringArray:
	var out := PackedStringArray()
	for key: String in ["nodes", "held"]:
		for item: String in after[key]:
			if item not in before[key]:
				out.append("%s %s" % ["node" if key == "nodes" else "held action", item])
	for key: String in ["time_scale", "tps"]:
		if after[key] != before[key]:
			out.append("%s %s -> %s" % [key, before[key], after[key]])
	return out
