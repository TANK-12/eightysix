extends Node3D
## A bare level for tests: the "mech" field and the flat ground_height a real map has (lane A5's squad tests).

var mech: RigidBody3D


func ground_height(_x: float, _z: float) -> float:
	return 0.0


func capture_mouse() -> void:
	pass
