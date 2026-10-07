extends "res://tests/lib/test_case.gd"
## Your music folder (lane A7, QUICKSTART item 10a): a folder of your own mp3/ogg/wav files plays when a
## context picks "Your music folder", and stands in for Soundtrack in a copy without the soundtrack.

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
	for key: String in [Music.FOLDER_KEY, "audio.music_explore"]:
		_saved[key] = Settings.get_value(key)


func after_each() -> void:
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
	assert_true(Music.plays_folder("folder", 45))
	assert_true(Music.plays_folder("ost", 0), "a copy with no soundtrack plays your folder for Soundtrack")
	assert_false(Music.plays_folder("ost", 45), "with the soundtrack there, Soundtrack plays it")
	assert_false(Music.plays_folder("shuffle", 0))


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
