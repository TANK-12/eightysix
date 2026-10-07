extends Node
## The music player (lane B4 part 2). Plays tracks from data/music.json (files in assets/audio/86/,
## git-ignored and skipped by Godot's import and export) on the Music bus: one for the menus, one while exploring, one in combat, each
## picked in Settings > Audio > Music (Soundtrack, a track, Shuffle or Off). Combat starts when a gun or a
## hit sounds near the listener and ends after COMBAT_HOLD_S of quiet. Changes crossfade over FADE_S.
## Soundtrack (the default, lane B4 part 3) plays the music.json "ost" set through in album order and
## carries on where it left off, across contexts and across launches (position_file).
## Your music folder (lane A7, for friends' copies that ship without the soundtrack): any mp3, ogg or wav in
## the folder set in Settings > Audio > Music plays shuffled when a context picks "Your music folder", and
## stands in for Soundtrack when the soundtrack files are missing. Its tracks have ids "folder:<file name>".

const FADE_S := 2.5
const COMBAT_HOLD_S := 25.0
const COMBAT_NEAR_M := 400.0
const SETTING := {"menu": "audio.music_menu", "explore": "audio.music_explore", "combat": "audio.music_combat"}
const FOLDER_KEY := "audio.music_folder"
const FOLDER_PREFIX := "folder:"
const FOLDER_EXTENSIONS := ["mp3", "ogg", "wav"]

var context := "menu"
var position_file := "user://music.cfg"  # where Soundtrack remembers its place (tests point it elsewhere)
var track := ""  # music.json id now playing, "" for none
var _players: Array[AudioStreamPlayer] = []
var _live := 0
var _fade := 1.0
var _combat_t := 0.0
var _streams := {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for i in 2:
		var p := AudioStreamPlayer.new()
		p.bus = "Music"
		p.volume_db = -80.0
		p.finished.connect(_on_finished.bind(p))
		add_child(p)
		_players.append(p)
	Settings.changed.connect(_on_setting_changed)
	Sfx.sounded.connect(_on_sounded)
	get_tree().scene_changed.connect(_on_scene_changed)
	_on_scene_changed.call_deferred()


## Tracks that may play in `ctx`, after the language filter; missing files are left out.
func candidates(ctx: String) -> PackedStringArray:
	var lang := Settings.get_s("audio.music_language") if Settings.has_key("audio.music_language") else "any"
	var out := PackedStringArray()
	for id in Registry.ids("music"):
		var e := Registry.entry("music", id)
		if not ctx in e.get("use", []) or not _shown(e):
			continue
		if lang != "any" and str(e.get("language", "none")) not in [lang, "none"]:
			continue
		if FileAccess.file_exists(path_of(id)):
			out.append(id)
	return out


## The music folder from the settings ("~" expanded), or "" when none is set or it is gone.
func folder() -> String:
	var path := Settings.get_s(FOLDER_KEY) if Settings.has_key(FOLDER_KEY) else ""
	if path.begins_with("~"):
		path = OS.get_environment("HOME") + path.substr(1)
	return path if path != "" and DirAccess.dir_exists_absolute(path) else ""


## Every playable file in the music folder as "folder:<file name>", sorted; empty without a folder.
func folder_tracks() -> PackedStringArray:
	var out := PackedStringArray()
	var dir := folder()
	if dir == "":
		return out
	for f in DirAccess.get_files_at(dir):
		if f.get_extension().to_lower() in FOLDER_EXTENSIONS:
			out.append(FOLDER_PREFIX + f)
	out.sort()
	return out


## The track's file on disk. A relative path is looked for in the project folder (a run from the editor or
## the project), then beside an exported game, then in ~/Games/eightysix (an exported version run from build/).
func path_of(id: String) -> String:
	if id.begins_with(FOLDER_PREFIX):
		return folder().path_join(id.substr(FOLDER_PREFIX.length()))
	var p := str(Registry.entry("music", id).get("path", ""))
	if p.begins_with("~"):
		return OS.get_environment("HOME") + p.substr(1)
	if p.is_absolute_path() or p.is_empty():
		return p
	var tries := [
		ProjectSettings.globalize_path("res://" + p),
		OS.get_executable_path().get_base_dir().path_join(p),
		OS.get_environment("HOME").path_join("Games/eightysix").path_join(p),
	]
	for t: String in tries:
		if FileAccess.file_exists(t):
			return t
	return tries[0]


## The soundtrack album in order: the "ost" set by "order", missing files left out.
func album() -> PackedStringArray:
	var out := PackedStringArray()
	for id in Registry.ids("music"):
		if str(Registry.entry("music", id).get("set", "")) == "ost" and FileAccess.file_exists(path_of(id)):
			out.append(id)
	return out


## The album track after `id` (wrapping round); after the saved place when `id` is not on the album.
func album_next(id: String) -> String:
	var tracks := album()
	if tracks.is_empty():
		return ""
	var at := tracks.find(id)
	if at < 0:
		var cfg := ConfigFile.new()
		cfg.load(position_file)
		at = tracks.find(str(cfg.get_value("ost", "last", "")))
	return tracks[(at + 1) % tracks.size()]


func _want(ctx: String) -> String:
	var want := Settings.get_s(SETTING[ctx]) if Settings.has_key(SETTING[ctx]) else "ost"
	if want not in ["ost", "shuffle", "off", "folder"] and (not Registry.has_entry("music", want) or not _shown(Registry.entry("music", want))):
		return "ost"  # a hidden extra (or a track no longer listed) falls back to the soundtrack
	return want


func _shown(e: Dictionary) -> bool:
	return not e.has("show_if") or Settings.get_b(str(e["show_if"]))


## Whether a context set to `want` plays the music folder: when picked, or for Soundtrack when the
## soundtrack is missing (`album_size` 0, a friend's copy).
static func plays_folder(want: String, album_size: int) -> bool:
	return want == "folder" or (want == "ost" and album_size == 0)


## The track `ctx` wants now: the next soundtrack track, the chosen one, a shuffled one, or "" for silence.
func choose(ctx: String) -> String:
	var want := _want(ctx)
	if want == "off":
		return ""
	if plays_folder(want, album().size()):
		var mine := folder_tracks()
		if not mine.is_empty():
			if mine.size() > 1 and track in mine:
				mine.remove_at(mine.find(track))
			return mine[randi() % mine.size()]
		if want == "folder":
			return album_next(track)  # no folder (or an empty one): the soundtrack instead
	if want == "ost":
		return album_next(track)
	if want != "shuffle" and FileAccess.file_exists(path_of(want)):
		return want
	var pool := candidates(ctx)
	if pool.is_empty():
		return ""
	if pool.size() > 1 and track in pool:
		pool.remove_at(pool.find(track))
	return pool[randi() % pool.size()]


func set_context(ctx: String) -> void:
	if ctx == context and track != "":
		return
	var carry_on := (_want(ctx) == "ost" and track in album()) or (_want(ctx) == "folder" and track.begins_with(FOLDER_PREFIX))
	context = ctx
	if not carry_on:  # the soundtrack just keeps playing from menu to field to combat
		play(choose(ctx))


func skip() -> void:
	play(choose(context))


## Crossfades to `id` ("" fades to silence).
func play(id: String) -> void:
	track = id
	if id != "" and str(_entry(id).get("set", "")) == "ost":
		var cfg := ConfigFile.new()
		cfg.set_value("ost", "last", id)
		cfg.save(position_file)
	var next := _players[1 - _live]
	next.stop()
	if id != "":
		var stream := _load(id)
		if stream == null:
			track = ""
		else:
			next.stream = stream
			next.volume_db = -80.0
			next.play()
	_live = 1 - _live
	_fade = 0.0


func _load(id: String) -> AudioStream:
	if not _streams.has(id):
		var path := path_of(id)
		var s: AudioStream = null
		match path.get_extension().to_lower():
			"mp3":
				s = AudioStreamMP3.load_from_file(path)
			"ogg":
				s = AudioStreamOggVorbis.load_from_file(path)
			"wav":
				s = AudioStreamWAV.load_from_file(path)
		_streams[id] = s
	return _streams[id]


func _process(delta: float) -> void:
	if _fade < 1.0:
		_fade = minf(_fade + delta / FADE_S, 1.0)
		var level := float(_entry(track).get("volume_db", 0.0)) if track != "" else 0.0
		_players[_live].volume_db = linear_to_db(maxf(_fade, 0.0001)) + level
		_players[1 - _live].volume_db = linear_to_db(maxf(1.0 - _fade, 0.0001))
		if _fade >= 1.0:
			_players[1 - _live].stop()
	if context == "combat":
		_combat_t -= delta
		if _combat_t <= 0.0:
			set_context("explore")


func _on_finished(p: AudioStreamPlayer) -> void:
	if p == _players[_live]:
		skip()


func _on_sounded(_event: String, bus: String, distance_m: float) -> void:
	if context == "menu" or bus not in ["weapons", "impacts"] or distance_m > COMBAT_NEAR_M:
		return
	_combat_t = COMBAT_HOLD_S
	set_context("combat")


func _on_scene_changed() -> void:
	var scene := get_tree().current_scene
	var in_menu := scene == null or scene.scene_file_path.contains("/ui/")
	set_context("menu" if in_menu else "explore")


## The music.json entry for `id`; a folder track has none.
func _entry(id: String) -> Dictionary:
	return {} if id.begins_with(FOLDER_PREFIX) else Registry.entry("music", id)


func _on_setting_changed(key: String, _value: Variant) -> void:
	if key == FOLDER_KEY and plays_folder(_want(context), album().size()):
		play(choose(context))
		return
	if key == SETTING.get(context, "") or key in ["audio.music_language", "audio.music_extras"]:
		if not (_want(context) == "ost" and track in album()):
			play(choose(context))
