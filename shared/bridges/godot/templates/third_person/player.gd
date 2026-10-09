extends CharacterBody3D
## Third-person player: WASD moves relative to the camera, the mouse orbits
## the Phantom Camera, Space jumps, Esc frees the mouse. The AnimationTree
## blends idle -> jog by speed. The body is a VRoid model (CC0) and the clips
## come from Quaternius's Universal Animation Library (CC0), both retargeted
## on import to Godot's humanoid skeleton (%GeneralSkeleton), so any other
## humanoid .vrm dropped in as Body/Character plays the same clips; the
## library's other clips (Sprint, Jump_Start, Roll, Sword_Attack...) are there
## as "ual/<name>". FORGE_DEMO_WALK=1 walks in a circle without input, for
## recorded checks.

@export var speed := 5.0
@export var jump_velocity := 4.5
@export var mouse_sensitivity := 0.003

@onready var pcam = $"../PlayerCamera"
@onready var body: Node3D = $Body
@onready var anim_tree: AnimationTree = $AnimationTree
@onready var anim_player: AnimationPlayer = $AnimationPlayer

const CLIPS := preload("res://characters/AnimationLibrary_Godot_Standard.gltf")

var _demo := OS.get_environment("FORGE_DEMO_WALK") == "1"
var _time := 0.0


func _ready() -> void:
	# The clips live inside the imported animation file; lend its library to
	# this player (the tracks name %GeneralSkeleton bones, so they fit).
	var clips := CLIPS.instantiate()
	anim_player.add_animation_library("ual", clips.get_node("AnimationPlayer").get_animation_library(""))
	clips.free()
	# The spring arm exists only after the camera's own _ready, so defer.
	pcam.set_third_person_rotation.call_deferred(Vector3(-0.35, 0, 0))
	if not _demo:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		var rot: Vector3 = pcam.get_third_person_rotation()
		rot.y -= event.relative.x * mouse_sensitivity
		rot.x = clampf(rot.x - event.relative.y * mouse_sensitivity, -1.2, 0.4)
		pcam.set_third_person_rotation(rot)
	elif event is InputEventKey and event.pressed and event.physical_keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _input_dir() -> Vector2:
	if _demo:
		return Vector2(cos(_time), sin(_time))
	var dir := Vector2.ZERO
	dir.x = float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))
	dir.y = float(Input.is_physical_key_pressed(KEY_S)) - float(Input.is_physical_key_pressed(KEY_W))
	return dir.limit_length(1.0)


func _physics_process(delta: float) -> void:
	_time += delta
	if not is_on_floor():
		velocity += get_gravity() * delta
	elif Input.is_physical_key_pressed(KEY_SPACE):
		velocity.y = jump_velocity

	var input := _input_dir()
	var yaw: float = pcam.get_third_person_rotation().y
	var move := Vector3(input.x, 0, input.y).rotated(Vector3.UP, yaw)
	if move.length() > 0.01:
		velocity.x = move.x * speed
		velocity.z = move.z * speed
		body.rotation.y = lerp_angle(body.rotation.y, atan2(-move.x, -move.z), 10 * delta)
	else:
		velocity.x = move_toward(velocity.x, 0, speed)
		velocity.z = move_toward(velocity.z, 0, speed)
	move_and_slide()

	var ground_speed := Vector2(velocity.x, velocity.z).length()
	anim_tree.set("parameters/blend_position", clampf(ground_speed / speed, 0.0, 1.0))
