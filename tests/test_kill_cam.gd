extends "res://tests/lib/test_case.gd"
## Final-kill cam (lane A7): on a win the last wreck gets a slow-motion swing behind letterbox bars,
## the HUD hides, and afterwards time, camera and HUD come back and the end card opens. Skippable,
## and never leaves the game in slow motion if the level goes away mid-shot.

const RIG := preload("res://tests/lib/mission_rig.gd")
const KILL_CAM := preload("res://scripts/camera/kill_cam.gd")

var rig: RefCounted


func before_each() -> void:
	rig = RIG.new(tree)


func after_each() -> void:
	rig.free_all()
	AudioServer.playback_speed_scale = 1.0
	Settings.set_value("gameplay.kill_cam", Settings.default_of("gameplay.kill_cam"), false)


func _scene() -> Dictionary:
	var cam := Camera3D.new()
	rig.level.add_child(cam)
	cam.make_current()
	var hud := CanvasLayer.new()
	hud.layer = 10
	rig.level.add_child(hud)
	var wreck := Node3D.new()
	rig.level.add_child(wreck)
	wreck.global_position = Vector3(0, 0, -60)
	return {"cam": cam, "hud": hud, "wreck": wreck}


func test_slow_motion_swing_then_everything_back() -> void:
	var s := _scene()
	var kc: Node3D = KILL_CAM.new()
	rig.level.add_child(kc)
	var done: Array = []
	kc.connect("finished", func() -> void: done.append(true))
	kc.call("begin", s["wreck"], Vector3.ZERO, "Final kill  ·  Ameise  ·  60 m")
	assert_eq(Engine.time_scale, KILL_CAM.SLOW, "time slows to a quarter")
	assert_eq(tree.root.get_viewport().get_camera_3d(), kc.get("camera"), "the kill camera takes over")
	assert_false((s["hud"] as CanvasLayer).visible, "the HUD hides")
	await tree.process_frame
	var cam := kc.get("camera") as Camera3D
	var start := cam.global_position
	assert_between(start.distance_to((s["wreck"] as Node3D).global_position), 8.0, 20.0, "close to the wreck")
	assert_lt(start.z, -40.0, "on the player's side of it (the player is south)")
	for i in 200:
		await tree.process_frame
	assert_gt(cam.global_position.distance_to(start), 3.0, "it swings round")
	var to_wreck := ((s["wreck"] as Node3D).global_position - cam.global_position).normalized()
	assert_gt(-cam.global_transform.basis.z.dot(to_wreck), 0.95, "looking at the wreck")
	for i in 400:
		if not done.is_empty():
			break
		await tree.process_frame
	assert_eq(done, [true], "it ends by itself after %.1f real seconds" % KILL_CAM.DURATION_S)
	assert_eq(Engine.time_scale, 1.0, "time back to normal")
	assert_eq(AudioServer.playback_speed_scale, 1.0, "sound too")
	assert_eq(tree.root.get_viewport().get_camera_3d(), s["cam"], "the player's camera is back")
	assert_true((s["hud"] as CanvasLayer).visible, "and the HUD")


func test_skip_and_leaving_mid_shot() -> void:
	var s := _scene()
	var kc: Node3D = KILL_CAM.new()
	rig.level.add_child(kc)
	kc.call("begin", s["wreck"], Vector3.ZERO, "x")
	var skip := InputEventAction.new()
	skip.action = "ui_cancel"
	skip.pressed = true
	kc.call("_input", skip)
	assert_eq(Engine.time_scale, 1.0, "Escape skips it")
	assert_true((s["hud"] as CanvasLayer).visible)
	var kc2: Node3D = KILL_CAM.new()
	rig.level.add_child(kc2)
	kc2.call("begin", s["wreck"], Vector3.ZERO, "x")
	assert_eq(Engine.time_scale, KILL_CAM.SLOW)
	kc2.free()
	assert_eq(Engine.time_scale, 1.0, "a level freed mid-shot leaves no slow motion behind")


func test_a_won_mission_plays_it_before_the_end_card() -> void:
	var m: Mission = rig.mission([["ameise"]], 120.0)
	var hud := MissionHud.new()
	rig.level.add_child(hud)
	hud.watch(m)
	await physics_frames(10)
	rig.kill_as_player(m.units[0])
	await physics_frames(3)
	assert_eq(m.state, "won")
	assert_not_null(hud.kill_cam, "the kill cam starts on the win")
	assert_true(MissionHud.kill_caption(hud.get("_last_kill"), rig.level.mech.global_position).begins_with("Final kill  ·  Ameise  ·  "))
	assert_eq(hud.find_children("*", "MissionEnd", true, false).size(), 0, "no end card yet")
	for i in 520:
		if not is_instance_valid(hud.kill_cam):
			break
		await tree.process_frame
	assert_false(is_instance_valid(hud.kill_cam), "the kill cam finishes")
	var ends := hud.find_children("*", "", true, false).filter(func(n: Node) -> bool: return n is MissionEnd)
	assert_eq(ends.size(), 1, "then the end card")
	Settings.set_value("gameplay.kill_cam", false, false)


func test_off_goes_straight_to_the_end_card() -> void:
	Settings.set_value("gameplay.kill_cam", false, false)
	var m: Mission = rig.mission([["ameise"]], 120.0)
	var hud := MissionHud.new()
	rig.level.add_child(hud)
	hud.watch(m)
	await physics_frames(10)
	rig.kill_as_player(m.units[0])
	await physics_frames(3)
	assert_null_like(hud.kill_cam)
	assert_eq(Engine.time_scale, 1.0)


func assert_null_like(v: Variant) -> void:
	assert_true(v == null or not is_instance_valid(v), "no kill cam")
