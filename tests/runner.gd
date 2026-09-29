extends Node
## Runs every tests/test_*.gd (each test_* method), prints the results and writes
## logs/tests-last.json for the hub page. Exit code 0 when everything passed.
## Run: tools/run_tests.sh [filter]   (headless, no window)

const TEST_DIR := "res://tests"


func _ready() -> void:
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
			failed += 1
			continue
		var methods: Array = []
		for m: Dictionary in script.get_script_method_list():
			var n := str(m["name"])
			if n.begins_with("test_") and n not in methods and (filter == "" or (file + ":" + n).contains(filter)):
				methods.append(n)
		if methods.is_empty():
			continue
		var suite: RefCounted = script.new()
		suite.set("tree", get_tree())
		await suite.call("before_all")
		for n: String in methods:
			suite.set("failures", PackedStringArray())
			await suite.call("before_each")
			await suite.call(n)
			await suite.call("after_each")
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
