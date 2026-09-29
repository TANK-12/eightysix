extends "res://tests/lib/test_case.gd"
## Every script in scripts/ compiles.


func test_all_scripts_compile() -> void:
	var dirs := ["res://scripts"]
	var count := 0
	while not dirs.is_empty():
		var dir: String = dirs.pop_back()
		for sub in DirAccess.get_directories_at(dir):
			dirs.append(dir.path_join(sub))
		for f in DirAccess.get_files_at(dir):
			if f.ends_with(".gd"):
				var script: GDScript = load(dir.path_join(f))
				assert_true(script != null and script.can_instantiate(), dir.path_join(f))
				count += 1
	assert_gt(count, 15)
