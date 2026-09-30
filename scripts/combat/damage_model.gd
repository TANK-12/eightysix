class_name DamageModel
extends RefCounted
## Per-part damage for one mech, from data/parts.json ("health", "armour_mm", "kind"). Keys are the
## same "damage_key" MechBuilder puts on every collider: the placement's socket or part id for chassis
## parts, "leg_<leg>_<segment>" for leg parts (the stand-in's four legs share one part id, so the id
## alone would not tell them apart). A hit lands on the part whose collider it struck: a round that
## penetrates the part's armour does its full damage, one that does not does "ricochet_fraction" of
## it. A part at 0 health is lost; an "armour" part that is lost comes off (the mech hides its panel,
## flings a copy and stops colliding there, so the internals behind take the next hits). A leg's
## health is its weakest segment; it limps as that falls. Losing a cockpit part or two legs destroys
## the mech. With permanent damage off, parts repair after "repair_delay_s" without a hit.

signal part_damaged(key: String, fraction: float)
signal part_lost(key: String)
signal part_restored(key: String)
signal destroyed

const DETACHABLE := ["armour"]
const CRITICAL := ["cockpit"]

var parts: Dictionary = {}  # key -> {"part", "kind", "label", "max", "hp", "armour_mm", "lost", "leg", "at"}
var legs: Dictionary = {}  # leg name -> [keys]
var is_destroyed := false
var _t: Dictionary = {}
var _since_hit := 0.0


func _init(def: Dictionary, tuning: Dictionary = {}) -> void:
	_t = tuning
	for placement: Dictionary in def.get("parts", []):
		var part_id := str(placement["part"])
		_add(str(placement.get("socket", part_id)), part_id, "", placement.get("at", [0, 0, 0]))
	for leg_name: String in def.get("legs", {}):
		var leg: Dictionary = def["legs"][leg_name]
		var keys: Array = []
		for seg: String in ["upper", "lower", "foot"]:
			var key := leg_key(leg_name, seg)
			_add(key, str(leg[seg]), leg_name, leg.get("hip", [0, 0, 0]))
			keys.append(key)
		legs[leg_name] = keys


static func leg_key(leg_name: String, seg: String) -> String:
	return "leg_%s_%s" % [leg_name, seg]


func _add(key: String, part_id: String, leg_name: String, at: Variant) -> void:
	if not Registry.has_entry("parts", part_id):
		return
	var p := Registry.entry("parts", part_id)
	var hp := float(p.get("health", 0))
	if hp <= 0.0:
		return
	var a: Array = at
	parts[key] = {
		"part": part_id,
		"kind": str(p.get("kind", "")),
		"label": str(p.get("label", part_id)),
		"max": hp,
		"hp": hp,
		"armour_mm": float(p.get("armour_mm", 0.0)),
		"lost": false,
		"leg": leg_name,
		"at": Vector3(float(a[0]), float(a[1]), float(a[2])),
		"size": _size_of(p),
	}


static func _size_of(p: Dictionary) -> Vector3:
	var c: Variant = p.get("collider")
	if c is Dictionary and (c as Dictionary).has("size"):
		var s: Array = (c as Dictionary)["size"]
		return Vector3(float(s[0]), float(s[1]), float(s[2]))
	return Vector3.ZERO


func has(key: String) -> bool:
	return parts.has(key)


func fraction(key: String) -> float:
	if not parts.has(key):
		return 1.0
	var p: Dictionary = parts[key]
	return float(p["hp"]) / float(p["max"])


func is_lost(key: String) -> bool:
	return parts.has(key) and bool(parts[key]["lost"])


func detachable(key: String) -> bool:
	return parts.has(key) and str(parts[key]["kind"]) in DETACHABLE


## Applies one hit; returns {"key", "dealt", "penetrated", "lost"} ("dealt" 0 for an unknown key).
func hit(key: String, damage: float, penetration_mm: float) -> Dictionary:
	var out := {"key": key, "dealt": 0.0, "penetrated": false, "lost": false}
	if not parts.has(key) or is_destroyed:
		return out
	_since_hit = 0.0
	var p: Dictionary = parts[key]
	var pen := penetration_mm >= float(p["armour_mm"])
	var dealt := damage * (1.0 if pen else float(_t.get("ricochet_fraction", 0.15)))
	dealt = minf(dealt, float(p["hp"]))
	p["hp"] = float(p["hp"]) - dealt
	out["dealt"] = dealt
	out["penetrated"] = pen
	part_damaged.emit(key, fraction(key))
	if float(p["hp"]) <= 0.0 and not bool(p["lost"]):
		p["lost"] = true
		out["lost"] = true
		part_lost.emit(key)
		_check_destroyed()
	return out


## A leg's health, 0 to 1: its weakest segment.
func leg_health(leg_name: String) -> float:
	var h := 1.0
	for key: String in legs.get(leg_name, []):
		h = minf(h, fraction(key))
	return h


func legs_lost() -> int:
	var n := 0
	for leg_name: String in legs:
		if leg_health(leg_name) <= 0.0:
			n += 1
	return n


## Whole-mech health, 0 to 1, weighted by each part's maximum.
func total_fraction() -> float:
	var hp := 0.0
	var top := 0.0
	for p: Dictionary in parts.values():
		hp += float(p["hp"])
		top += float(p["max"])
	return hp / top if top > 0.0 else 1.0


func _check_destroyed() -> void:
	if is_destroyed:
		return
	var dead := legs_lost() >= int(_t.get("legs_lost_to_destroy", 2))
	for p: Dictionary in parts.values():
		if str(p["kind"]) in CRITICAL and bool(p["lost"]):
			dead = true
	if dead:
		is_destroyed = true
		destroyed.emit()


## Repairs over time when damage is not permanent: after repair_delay_s without a hit every part
## regains repair_per_s of its maximum each second; a lost part comes back once it is whole again.
func tick(dt: float, permanent: bool) -> void:
	_since_hit += dt
	if permanent or is_destroyed or _since_hit < float(_t.get("repair_delay_s", 8.0)):
		return
	var rate := float(_t.get("repair_per_s", 0.05))
	for key: String in parts:
		var p: Dictionary = parts[key]
		if float(p["hp"]) >= float(p["max"]):
			continue
		p["hp"] = minf(float(p["hp"]) + float(p["max"]) * rate * dt, float(p["max"]))
		part_damaged.emit(key, fraction(key))
		if bool(p["lost"]) and float(p["hp"]) >= float(p["max"]):
			p["lost"] = false
			part_restored.emit(key)
