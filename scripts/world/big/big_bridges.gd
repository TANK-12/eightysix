class_name BigBridges
extends RefCounted
## Where a bridge goes on a streamed map (lane B5 part 2). A map's "bridges" entry names a road that
## is "bridged" (BigTerrain leaves the river deep and steepens its banks there, no ford); the bridge
## is the kit's "bridge" laid along the road where it crosses the water: flat deck at the height of
## the road bed on the higher bank, pillars down to the river bed, an abutment block at each end so
## the deck always has something under it. layout() returns what BigMap needs to build and place it.

const BANK_CLEAR_M := 1.5  # the deck starts this far beyond the steep bank's foot
const BURY_M := 2.0  # each end runs this far into the bank
const STEP_M := 1.0
const MAX_HALF_M := 200  # a bridge is never longer than twice this


## {"kit", "id", "at": Vector3 (the deck's start, top of the deck), "yaw": radians, "over": kit
## overrides, "from": Vector2, "to": Vector2}. Empty when the road does not cross water.
static func layout(terrain: BigTerrain, entry: Dictionary, spec: Dictionary) -> Dictionary:
	var road := _road(entry, str(spec.get("road", "")))
	if road.is_empty():
		return {}
	var pts: Array = road["points"]
	var cross := Vector2.ZERO
	var dir := Vector2.ZERO
	var found := false
	for i in pts.size() - 1:
		var p0 := Vector2(float(pts[i][0]), float(pts[i][1]))
		var p1 := Vector2(float(pts[i + 1][0]), float(pts[i + 1][1]))
		var d := (p1 - p0).normalized()
		var n := int(p0.distance_to(p1) / STEP_M)
		for k in n:
			var q := p0 + d * (k * STEP_M)
			if terrain.water_edge_at(q.x, q.y) < 0.0:
				cross = q
				dir = d
				found = true
				break
		if found:
			break
	if not found:
		return {}
	var rivers: Array = entry.get("rivers", [])
	var bank: float = float(rivers[0].get("bank_m", 20.0)) if not rivers.is_empty() else 20.0
	var reach := bank * BigTerrain.BRIDGE_BANK_KEEP * BigTerrain.WATER_REACH + BANK_CLEAR_M  # past the steep bank
	var a := cross
	var b := cross
	for _i in MAX_HALF_M:
		if terrain.water_edge_at(a.x, a.y) >= reach:
			break
		a -= dir * STEP_M
	for _i in MAX_HALF_M:
		if terrain.water_edge_at(b.x, b.y) >= reach:
			break
		b += dir * STEP_M
	var length := a.distance_to(b)
	var deck := maxf(terrain.height_at(a.x, a.y), terrain.height_at(b.x, b.y)) + 0.1
	var low := deck
	var k := 0.0
	while k <= length:
		var q := a + dir * k
		low = minf(low, terrain.height_at(q.x, q.y))
		k += STEP_M
	a -= dir * BURY_M
	length += BURY_M * 2.0
	var kit: Dictionary = Kit.entry(str(spec.get("kit", "bridge")))
	var over := {
		"length_m": length,
		"end_heights": [0.0, 0.0],
		"broken_spans": [],
		"pillar_drop_m": deck - low + 2.0,
		"abutment_m": 3.0,
		"width_m": float(road.get("width_m", 9.0)) + 1.5,
	}
	over["span_m"] = length / maxf(1.0, roundf(length / float(kit.get("span_m", 7.0))))
	return {"id": str(spec.get("id", "bridge")), "kit": str(spec.get("kit", "bridge")), "at": Vector3(a.x, deck, a.y), "yaw": -atan2(dir.y, dir.x), "over": over, "from": a, "to": a + dir * length}


static func _road(entry: Dictionary, id: String) -> Dictionary:
	for r: Dictionary in entry.get("roads", []):
		if str(r.get("id", "")) == id:
			return r
	return {}
