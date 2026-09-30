class_name MechClimb
extends Node
## Ledge climbing (lane A3): walking into a ledge the legs can reach (between min_ledge_m and
## max_ledge_m above the feet, tuning "climb") makes the Juggernaut haul itself up it, the way the
## anime's Juggernauts scramble over rubble: a lift towards climb_m_s until the chassis is over the
## top, then a push over the lip. The ledge is found with two rays, one forward at knee height for
## the face and one down from above for the top; it only counts when the face is steep and the top
## is flat enough to stand on, so a slope the legs can simply walk up never triggers it. Once a
## climb starts it holds (the feet leave the ground as it hauls) until the chassis is up and over
## the top, the stick lets go, or max_s runs out.

var mech: RigidBody3D
var climbing := false
var ledge_top := Vector3.ZERO
var _c: Dictionary = {}
var _held_s := 0.0


func _ready() -> void:
	mech = get_parent().get_parent() as RigidBody3D
	_c = Registry.tune("climb", {})


## The ledge ahead as {"top": Vector3, "height": metres above the feet}, or {}.
func find_ledge() -> Dictionary:
	var xf := mech.global_transform
	var fwd := -xf.basis.z
	fwd.y = 0.0
	if fwd.length() < 0.1:
		return {}
	fwd = fwd.normalized()
	var height := float(mech.get("def").get("stance", {}).get("height_m", 1.4))
	var feet_y := xf.origin.y - height
	var space := mech.get_world_3d().direct_space_state
	var from := Vector3(xf.origin.x, feet_y + float(_c.get("probe_height_m", 0.6)), xf.origin.z)
	var face := space.intersect_ray(PhysicsRayQueryParameters3D.create(from, from + fwd * float(_c.get("probe_m", 4.5)), 1, [mech.get_rid()]))
	if face.is_empty() or absf((face["normal"] as Vector3).y) > 0.6:
		return {}
	var max_h := float(_c.get("max_ledge_m", 4.2))
	var over: Vector3 = (face["position"] as Vector3) + fwd * float(_c.get("top_depth_m", 1.2))
	var top_q := PhysicsRayQueryParameters3D.create(Vector3(over.x, feet_y + max_h + 0.5, over.z), Vector3(over.x, feet_y, over.z), 1, [mech.get_rid()])
	var top := space.intersect_ray(top_q)
	if top.is_empty() or (top["normal"] as Vector3).y < 0.7:
		return {}
	var h := (top["position"] as Vector3).y - feet_y
	if h < float(_c.get("min_ledge_m", 0.9)) or h > max_h:
		return {}
	return {"top": top["position"], "height": h}


func _physics_process(delta: float) -> void:
	_tick(delta)
	if "hauling" in mech:
		mech.set("hauling", climbing)


func _tick(delta: float) -> void:
	if mech == null or not mech.get("is_player") or Game.is_paused() or Controls.stick("move").y < 0.5:
		climbing = false
		return
	if climbing:
		_held_s += delta
		if over_top(ledge_top) or _held_s > float(_c.get("max_s", 3.0)):
			climbing = false
			return
	else:
		if int(mech.get("grounded_legs")) < 1:
			return
		var ledge := find_ledge()
		if ledge.is_empty():
			return
		climbing = true
		_held_s = 0.0
		ledge_top = ledge["top"]
	climb_force(ledge_top)


func lowest_foot_y() -> float:
	var low := INF
	for leg: Dictionary in mech.get("legs"):
		var f: Variant = leg.get("foot")
		if f is Vector3:
			low = minf(low, (f as Vector3).y)
	return low if low < INF else mech.global_position.y - float(mech.get("def").get("stance", {}).get("height_m", 1.4))


## True once the chassis stands at the ledge's height and has reached the point above the top.
func over_top(top: Vector3) -> bool:
	var height := float(mech.get("def").get("stance", {}).get("height_m", 1.4))
	var fwd := -mech.global_transform.basis.z
	fwd.y = 0.0
	var past := (mech.global_position - top).dot(fwd.normalized()) > -0.3
	return mech.global_position.y > top.y + height * 0.8 and past


## One tick of the haul up and over `top` (split out so tests and AI can drive it without input).
func climb_force(top: Vector3) -> void:
	var height := float(mech.get("def").get("stance", {}).get("height_m", 1.4))
	var v := mech.linear_velocity
	var fwd := -mech.global_transform.basis.z
	fwd.y = 0.0
	fwd = fwd.normalized()
	var accel := float(_c.get("accel_m_s2", 16.0))
	var acc := Vector3.ZERO
	# Lift until the lowest foot clears the lip (dangling legs hang lower than the stance height).
	var clear := lowest_foot_y() >= top.y + float(_c.get("foot_clear_m", 0.25))
	if not clear or mech.global_position.y < top.y + height * 0.9:
		acc.y = clampf((float(_c.get("climb_m_s", 3.0)) - v.y) * 8.0, 0.0, accel)
	# Leans into the face while hauling, then drives over the lip once the feet are clear of it.
	var push := accel if clear else accel * 0.25
	acc += fwd * clampf((float(_c.get("push_m_s", 3.0)) - v.dot(fwd)) * 4.0, 0.0, push)
	mech.apply_central_force(acc * mech.mass)
