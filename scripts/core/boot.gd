extends Node
## First scene. Hands over to the main menu, or straight to a map when started with
## "-- --map=<id>" (handy from the editor and for quick checks). Bot runs pick their own start.


func _ready() -> void:
	if Bot.active:
		if Bot.steps.is_empty() or str(Bot.report.get("script", "")) == "":
			return
		var parsed: Variant = Bot.parse_script(FileAccess.get_file_as_string(Bot.script_path))
		if parsed is Dictionary and str((parsed as Dictionary).get("map", "")) != "":
			return
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--map="):
			Game.start_map.call_deferred(arg.substr(6))
			return
	Game.goto_main_menu.call_deferred()
