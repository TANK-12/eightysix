class_name MechBuilder
extends RefCounted
## Builds a mech from data/mechs.json and data/parts.json: a RigidBody3D running the controller
## script named by the entry ("controller": "standin" -> scripts/mech/standin_mech.gd), one fitted
## collider per chassis-mounted part (no whole-mech capsule), leg segments with hitboxes that follow
## the legs, and mass, centre of mass and inertia summed from every part and actuator.

const LAYER_WORLD := 1
const LAYER_MECH := 2
const LAYER_HITBOX := 4
const LAYER_DEBRIS := 16


static func controller_path(def: Dictionary) -> String:
	return "res://scripts/mech/%s_mech.gd" % str(def.get("controller", "standin"))


static func can_build(mech_id: String) -> bool:
	if not Registry.has_entry("mechs", mech_id):
		return false
	var def := Registry.entry("mechs", mech_id)
	return str(def.get("status", "")) != "planned" and ResourceLoader.exists(controller_path(def))


## Rest-stance foot position for a leg in the body frame.
static func rest_foot(def: Dictionary, hip: Vector3) -> Vector3:
	var stance: Dictionary = def.get("stance", {})
	var out := float(stance.get("foot_out_m", 1.0))
	var fwd := float(stance.get("foot_forward_m", 0.0))
	return Vector3(hip.x + signf(hip.x) * out, -float(stance.get("height_m", 2.0)), hip.z + signf(hip.z) * fwd)


static func knee_pole(hip: Vector3) -> Vector3:
	return Vector3(signf(hip.x), 1.4, 0.0)


## Every mass-carrying piece of the mech at its rest stance, for MechMass.sum().
static func mass_pieces(def: Dictionary) -> Array:
	var pieces: Array = []
	for placement: Dictionary in def.get("parts", []):
		var part := Registry.entry("parts", str(placement["part"]))
		pieces.append(
			{"mass": float(part.get("mass_kg", 0.0)), "position": _vec(placement.get("at", [0, 0, 0])), "size": _collider_size(part)}
		)
	for leg_name: String in def.get("legs", {}):
		var leg: Dictionary = def["legs"][leg_name]
		var hip := _vec(leg["hip"])
		var upper := Registry.entry("parts", str(leg["upper"]))
		var lower := Registry.entry("parts", str(leg["lower"]))
		var foot_part := Registry.entry("parts", str(leg["foot"]))
		var foot := rest_foot(def, hip)
		var knee := LegIK.knee(hip, foot, float(upper["length_m"]), float(lower["length_m"]), knee_pole(hip))
		var seg_a := LegIK.segment(hip, knee)
		var seg_b := LegIK.segment(knee, foot)
		pieces.append({"mass": float(upper["mass_kg"]), "position": seg_a.origin, "size": _collider_size(upper), "basis": seg_a.basis})
		pieces.append({"mass": float(lower["mass_kg"]), "position": seg_b.origin, "size": _collider_size(lower), "basis": seg_b.basis})
		pieces.append({"mass": float(foot_part["mass_kg"]), "position": foot, "size": _collider_size(foot_part)})
		for act_id: String in leg.get("actuators", []):
			var act := Registry.entry("parts", act_id)
			var at := knee if str(act.get("joint", "")) == "knee" else hip
			pieces.append({"mass": float(act.get("mass_kg", 0.0)), "position": at})
	return pieces


static func actuators_of(def: Dictionary) -> Array:
	var out: Array = []
	for leg_name: String in def.get("legs", {}):
		for act_id: String in def["legs"][leg_name].get("actuators", []):
			var act := Registry.entry("parts", act_id)
			act["id"] = act_id
			out.append(act)
	return out


static func build(mech_id: String) -> RigidBody3D:
	if not can_build(mech_id):
		push_error("MechBuilder: '%s' cannot be built (missing, planned or no controller)" % mech_id)
		return null
	var def := Registry.entry("mechs", mech_id)
	var body := RigidBody3D.new()
	body.set_script(load(controller_path(def)))
	body.name = "Mech_" + mech_id
	body.collision_layer = LAYER_MECH
	body.collision_mask = LAYER_WORLD | LAYER_MECH | LAYER_DEBRIS
	body.can_sleep = false
	body.continuous_cd = true

	for placement: Dictionary in def.get("parts", []):
		var part_id := str(placement["part"])
		var part := Registry.entry("parts", part_id)
		var at := _vec(placement.get("at", [0, 0, 0]))
		var shape := _make_shape(part)
		if shape != null:
			var cs := CollisionShape3D.new()
			cs.shape = shape
			cs.position = at
			cs.name = "Collider_" + str(placement.get("socket", part_id))
			cs.set_meta("part_id", part_id)
			body.add_child(cs)
		body.add_child(_make_mesh(part, Transform3D(Basis.IDENTITY, at), "Mesh_" + str(placement.get("socket", part_id))))

	var hitboxes := Area3D.new()
	hitboxes.name = "LegHitboxes"
	hitboxes.collision_layer = LAYER_HITBOX
	hitboxes.collision_mask = 0
	hitboxes.monitoring = false
	body.add_child(hitboxes)
	var legs: Array = []
	for leg_name: String in def.get("legs", {}):
		var leg_def: Dictionary = def["legs"][leg_name]
		var leg := {
			"name": leg_name,
			"hip": _vec(leg_def["hip"]),
			"upper_len": float(Registry.entry("parts", str(leg_def["upper"]))["length_m"]),
			"lower_len": float(Registry.entry("parts", str(leg_def["lower"]))["length_m"]),
		}
		for seg: String in ["upper", "lower", "foot"]:
			var part_id := str(leg_def[seg])
			var part := Registry.entry("parts", part_id)
			var mesh := _make_mesh(part, Transform3D.IDENTITY, "Leg_%s_%s" % [leg_name, seg])
			body.add_child(mesh)
			var cs := CollisionShape3D.new()
			cs.shape = _make_shape(part)
			cs.name = "Hitbox_%s_%s" % [leg_name, seg]
			cs.set_meta("part_id", part_id)
			hitboxes.add_child(cs)
			leg[seg + "_mesh"] = mesh
			leg[seg + "_hitbox"] = cs
		legs.append(leg)

	var info := MechMass.sum(mass_pieces(def))
	body.mass = float(info["mass"])
	body.center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	body.center_of_mass = info["com"]
	body.inertia = info["inertia"]
	body.set_meta("mech_id", mech_id)
	body.call("setup", mech_id, def, legs, info, actuators_of(def))
	return body


static func _make_shape(part: Dictionary) -> Shape3D:
	var collider: Variant = part.get("collider")
	if not collider is Dictionary:
		return null
	match str((collider as Dictionary).get("shape", "box")):
		"box":
			var box := BoxShape3D.new()
			box.size = _vec((collider as Dictionary).get("size", [1, 1, 1]))
			return box
	return null


static func _make_mesh(part: Dictionary, xf: Transform3D, name: String) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.name = name
	mi.transform = xf
	var box := BoxMesh.new()
	box.size = _collider_size(part)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(str(part.get("look", {}).get("color", "#5d6670")))
	mat.metallic = 0.55
	mat.roughness = 0.5
	box.material = mat
	mi.mesh = box
	return mi


static func _collider_size(part: Dictionary) -> Vector3:
	var collider: Variant = part.get("collider")
	if collider is Dictionary:
		return _vec((collider as Dictionary).get("size", [0, 0, 0]))
	return Vector3.ZERO


static func _vec(a: Variant) -> Vector3:
	var arr: Array = a
	return Vector3(float(arr[0]), float(arr[1]), float(arr[2]))
