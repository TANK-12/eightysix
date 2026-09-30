extends "res://tests/lib/test_case.gd"
## Photo / inspect mode (Emerson, PLAN "Raising the bar"): from the field, time freezes, the HUD
## hides and a free camera orbits the player's Juggernaut; zoom and pan stay within their limits;
## closing gives back the game camera, the HUD and time.


class FakeLevel:
	extends Node3D
	var mech: RigidBody3D
	var camera: Camera3D
	var hud: CanvasLayer


var level: FakeLevel
var before: Node


func before_each() -> void:
	level = FakeLevel.new()
	tree.root.add_child(level)
	level.mech = MechBuilder.build("juggernaut_m2")
	level.mech.position = Vector3(0, 400, 0)
	level.add_child(level.mech)
	level.camera = Camera3D.new()
	level.add_child(level.camera)
	level.camera.position = Vector3(0, 405, 12)
	level.camera.make_current()
	level.hud = CanvasLayer.new()
	level.add_child(level.hud)
	before = Game.level
	Game.level = level


func after_each() -> void:
	if Game.is_photo():
		Game.close_photo()
	Game.level = before
	tree.paused = false
	level.free()


func test_opens_frozen_with_the_hud_hidden_and_closes_back() -> void:
	await physics_frames(2)
	Game.open_photo()
	await tree.process_frame
	assert_true(Game.is_photo(), "photo mode is open")
	assert_true(tree.paused, "time is frozen")
	assert_false(level.hud.visible, "the HUD is hidden")
	var cam := tree.root.get_viewport().get_camera_3d()
	assert_eq(str(cam.name), "PhotoCamera", "the photo camera is the one drawing")
	var y := level.mech.global_position.y
	await physics_frames(30)
	assert_almost_eq(level.mech.global_position.y, y, 0.001, "the mech does not fall while frozen")
	Game.close_photo()
	await tree.process_frame
	assert_false(tree.paused, "time runs again")
	assert_true(level.hud.visible, "the HUD is back")
	assert_eq(tree.root.get_viewport().get_camera_3d(), level.camera, "the game camera is back")


func test_orbit_zoom_and_pan_stay_in_limits() -> void:
	Game.open_photo()
	await tree.process_frame
	var photo: PhotoMode = Game.get("_photo")
	var f := photo.focus_point()
	var d0 := photo.camera.global_position.distance_to(f)
	var p0 := photo.camera.global_position
	photo.orbit(1.2, -0.3)
	assert_almost_eq(photo.camera.global_position.distance_to(f), d0, 0.01, "orbiting keeps the distance (nothing in the way)")
	assert_gt(photo.camera.global_position.distance_to(p0), 5.0, "and moves the camera round")
	assert_lt(photo.camera.global_transform.basis.z.dot((photo.camera.global_position - f).normalized()), 1.01, "looking at the mech")
	for i in 40:
		photo.zoom(0.8)
	assert_almost_eq(photo.distance, 5.0, 0.001, "zoom in stops at photo.min_distance_m")
	for i in 40:
		photo.zoom(1.3)
	assert_almost_eq(photo.distance, 40.0, 0.001, "zoom out stops at photo.max_distance_m")
	photo.pan(100.0, 100.0)
	assert_almost_eq(photo.focus_offset.length(), 25.0, 0.01, "the focus stays within 25 m of the mech")
	photo.orbit(0.0, -10.0)
	assert_almost_eq(rad_to_deg(photo.pitch), -80.0, 0.01, "pitch stops above the mech")
	assert_true(PhotoMode.photo_path().begins_with(PhotoMode.photo_dir()), "photos go to Pictures/Eighty Six")
	assert_true(PhotoMode.photo_path().ends_with(".png"))


func test_camera_stops_at_the_ground() -> void:
	var ground := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 2, 200)
	cs.shape = box
	ground.add_child(cs)
	ground.position = level.mech.global_position + Vector3(0, -3, 0)
	level.add_child(ground)
	await physics_frames(2)
	Game.open_photo()
	await tree.process_frame
	var photo: PhotoMode = Game.get("_photo")
	photo.orbit(0.0, 10.0)  # swing the camera down under the mech
	assert_gt(photo.camera.global_position.y, ground.position.y + 1.0, "kept above the ground (y %.1f)" % photo.camera.global_position.y)
