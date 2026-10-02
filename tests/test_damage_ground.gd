extends "res://tests/lib/test_case.gd"
## Emerson's note 17 (2026-10-02, high priority): the Juggernaut fell through the map when damaged. A damaged
## Juggernaut (armour shot off, a leg lost, both) stands 10 s on flat ground and on a 20 degree slope and its
## centre must stay above the ground the whole time.

var ground: StaticBody3D
var mech: RigidBody3D
var dm: DamageModel


func _setup(slope_deg: float) -> void:
	ground = StaticBody3D.new()
	# A thin triangle surface like the maps' terrain (a 2 m box hid the fall: a body pushed into it came back out).
	var cs := CollisionShape3D.new()
	var plane := ConcavePolygonShape3D.new()
	var a := Vector3(-100, 0, -100)
	var b := Vector3(100, 0, -100)
	var c := Vector3(100, 0, 100)
	var d := Vector3(-100, 0, 100)
	plane.set_faces(PackedVector3Array([a, b, c, a, c, d]))
	cs.shape = plane
	ground.add_child(cs)
	ground.rotation.x = deg_to_rad(slope_deg)
	tree.root.add_child(ground)
	mech = MechBuilder.build("juggernaut_m2")
	mech.set("is_player", false)
	mech.position = Vector3(0, 3.2, 0)
	tree.root.add_child(mech)
	dm = mech.get_node("Combat").get("damage")
	await physics_frames(120)


func after_each() -> void:
	if is_instance_valid(mech):
		mech.free()
	if is_instance_valid(ground):
		ground.free()


## Lowest height of the mech's centre above the ground plane over `seconds`.
func _lowest(seconds: float) -> float:
	var up := ground.global_basis.y
	var low := INF
	for i in int(seconds * 120.0):
		await physics_frames(1)
		low = minf(low, (mech.global_position - ground.global_position).dot(up))
	return low


func _lose_armour() -> int:
	var n := 0
	for key: String in dm.parts:
		if dm.detachable(key):
			dm.hit(key, 1e9, 1e9)
			n += 1
	return n


func _lose_leg(leg_name: String) -> void:
	for key: String in dm.legs[leg_name]:
		dm.hit(key, 1e9, 1e9)


func _case(slope_deg: float, armour: bool, leg: bool, label: String) -> void:
	await _setup(slope_deg)
	var start := (mech.global_position - ground.global_position).dot(ground.global_basis.y)
	if armour:
		assert_gt(_lose_armour(), 0, "%s: some armour came off" % label)
	if leg:
		_lose_leg(str(dm.legs.keys()[0]))
	assert_false(dm.is_destroyed, "%s: still alive (one leg lost is a limp, not a kill)" % label)
	var low := await _lowest(10.0)
	assert_gt(low, 1.2, "%s: it stays on its feet (started %.2f m, lowest %.2f m)" % [label, start, low])


func test_armour_off_on_flat_ground() -> void:
	for i in 4:
		seed(1000 + i)
		await _case(0.0, true, false, "armour off, flat, try %d" % i)
		after_each()


func test_a_leg_lost_on_flat_ground() -> void:
	await _case(0.0, false, true, "leg lost, flat")


func test_armour_and_a_leg_on_a_slope() -> void:
	await _case(20.0, true, true, "armour and leg, 20 deg slope")


## Destroyed (two legs gone) with its armour off: it drops onto what is left of its hull and stays on the ground.
func test_a_wreck_rests_on_the_ground() -> void:
	await _setup(0.0)
	_lose_armour()
	for leg_name: String in dm.legs.keys().slice(0, 2):
		_lose_leg(leg_name)
	assert_true(dm.is_destroyed, "two legs lost is a kill")
	var low := await _lowest(10.0)
	assert_gt(low, 0.2, "the wreck lies on the ground, not in it (lowest centre %.2f m)" % low)
