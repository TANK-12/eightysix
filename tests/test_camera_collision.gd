extends "res://tests/lib/test_case.gd"
## Emerson's note 18 (2026-10-02): the third-person camera often went into the ground. With a hill rising behind
## the Juggernaut, or the mech backed against a wall, the camera ends up in open air, never inside the solid.

var world: Node3D
var mech: RigidBody3D
var cam: Camera3D


func _box(size: Vector3, at: Vector3, tilt_deg: float = 0.0) -> void:
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	body.add_child(cs)
	world.add_child(body)
	body.global_position = at
	body.rotation.x = deg_to_rad(tilt_deg)


func _setup() -> void:
	world = Node3D.new()
	tree.root.add_child(world)
	_box(Vector3(300, 2, 300), Vector3(0, -1, 0))
	mech = MechBuilder.build("juggernaut_m2")
	mech.set("is_player", false)
	world.add_child(mech)
	mech.global_position = Vector3(0, 3.2, 0)
	cam = Camera3D.new()
	cam.set_script(load("res://scripts/camera/chase_camera.gd"))
	world.add_child(cam)
	cam.call("follow", mech)
	cam.set("view", "third")


func after_each() -> void:
	world.free()


## Whether the camera is inside any solid, or closer to one than the near plane can bear.
func _buried() -> bool:
	var probe := PhysicsShapeQueryParameters3D.new()
	var ball := SphereShape3D.new()
	ball.radius = 0.15
	probe.shape = ball
	probe.transform = Transform3D(Basis.IDENTITY, cam.global_position)
	probe.collision_mask = 1
	return not world.get_world_3d().direct_space_state.intersect_shape(probe, 1).is_empty()


func _worst(frames: int) -> int:
	var bad := 0
	for i in frames:
		await physics_frames(1)
		cam.call("_process", 1.0 / 120.0)
		if _buried():
			bad += 1
	return bad


func test_a_hill_rising_behind_the_mech() -> void:
	await _setup()
	# A 30 degree slope whose face starts about 3 m behind the mech and climbs past the camera's height.
	_box(Vector3(60, 2, 60), Vector3(0, 14, 29), -30.0)
	assert_eq(await _worst(240), 0, "the camera never sits inside the hill")


func test_backed_against_a_wall() -> void:
	await _setup()
	# The wall's face 3.5 m behind the mech's centre, inside the camera's 6 m keep-clear distance.
	_box(Vector3(60, 30, 2), Vector3(0, 15, 4.5))
	assert_eq(await _worst(240), 0, "the camera never sits inside the wall")
	assert_lt(cam.global_position.z, 3.5, "it stays on the mech's side of the wall")


func test_open_ground_keeps_the_usual_distance() -> void:
	await _setup()
	await _worst(240)
	var d := cam.global_position.distance_to(mech.global_position)
	assert_gt(d, 8.0, "with nothing in the way it trails at its set distance (%.1f m)" % d)


## Relay 38 (Emerson after 015, "the camera keeps slipping through the floor"): with the mech rolled onto its
## side or its back and the aim pitched down, the look point drops into the ground; the camera still stays out.
func _rolled(roll: Basis) -> int:
	await _setup()
	mech.freeze = true
	mech.global_transform = Transform3D(roll, Vector3(0, 1.6, 0))
	Settings.set_value("controls.mouse_mode", "camera", false)
	var bad := 0
	for pitch: float in [-30.0, 0.0, 60.0]:
		mech.set("look_pitch_deg", pitch)
		cam.set("_orbit", Vector2(0, -0.5))
		bad += await _worst(60)
	Settings.reset_all_quietly()
	return bad


func test_mech_on_its_side_aiming_down() -> void:
	assert_eq(await _rolled(Basis(Vector3.BACK, PI * 0.5)), 0, "the camera never goes into the ground")


func test_mech_on_its_back_aiming_down() -> void:
	assert_eq(await _rolled(Basis(Vector3.BACK, PI)), 0, "the camera never goes into the ground")
