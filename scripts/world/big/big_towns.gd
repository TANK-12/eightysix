class_name BigTowns
extends RefCounted
## Lays out a streamed map's towns (lane B5) from their maps.json entry and a data/town_styles.json
## style: streets along the town's long side, kit buildings on lots either side facing the street,
## rubble and walls on some empty lots. Deterministic per town seed. Returns place specs the level
## builds with Kit.build: {"kit", "at": [x, z], "rot" (deg), "damage", "seed", "town"}.


static func layout(terrain: BigTerrain, town: Dictionary) -> Array:
	var style: Dictionary = Registry.entry("town_styles", str(town.get("style", "town")))
	var rng := RandomNumberGenerator.new()
	rng.seed = int(town.get("seed", 1)) * 7919
	var c := Vector2(float(town["center"][0]), float(town["center"][1]))
	var hs := Vector2(float(town["size_m"][0]), float(town["size_m"][1])) * 0.5
	var rot := deg_to_rad(float(town.get("rot", 0.0)))
	var u := Vector2(cos(rot), sin(rot))  # along the long side
	var v := Vector2(-u.y, u.x)
	var dmg: Array = town.get("damage", [0.2, 0.6])
	var kits: Dictionary = style.get("kits", {"ruin_house": 1})
	var extras: Dictionary = style.get("extras", {})
	var lot := float(style.get("lot_m", 18.0))
	var every := float(style.get("street_every_m", 64.0))
	var street_half := float(style.get("street_w_m", 12.0)) * 0.5
	var out: Array = []
	var taken: Array[Vector3] = []  # x, z, radius
	var streets := maxi(int(floor(hs.y * 2.0 / every)), 1)
	for si in streets:
		var sv := -hs.y + every * (si + 0.5)
		for side: float in [-1.0, 1.0]:
			var along := -hs.x + lot * 0.5
			while along <= hs.x - lot * 0.5:
				var kit := _pick(rng, kits)
				var fp: Array = Kit.entry(kit).get("footprint_m", [8, 8])
				var depth := float(fp[1])
				var off := sv + side * (street_half + depth * 0.5 + 1.0)
				var p := c + u * (along + rng.randf_range(-1.5, 1.5)) + v * off
				var r := maxf(float(fp[0]), float(fp[1])) * 0.6
				var facing := rad_to_deg(rot) + (0.0 if side > 0.0 else 180.0)
				if absf(off) + depth * 0.5 > hs.y or not _clear(terrain, p, r, taken):
					along += lot
					continue
				if rng.randf() < float(style.get("fill", 0.6)):
					out.append({"kit": kit, "at": [p.x, p.y], "rot": facing, "damage": rng.randf_range(float(dmg[0]), float(dmg[1])), "seed": rng.randi() % 100000, "town": str(town["id"])})
					taken.append(Vector3(p.x, p.y, r))
				else:
					for extra: String in extras:
						if rng.randf() < float(extras[extra]):
							out.append({"kit": extra, "at": [p.x, p.y], "rot": facing + rng.randf_range(-25.0, 25.0), "seed": rng.randi() % 100000, "town": str(town["id"])})
							taken.append(Vector3(p.x, p.y, float(Kit.entry(extra).get("clear_m", 3.0))))
							break
				along += lot
	return out


static func _pick(rng: RandomNumberGenerator, weights: Dictionary) -> String:
	var total := 0.0
	for k: String in weights:
		total += float(weights[k])
	var roll := rng.randf() * total
	for k: String in weights:
		roll -= float(weights[k])
		if roll <= 0.0:
			return k
	return str(weights.keys()[0])


static func _clear(terrain: BigTerrain, p: Vector2, r: float, taken: Array[Vector3]) -> bool:
	if terrain.road_edge_at(p.x, p.y) < r + 1.0 or terrain.water_edge_at(p.x, p.y) < r + 4.0:
		return false
	for t: Vector3 in taken:
		if Vector2(t.x, t.y).distance_to(p) < t.z + r:
			return false
	return true
