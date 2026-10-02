extends "res://tests/lib/test_case.gd"
## Emerson's note 20 (2026-10-02): a zoom scope on the mouse wheel to spot the Legion far off. The wheel steps
## 1x / 3x / 6x / 10x; zoomed, the view looks down the 57 mm's bore at the cockpit field of view / the step.

var ground: StaticBody3D
var mech: RigidBody3D
var cam: Camera3D


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 2, 400)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	mech = MechBuilder.build("juggernaut_m2")
	mech.set("is_player", false)
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)
	cam = Camera3D.new()
	cam.set_script(load("res://scripts/camera/chase_camera.gd"))
	tree.root.add_child(cam)
	cam.call("follow", mech)
	cam.set("view", "third")
	await physics_frames(30)


func after_each() -> void:
	cam.free()
	mech.free()
	ground.free()


func _press(action: String) -> void:
	var ev := InputEventAction.new()
	ev.action = action
	ev.pressed = true
	cam.call("_unhandled_input", ev)
	cam.call("_process", 1.0 / 60.0)


func test_the_wheel_steps_the_magnification() -> void:
	assert_eq(float(cam.call("zoom")), 1.0, "no optics to start")
	var cockpit_fov := Settings.get_f("gameplay.fov_cockpit")
	_press("optics_zoom_in")
	assert_eq(float(cam.call("zoom")), 3.0, "one notch: 3x")
	assert_almost_eq(cam.fov, cockpit_fov / 3.0, 0.01, "a third of the cockpit field of view")
	for i in 5:
		_press("optics_zoom_in")
	assert_eq(float(cam.call("zoom")), 10.0, "it stops at 10x")
	_press("optics_zoom_out")
	assert_eq(float(cam.call("zoom")), 6.0, "back one notch: 6x")


func test_the_optics_look_down_the_bore() -> void:
	_press("optics_zoom_in")
	var bore: Vector3 = mech.get_node("Combat").call("gun_direction")
	assert_gt((-cam.global_basis.z).dot(bore), 0.9999, "the middle of the view is where the gun points")


func test_middle_mouse_flips_in_and_out_at_the_last_step() -> void:
	_press("optics_zoom_in")
	_press("optics_zoom_in")
	_press("zoom_optics")
	assert_eq(float(cam.call("zoom")), 1.0, "out of the optics")
	assert_almost_eq(cam.fov, Settings.get_f("gameplay.fov_third"), 0.01, "back to the chase camera's view")
	_press("zoom_optics")
	assert_eq(float(cam.call("zoom")), 6.0, "and straight back in at 6x")
