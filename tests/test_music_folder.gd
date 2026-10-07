extends "res://tests/lib/test_case.gd"
## Your music folder (lane A7, QUICKSTART item 10a): a folder of your own mp3/ogg/wav files plays when a
## context picks "Your music folder", and stands in for Soundtrack in a copy without the soundtrack.
## A friend's copy (Relay 95, item 10b): Music.hide_sets stands in for a share zip without the 86 music; the
## free tracks play then, the folder beats them, and with nothing at all the game is silent without errors.

const NO_86 := ["ost", "song", "extra"]
const FREE := ["heartbreaking", "five_armies", "clash_defiant"]

const SCREEN := preload("res://scripts/ui/settings_screen.gd")

var _dir := ""
var _saved := {}


func before_each() -> void:
	_dir = ProjectSettings.globalize_path("user://test_music_folder")
	DirAccess.make_dir_recursive_absolute(_dir)
	var wav := AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.mix_rate = 22050
	var data := PackedByteArray()
	data.resize(22050)  # half a second of 16-bit silence
	wav.data = data
	wav.save_to_wav(_dir.path_join("my_track.wav"))
	wav.save_to_wav(_dir.path_join("another.wav"))
	var f := FileAccess.open(_dir.path_join("cover.txt"), FileAccess.WRITE)
	f.store_string("not music")
	f.close()
	for key: String in [Music.FOLDER_KEY, "audio.music_menu", "audio.music_explore", "audio.music_combat"]:
		_saved[key] = Settings.get_value(key)


func after_each() -> void:
	Music.hide_sets = PackedStringArray()
	for key: String in _saved:
		Settings.set_value(key, _saved[key], false)
	for f in DirAccess.get_files_at(_dir):
		DirAccess.remove_absolute(_dir.path_join(f))
	DirAccess.remove_absolute(_dir)


func test_folder_lists_only_music_files() -> void:
	Settings.set_value(Music.FOLDER_KEY, "", false)
	assert_eq(Music.folder_tracks().size(), 0, "no folder, no tracks")
	Settings.set_value(Music.FOLDER_KEY, _dir, false)
	assert_eq(Music.folder_tracks(), PackedStringArray(["folder:another.wav", "folder:my_track.wav"]), "the wavs, sorted, not the txt")
	assert_eq(Music.path_of("folder:my_track.wav"), _dir.path_join("my_track.wav"))
	Settings.set_value(Music.FOLDER_KEY, _dir.path_join("gone"), false)
	assert_eq(Music.folder(), "", "a folder that does not exist counts as none")


func test_your_music_plays_from_the_folder() -> void:
	Settings.set_value(Music.FOLDER_KEY, _dir, false)
	Settings.set_value("audio.music_explore", "folder", false)
	for i in 6:
		assert_true(Music.choose("explore").begins_with("folder:"), "Your music folder picks a folder track")
	var stream: AudioStream = Music._load("folder:my_track.wav")
	assert_not_null(stream, "a wav from the folder loads at run time")
	assert_almost_eq(stream.get_length(), 0.5, 0.05, "the whole file (11025 samples at 22050 Hz, 16-bit)")
	Settings.set_value(Music.FOLDER_KEY, "", false)
	assert_false(Music.choose("explore").begins_with("folder:"), "with no folder it falls back to the soundtrack")


func test_soundtrack_falls_back_to_the_folder_only_when_missing() -> void:
	assert_true(Music.plays_folder("folder", true))
	assert_true(Music.plays_folder("ost", false), "a copy with no soundtrack plays your folder for Soundtrack")
	assert_false(Music.plays_folder("ost", true), "with the soundtrack there, Soundtrack plays it")
	assert_false(Music.plays_folder("shuffle", false))


func test_settings_row_shows_folder_and_track_count() -> void:
	assert_eq(Settings.label_for(Music.FOLDER_KEY, ""), "None chosen")
	var home := OS.get_environment("HOME")
	assert_eq(Settings.label_for(Music.FOLDER_KEY, home.path_join("Music")), "~/Music")
	Settings.set_value(Music.FOLDER_KEY, _dir, false)
	var screen: Control = SCREEN.new()
	tree.root.add_child(screen)
	screen.show_page("audio", "music")
	await tree.process_frame
	assert_has(screen._rows, Music.FOLDER_KEY, "the folder row is on the music page")
	var row: Dictionary = screen._rows[Music.FOLDER_KEY]
	assert_true((row["control"] as Button).text.contains("test_music_folder"), "the button names the folder")
	assert_true((row["value"] as Label).text.contains("2 tracks"), "and the row counts its tracks")
	var options := Settings.options_for("audio.music_combat").map(func(o: Array) -> String: return str(o[0]))
	assert_has(options, "folder", "each music pick offers Your music folder")
	screen.queue_free()


func test_your_folder_carries_on_across_contexts() -> void:
	Music.hide_sets = PackedStringArray(NO_86)
	Settings.set_value(Music.FOLDER_KEY, _dir, false)
	for key: String in ["audio.music_menu", "audio.music_explore", "audio.music_combat"]:
		Settings.set_value(key, "ost", false)
	var was_ctx := Music.context
	Music.context = "menu"
	Music.play(Music.choose("menu"))
	var first := Music.track
	assert_true(first.begins_with("folder:"), "your folder stands in on the menu")
	for ctx: String in ["explore", "combat", "explore"]:
		Music.set_context(ctx)
		assert_eq(Music.track, first, "%s: the same song carries on" % ctx)
	Music.context = was_ctx
	Music.play("")


func test_a_broken_file_is_skipped() -> void:
	var f := FileAccess.open(_dir.path_join("broken.ogg"), FileAccess.WRITE)
	f.store_string("not really ogg vorbis")
	f.close()
	Music.hide_sets = PackedStringArray(NO_86)
	Settings.set_value(Music.FOLDER_KEY, _dir, false)
	Settings.set_value("audio.music_menu", "folder", false)
	var was_ctx := Music.context
	Music.context = "menu"
	Music.play("folder:broken.ogg")
	assert_has(["folder:another.wav", "folder:my_track.wav"], Music.track, "a good file plays instead")
	for i in 6:
		assert_ne(Music.choose("menu"), "folder:broken.ogg", "and the broken one is not picked again")
	Music._streams.erase("folder:broken.ogg")
	Music.context = was_ctx
	Music.play("")


func _option_ids(key: String) -> Array:
	return Settings.options_for(key).map(func(o: Array) -> String: return str(o[0]))


func test_friends_copy_plays_the_free_tracks() -> void:
	Settings.set_value("audio.music_combat", "eighty_six", false)  # picked before the soundtrack went
	Music.hide_sets = PackedStringArray(NO_86)
	Settings.set_value(Music.FOLDER_KEY, "", false)
	Settings.set_value("audio.music_menu", "ost", false)
	assert_false(Music.has_soundtrack(), "no 86 soundtrack in a share zip")
	assert_eq(Music.album(), PackedStringArray(FREE), "Soundtrack is the free tracks, in order")
	assert_has(FREE, Music.choose("menu"), "the menu plays a free track")
	var stream: AudioStream = Music._load("heartbreaking")
	assert_not_null(stream, "an imported free track loads from res:// (so it is in an exported pck)")
	assert_gt(stream.get_length(), 60.0, "the whole track")
	var offered := _option_ids("audio.music_combat")
	assert_false("eighty_six" in offered, "no 86 track names offered without their files")
	assert_has(offered, "clash_defiant", "the free tracks are offered")
	assert_eq(Music._want("combat"), "ost", "a saved 86 pick falls back to Soundtrack")
	assert_has(FREE, Music.choose("combat"), "and so plays a free track")


func test_the_folder_beats_the_free_tracks() -> void:
	Music.hide_sets = PackedStringArray(NO_86)
	Settings.set_value(Music.FOLDER_KEY, _dir, false)
	Settings.set_value("audio.music_explore", "ost", false)
	for i in 4:
		assert_true(Music.choose("explore").begins_with("folder:"), "your folder stands in for the soundtrack")


func test_with_the_soundtrack_the_free_tracks_stay_hidden() -> void:
	assert_true(Music.has_soundtrack(), "this machine has the 86 music (Emerson's copy)")
	assert_false("heartbreaking" in Music.album())
	assert_false("five_armies" in Music.candidates("explore"), "not in Shuffle")
	assert_false("clash_defiant" in _option_ids("audio.music_combat"), "not offered")


func test_no_music_at_all_is_silent() -> void:
	Settings.set_value(Music.FOLDER_KEY, "", false)
	for ctx: String in ["menu", "explore", "combat"]:
		for want: String in ["ost", "shuffle", "folder", "eighty_six"]:
			Music.hide_sets = PackedStringArray()
			Settings.set_value(Music.SETTING[ctx], want, false)  # set while the track still counts
			Music.hide_sets = PackedStringArray(NO_86 + ["free"])
			assert_eq(Music.choose(ctx), "", "%s set to %s: silence" % [ctx, want])
	var was := Music.track
	Music.play("")
	assert_eq(Music.track, "", "playing nothing is fine")
	Music.play(was)
