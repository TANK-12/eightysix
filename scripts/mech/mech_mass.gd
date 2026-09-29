class_name MechMass
extends RefCounted
## A mech's mass, centre of mass and principal inertia, summed from its parts (physics supplement,
## point 2: the mass comes from the parts, never a typed-in total). Each piece is a solid box
## (or a point mass when its size is zero) at a position and rotation in the body frame.


## pieces: [{"mass": kg, "position": Vector3, "size": Vector3 (optional), "basis": Basis (optional)}]
## Returns {"mass": kg, "com": Vector3, "inertia": Vector3 (diagonal about the centre of mass)}.
static func sum(pieces: Array) -> Dictionary:
	var total := 0.0
	var moment := Vector3.ZERO
	for p: Dictionary in pieces:
		total += float(p["mass"])
		moment += (p["position"] as Vector3) * float(p["mass"])
	if total <= 0.0:
		return {"mass": 0.0, "com": Vector3.ZERO, "inertia": Vector3.ZERO}
	var com := moment / total
	var tensor := [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
	for p: Dictionary in pieces:
		var m := float(p["mass"])
		var s: Vector3 = p.get("size", Vector3.ZERO)
		var b: Basis = p.get("basis", Basis.IDENTITY)
		var local := box_inertia(m, s)
		var d: Vector3 = (p["position"] as Vector3) - com
		for i in 3:
			for j in 3:
				var rotated := 0.0
				for k in 3:
					rotated += b[k][i] * local[k] * b[k][j]
				var parallel := m * ((d.length_squared() if i == j else 0.0) - d[i] * d[j])
				tensor[i][j] += rotated + parallel
	return {"mass": total, "com": com, "inertia": Vector3(tensor[0][0], tensor[1][1], tensor[2][2])}


## Principal inertia of a solid box of `size` metres.
static func box_inertia(mass: float, size: Vector3) -> Vector3:
	return (
		Vector3(
			size.y * size.y + size.z * size.z,
			size.x * size.x + size.z * size.z,
			size.x * size.x + size.y * size.y
		)
		* (mass / 12.0)
	)
