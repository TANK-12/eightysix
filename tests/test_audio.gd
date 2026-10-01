extends "res://tests/lib/test_case.gd"
## Sound (lane B4): every registered sound loads and has a bus, weapons and surfaces point at real
## sounds, Sfx plays 2D and 3D takes, far sounds arrive at the speed of sound, surfaces are told
## apart, and every mech gets its MechSounds with footsteps and gun sounds from its own signals.


func test_every_sound_loads_and_has_a_bus() -> void:
	var buses := {}
	for b: Dictionary in Registry.file("sounds")["buses"]:
		buses[str(b["id"])] = true
	var ids := Registry.ids("sounds")
	assert_gt(float(ids.size()), 20.0, "the synth set is registered")
	for id: String in ids:
		var e := Registry.entry("sounds", id)
		assert_true(buses.has(str(e["bus"])), id + " bus")
		for f: String in e["files"]:
			assert_true(load(f) is AudioStream, f)


func test_weapons_and_surfaces_point_at_real_sounds() -> void:
	var file := Registry.file("sounds")
	for wid: String in file["weapons"]:
		if wid.begins_with("_"):
			continue
		assert_true(Registry.has_entry("weapons", wid), "weapon " + wid)
		for k: String in file["weapons"][wid]:
			assert_true(Sfx.has(str(file["weapons"][wid][k])), wid + " " + k)
	for s: String in ["dirt", "rock", "metal"]:
		assert_true(Sfx.has(str(file["surfaces"][s]["impact"])), s + " impact")
		assert_true(Sfx.has(str(file["surfaces"][s]["foot"])), s + " foot")


func test_play_2d_and_3d_and_unknown() -> void:
	var before := Sfx.played
	assert_true(Sfx.play("ui_click") is AudioStreamPlayer, "ui is 2D")
	var cam := Camera3D.new()
	tree.root.add_child(cam)
	cam.make_current()
	var p := Sfx.play("foot_dirt", Vector3(3, 0, 0))
	assert_true(p is AudioStreamPlayer3D, "a footstep is placed in the world")
	assert_eq(Sfx.played, before + 2)
	assert_eq(Sfx.play("no_such_sound"), null)
	cam.free()


func test_far_gunfire_arrives_at_the_speed_of_sound() -> void:
	var cam := Camera3D.new()
	tree.root.add_child(cam)
	cam.make_current()
	var before := Sfx.played
	assert_eq(Sfx.play("gun_57mm_fire", Vector3(686, 0, 0)), null, "a shot 686 m away is not heard at once")
	await physics_frames(120 + 60)  # 1.5 s
	assert_eq(Sfx.played, before, "not yet after 1.5 s")
	await physics_frames(120)  # 2.5 s: sound takes 2.0 s over 686 m
	assert_eq(Sfx.played, before + 1, "heard after 2 s")
	cam.free()


func test_surfaces_are_told_apart() -> void:
	var ground := StaticBody3D.new()
	var wall := StaticBody3D.new()
	wall.set_meta("kit", "wall_4m")
	var piece := CollisionShape3D.new()
	wall.add_child(piece)
	var body := RigidBody3D.new()
	var mech := RigidBody3D.new()
	mech.add_to_group("mechs")
	assert_eq(Sfx.surface_of(ground), "dirt")
	assert_eq(Sfx.surface_of(piece), "rock", "a kit piece's shape counts as its kit")
	assert_eq(Sfx.surface_of(mech), "metal")
	assert_eq(Sfx.surface_of(body), "rock", "loose debris is not armour (a shell into it rang like a bell)")
	assert_eq(Sfx.surface_of(null), "dirt")
	ground.free()
	wall.free()
	body.free()
	mech.free()


func test_every_mech_gets_sounds_from_its_own_signals() -> void:
	var cam := Camera3D.new()
	tree.root.add_child(cam)
	cam.make_current()
	var mech := MechBuilder.build("juggernaut_m2")
	tree.root.add_child(mech)
	await physics_frames(3)
	assert_true(mech.has_node("MechSounds"), "Sfx attached MechSounds")
	var before := Sfx.played
	mech.emit_signal("stepped", "fl")
	assert_eq(Sfx.played, before + 1, "a step makes a footstep")
	var combat := mech.get_node_or_null("Combat")
	assert_not_null(combat, "the Juggernaut has its combat node")
	if combat != null:
		combat.emit_signal("fired", "gun_57mm", "apfsds")
		assert_eq(Sfx.played, before + 2, "the gun fires")
		await physics_frames(90)
		assert_eq(Sfx.played, before + 3, "and its casing lands 0.6 s later")
	mech.free()
	cam.free()


func test_a_fast_gun_keeps_to_its_voice_cap() -> void:
	var cam := Camera3D.new()
	tree.root.add_child(cam)
	cam.make_current()
	var cap := int(Registry.entry("sounds", "mg_12_7_fire")["max_voices"])
	var used := {}
	for i in 30:
		used[Sfx.play("mg_12_7_fire", Vector3(5, 0, 0))] = true
	assert_eq(used.size(), cap, "30 rounds in a burst share %d voices" % cap)
	cam.free()


func test_reverb_follows_the_listeners_zone() -> void:
	Sfx.clear_reverb_zones()
	for z: Dictionary in Registry.entry("maps", "small_map")["reverb_zones"]:
		var at: Array = z["at"]
		var sz: Array = z["size_m"]
		var size := Vector3(float(sz[0]), float(sz[1]), float(sz[2]))
		Sfx.add_reverb_zone(AABB(Vector3(float(at[0]) - size.x * 0.5, -20.0, float(at[1]) - size.z * 0.5), size), str(z["reverb"]), float(z["amount"]), int(z["priority"]))
	var town := Sfx.reverb_at(Vector3(10, 5, -170))
	var open_ground := Sfx.reverb_at(Vector3(-250, 5, 330))
	var outside := Sfx.reverb_at(Vector3(5000, 0, 0))
	assert_gt(float(town["wet"]), float(open_ground["wet"]), "the town rings more than the open valley")
	assert_lt(float(town["predelay_ms"]), float(open_ground["predelay_ms"]), "walls are closer than the valley sides")
	assert_eq(float(outside["wet"]), 0.0, "no zone, no reverb")
	assert_not_null(AudioMix.effects_reverb(), "the Effects bus has its reverb")
	Sfx.clear_reverb_zones()


# --- lane B4 part 2: Emerson's own mix, downloaded sounds, shell bangs, music --------------------


func test_every_sound_gets_a_level_and_a_pick_in_settings() -> void:
	for id: String in Registry.ids("sounds"):
		var e := Registry.entry("sounds", id)
		assert_true(Settings.has_key("audio.level." + id), id + " level slider")
		if e.get("choices", []).size() > 1:
			assert_true(Settings.has_key("audio.pick." + id), id + " pick")
			for c: Dictionary in e["choices"]:
				for f: String in c["files"]:
					assert_true(load(f) is AudioStream, f)


func test_pick_and_level_change_what_plays() -> void:
	var e := Registry.entry("sounds", "gun_57mm_fire")
	assert_gt(float(e.get("choices", []).size()), 3.0, "the gun has downloaded choices")
	var synth: Dictionary = e["choices"][0]
	Settings.set_value("audio.pick.gun_57mm_fire", synth["id"])
	assert_eq(Sfx.files_of("gun_57mm_fire"), synth["files"])
	Settings.set_value("audio.pick.gun_57mm_fire", "off")
	assert_eq(Sfx.play("gun_57mm_fire"), null, "Off plays nothing")
	Settings.set_value("audio.pick.gun_57mm_fire", str(e["choice"]))
	Settings.set_value("audio.level.ui_click", Settings.SOUND_LEVEL_OFF_DB)
	assert_eq(Sfx.play("ui_click"), null, "level all the way down is off")
	Settings.set_value("audio.level.ui_click", 6.0)
	var p := Sfx.play("ui_click") as AudioStreamPlayer
	assert_almost_eq(p.volume_db, float(Registry.entry("sounds", "ui_click").get("volume_db", 0.0)) + 6.0, 0.01)
	Settings.set_value("audio.level.ui_click", 0.0)


func test_a_heavy_shell_bangs_and_a_bullet_does_not() -> void:
	var cam := Camera3D.new()
	tree.root.add_child(cam)
	cam.make_current()
	Sfx.counts.clear()
	Sfx._on_impact({"point": Vector3(5, 0, 0), "projectile_kg": 1.2, "collider": null})
	assert_eq(int(Sfx.counts.get("shell_explode", 0)), 1, "57 mm hit goes off")
	Sfx._on_impact({"point": Vector3(5, 0, 0), "projectile_kg": 0.05, "collider": null})
	assert_eq(int(Sfx.counts.get("shell_explode", 0)), 1, "12.7 mm does not")
	assert_eq(int(Sfx.counts.get("impact_dirt", 0)), 2)
	cam.free()


func test_the_gun_is_the_loudest_thing_in_the_mix() -> void:
	var gun := float(Registry.entry("sounds", "gun_57mm_fire").get("volume_db", 0.0))
	for id: String in Registry.ids("sounds"):
		var e := Registry.entry("sounds", id)
		if e.get("loop", false) or e.get("2d", false) or id in ["gun_57mm_fire", "lowe_fire", "shell_explode"]:
			continue
		if true:
			assert_gt(gun, float(Registry.entry("sounds", id).get("volume_db", 0.0)), id + " under the 57 mm")


func test_the_servo_hum_is_off_until_picked() -> void:
	assert_eq(str(Registry.entry("sounds", "servo_loop").get("choice", "")), "off")
	assert_eq(Sfx.files_of("servo_loop"), [])


func test_music_follows_the_settings() -> void:
	Settings.set_value("audio.music_menu", "off")
	assert_eq(Music.choose("menu"), "")
	var pool := Music.candidates("combat")
	assert_gt(float(pool.size()), 0.0, "tracks are on disk for combat")
	Settings.set_value("audio.music_menu", "shuffle")
	assert_true(Music.choose("menu") in Music.candidates("menu"))
	Settings.set_value("audio.music_language", "en")
	for id in Music.candidates("menu"):
		assert_true(str(Registry.entry("music", id)["language"]) in ["en", "none"], id)
	Settings.set_value("audio.music_language", "any")
	Music.context = "explore"
	Music._on_sounded("gun_57mm_fire", "weapons", 900.0)
	assert_eq(Music.context, "explore", "a far gun does not start combat music")
	Music._on_sounded("gun_57mm_fire", "weapons", 10.0)
	assert_eq(Music.context, "combat", "a near gun does")


func test_a_placed_sound_is_not_capped_below_its_level() -> void:
	# Godot's AudioStreamPlayer3D.max_db (+3 dB by default) silently capped the 57 mm at +3
	var cam := Camera3D.new()
	tree.root.add_child(cam)
	cam.make_current()
	var p := Sfx.play("gun_57mm_fire", Vector3(3, 0, 0)) as AudioStreamPlayer3D
	assert_true(p != null)
	assert_gt(p.max_db, p.volume_db, "the player's ceiling is above the gun's level")
	cam.free()
