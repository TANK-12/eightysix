class_name MechBuilder
extends RefCounted
## Builds a mech from data/mechs.json and data/parts.json: a RigidBody3D running the controller
## script named by the entry ("controller": "standin" -> scripts/mech/standin_mech.gd), one fitted
## collider per chassis-mounted part (no whole-mech capsule), leg segments with hitboxes that follow
## the legs, and mass, centre of mass and inertia summed from every part and actuator.
##
## A part's "collider" is a box ({"shape": "box", "size": [...]}) or the model's own convex hulls
## ({"shape": "hulls", "hulls_from": "<export part name>", "size": [...]}): read from the mech's
## "model_data" export json (B1's parts[].hulls, one or more convex pieces per part, model space)
## and moved into the body frame by the mech's "model_origin". "size" stays the box used for
## inertia, the placeholder mesh, and the fallback when the export is not synced.
##
## Every collider and leg hitbox carries a "damage_key" meta (DamageModel's key for the part it
## belongs to), and every mech gets a MechCombat child named "Combat" (gun, damage, wire anchors).

const LAYER_WORLD := 1
const LAYER_MECH := 2
const LAYER_HITBOX := 4
const LAYER_DEBRIS := 16
## The foot's box and mesh sit this far above the leg's IK end point (the sole).
const FOOT_RAISE := Vector3(0, 0.1, 0)

static var _hull_cache: Dictionary = {}


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


## Where a leg's sole rests in the body frame: the leg's own "sole" (the model's sole socket) when
## the entry has one, otherwise the stance's generic foot placement.
static func leg_sole(def: Dictionary, leg_def: Dictionary) -> Vector3:
	if leg_def.has("sole"):
		return _vec(leg_def["sole"])
	return rest_foot(def, _vec(leg_def["hip"]))


static func knee_pole(hip: Vector3) -> Vector3:
	return Vector3(signf(hip.x), 1.4, 0.0)


## A leg's geometry in the body frame. "hip" carries the spring (the physics). The IK chain runs from
## "pivot" (the real hip-pitch joint when the entry has one) through the knee, which bends towards
## "pole" (the modelled knee when the entry has one), to its end at "sole_rest" + "end_offset" (the
## real ankle when the entry has one). With the real joints the thigh, shin and foot stay joined as
## the leg moves; the stand-in has none and keeps its generic chain.
static func leg_geometry(def: Dictionary, leg_def: Dictionary) -> Dictionary:
	var hip := _vec(leg_def["hip"])
	var pivot := _vec(leg_def["pivot"]) if leg_def.has("pivot") else hip
	var sole := leg_sole(def, leg_def)
	return {
		"hip": hip,
		"pivot": pivot,
		"sole_rest": sole,
		"end_offset": (_vec(leg_def["ankle"]) - sole) if leg_def.has("ankle") else FOOT_RAISE,
		"pole": (_vec(leg_def["knee"]) - pivot) if leg_def.has("knee") else knee_pole(hip),
		"upper_len": float(Registry.entry("parts", str(leg_def["upper"]))["length_m"]),
		"lower_len": float(Registry.entry("parts", str(leg_def["lower"]))["length_m"]),
	}


## A leg's rest pose (the frames its meshes and hitboxes follow; a hull is stored relative to these).
static func rest_segments(geom: Dictionary) -> Dictionary:
	return pose_segments(geom, (geom["sole_rest"] as Vector3) + (geom["end_offset"] as Vector3), Basis.IDENTITY)


## A leg's segment frames for an IK end point (body frame): upper and lower rolled into the leg's
## bend plane, and the foot frame at the end, tilted by `tilt`. `scale` lengthens thigh and shin.
static func pose_segments(geom: Dictionary, end: Vector3, tilt: Basis, scale: float = 1.0, swivel: float = 0.0) -> Dictionary:
	var pivot: Vector3 = geom["pivot"]
	var upper := float(geom["upper_len"]) * scale
	var lower := float(geom["lower_len"]) * scale
	var reach := LegIK.reachable(pivot, end, upper, lower)
	var pole := LegIK.swivelled(pivot, reach, geom["pole"], swivel)
	var knee := LegIK.knee(pivot, reach, upper, lower, pole)
	var line := (reach - pivot).normalized()
	var bend := (knee - pivot) - line * (knee - pivot).dot(line)
	# A straight leg's knee sits on the hip-ankle line, so its bend is zero and the segments' roll
	# fell back to world up (the thigh and shin meshes twisted apart at the knee): keep the roll from
	# the knee's pole instead.
	if bend.length() < 0.05:
		bend = pole - line * pole.dot(line)
	return {
		"knee": knee,
		"end": reach,
		"upper": LegIK.segment(pivot, knee, bend),
		"lower": LegIK.segment(knee, reach, bend),
		"foot": Transform3D(tilt, reach),
	}


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
		var geom := leg_geometry(def, leg)
		var hip: Vector3 = geom["hip"]
		var upper := Registry.entry("parts", str(leg["upper"]))
		var lower := Registry.entry("parts", str(leg["lower"]))
		var foot_part := Registry.entry("parts", str(leg["foot"]))
		var foot: Vector3 = geom["sole_rest"]
		var rest := rest_segments(geom)
		var seg_a: Transform3D = rest["upper"]
		var seg_b: Transform3D = rest["lower"]
		var knee: Vector3 = rest["knee"]
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
	body.contact_monitor = true
	body.max_contacts_reported = 8
	var hulls := model_hulls(def)

	for placement: Dictionary in def.get("parts", []):
		var part_id := str(placement["part"])
		var part := Registry.entry("parts", part_id)
		var at := _vec(placement.get("at", [0, 0, 0]))
		var label := str(placement.get("socket", part_id))
		var shapes := make_shapes(part, hulls, Transform3D(Basis.IDENTITY, at))
		for i in shapes.size():
			var cs := CollisionShape3D.new()
			cs.shape = shapes[i]
			cs.position = at
			cs.name = "Collider_" + label + ("" if i == 0 else "_%d" % (i + 1))
			cs.set_meta("part_id", part_id)
			cs.set_meta("damage_key", label)
			body.add_child(cs)
		body.add_child(_make_mesh(part, Transform3D(Basis.IDENTITY, at), "Mesh_" + label))

	var hitboxes := Area3D.new()
	hitboxes.name = "LegHitboxes"
	hitboxes.collision_layer = LAYER_HITBOX
	hitboxes.collision_mask = 0
	hitboxes.monitoring = false
	body.add_child(hitboxes)
	var legs: Array = []
	for leg_name: String in def.get("legs", {}):
		var leg_def: Dictionary = def["legs"][leg_name]
		var leg := leg_geometry(def, leg_def)
		leg["name"] = leg_name
		var rest := rest_segments(leg)
		for seg: String in ["upper", "lower", "foot"]:
			var part_id := str(leg_def[seg])
			var part := Registry.entry("parts", part_id)
			var mesh := _make_mesh(part, Transform3D.IDENTITY, "Leg_%s_%s" % [leg_name, seg])
			body.add_child(mesh)
			var shapes := make_shapes(part, hulls, rest[seg])
			if shapes.is_empty():
				shapes = [null]
			var boxes: Array = []
			for i in shapes.size():
				var cs := CollisionShape3D.new()
				cs.shape = shapes[i]
				cs.name = "Hitbox_%s_%s" % [leg_name, seg] + ("" if i == 0 else "_%d" % (i + 1))
				cs.set_meta("part_id", part_id)
				cs.set_meta("damage_key", DamageModel.leg_key(leg_name, seg))
				hitboxes.add_child(cs)
				boxes.append(cs)
			leg[seg + "_mesh"] = mesh
			leg[seg + "_hitbox"] = boxes[0]
			leg[seg + "_hitboxes"] = boxes
		legs.append(leg)

	var info := MechMass.sum(mass_pieces(def))
	body.mass = float(info["mass"])
	body.center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	body.center_of_mass = info["com"]
	body.inertia = info["inertia"]
	body.set_meta("mech_id", mech_id)
	body.call("setup", mech_id, def, legs, info, actuators_of(def))
	var combat := MechCombat.new()
	combat.name = "Combat"
	body.add_child(combat)
	return body


## The export's convex hulls per part name, in the body frame (model space minus "model_origin").
## Empty when the mech has no export json, or it is not synced yet (colliders then fall back to boxes).
static func model_hulls(def: Dictionary) -> Dictionary:
	var path := str(def.get("model_data", ""))
	if path == "":
		return {}
	if not FileAccess.file_exists(path):
		push_warning("MechBuilder: %s not synced yet, colliders fall back to boxes" % path)
		return {}
	var origin := _vec(def.get("model_origin", [0, 0, 0]))
	var key := "%s@%s" % [path, origin]
	if _hull_cache.has(key):
		return _hull_cache[key]
	var out := {}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if data is Dictionary:
		for part: Dictionary in (data as Dictionary).get("parts", []):
			var pieces: Array = []
			for hull: Array in part.get("hulls", []):
				var pts := PackedVector3Array()
				for p: Array in hull:
					pts.append(Vector3(float(p[0]), float(p[1]), float(p[2])) - origin)
				pieces.append(pts)
			out[str(part.get("name", ""))] = pieces
	_hull_cache[key] = out
	return out


## A part's collision shapes, for a collider that sits at `frame` in the body at the rest pose:
## one ConvexPolygonShape3D per hull piece (points moved into that frame), or the part's box.
static func make_shapes(part: Dictionary, hulls: Dictionary, frame: Transform3D) -> Array:
	var collider: Variant = part.get("collider")
	if not collider is Dictionary:
		return []
	var c: Dictionary = collider
	var kind := str(c.get("shape", "box"))
	var from := str(c.get("hulls_from", ""))
	if kind == "hulls" and hulls.has(from) and not (hulls[from] as Array).is_empty():
		var inv := frame.affine_inverse()
		var out: Array = []
		for pts: PackedVector3Array in hulls[from]:
			var shape := ConvexPolygonShape3D.new()
			shape.points = inv * pts
			out.append(shape)
		return out
	if kind != "box" and kind != "hulls":
		return []
	var box := BoxShape3D.new()
	box.size = _vec(c.get("size", [1, 1, 1]))
	return [box]


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
