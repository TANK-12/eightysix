class_name LegionNav
extends RefCounted
## Path-finding for the Legion on the big map (lane B5 part 3). The AI steers locally (rays and ground probes),
## which is not enough on a 4 km map: a unit walking straight at the Juggernaut stalls on a ridge or at the river.
## This is a coarse grid over the Legion's area (CELL_M per cell, read from the terrain's 8 m overview) where
## ground steeper than the slope limit and water deeper than the wade limit are walls; fords stay open, and a
## bridge is a corridor of open cells that is open only while the bridge stands. A* (Godot's AStarGrid2D) gives the
## waypoints; the brain steers to the next one with its own local avoidance for the rest.

const CELL_M := 16.0
const SLOPE_WEIGHT := 3.0  # a cell at the slope limit costs this much more to cross than flat ground
const CORRIDOR_EXTEND_M := 40.0  # a bridge corridor runs this far past each end, over the steep banks
const CORRIDOR_WIDTH_M := 12.0

var _grid := AStarGrid2D.new()
var _n := 0
var _origin := Vector2.ZERO  # world x, z of the centre of cell (0, 0)
var _base_solid := PackedByteArray()  # 1: a wall by terrain
var _corridors := {}  # id -> {"cells": Array[Vector2i], "open": bool}
var _terrain: BigTerrain


## A grid over [-area_half_m, area_half_m] on both axes. max_slope_deg: steeper cells are walls (a little under the
## units' own limit, as a cell's slope is a 32 m average); wade_m: water deeper than this is a wall.
static func build(terrain: BigTerrain, area_half_m: float, max_slope_deg: float = 30.0, wade_m: float = 0.6) -> LegionNav:
	var nav := LegionNav.new()
	nav._terrain = terrain
	nav._n = int(ceilf(area_half_m * 2.0 / CELL_M))
	nav._origin = Vector2(-area_half_m + CELL_M * 0.5, -area_half_m + CELL_M * 0.5)
	nav._grid.region = Rect2i(0, 0, nav._n, nav._n)
	nav._grid.cell_size = Vector2(CELL_M, CELL_M)
	nav._grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	nav._grid.default_compute_heuristic = AStarGrid2D.HEURISTIC_OCTILE
	nav._grid.default_estimate_heuristic = AStarGrid2D.HEURISTIC_OCTILE
	nav._grid.update()
	nav._base_solid.resize(nav._n * nav._n)
	var tan_max := tan(deg_to_rad(max_slope_deg))
	# one height read per cell (plus a ring round the grid), then the slopes from neighbours: the terrain's own
	# lookup is the slow part
	var w := nav._n + 2
	var hs := PackedFloat32Array()
	hs.resize(w * w)
	for j in w:
		for i in w:
			var c := nav._centre(Vector2i(i - 1, j - 1))
			hs[j * w + i] = terrain.overview_height(c.x, c.y)
	var wet := terrain.water_level - wade_m
	for j in nav._n:
		for i in nav._n:
			var k := (j + 1) * w + i + 1
			var gx := (hs[k + 1] - hs[k - 1]) / (2.0 * CELL_M)
			var gz := (hs[k + w] - hs[k - w]) / (2.0 * CELL_M)
			var slope := sqrt(gx * gx + gz * gz)
			var cell := Vector2i(i, j)
			var wall := slope > tan_max or hs[k] < wet
			nav._base_solid[j * nav._n + i] = 1 if wall else 0
			if wall:
				nav._grid.set_point_solid(cell, true)
			else:
				nav._grid.set_point_weight_scale(cell, 1.0 + SLOPE_WEIGHT * (slope / tan_max) * (slope / tan_max))
	return nav


## A bridge from world (x, z) `a` to `b`: the cells along it, widened and run past both ends, are open while the
## corridor is open (set_corridor_open) and walls while it is not. Added open.
func add_corridor(id: String, a: Vector2, b: Vector2) -> void:
	var cells: Array[Vector2i] = []
	var dir := (b - a).normalized()
	var from := a - dir * CORRIDOR_EXTEND_M
	var length := from.distance_to(b + dir * CORRIDOR_EXTEND_M)
	var half := CORRIDOR_WIDTH_M * 0.5 + CELL_M * 0.5
	var side := Vector2(-dir.y, dir.x)
	var k := 0.0
	while k <= length:
		var p := from + dir * k
		for off: float in [-half, 0.0, half]:
			var cell := _cell_of(p + side * off)
			if cell.x >= 0 and not cells.has(cell):
				cells.append(cell)
		k += CELL_M * 0.5
	_corridors[id] = {"cells": cells, "open": false}
	set_corridor_open(id, true)


## Opens or closes a corridor. Closing puts back the terrain's own walls (the river banks are walls).
func set_corridor_open(id: String, open: bool) -> void:
	if not _corridors.has(id):
		return
	var c: Dictionary = _corridors[id]
	c["open"] = open
	for cell: Vector2i in c["cells"]:
		var wall := _base_solid[cell.y * _n + cell.x] == 1 and not open
		var in_other := false
		for other_id: String in _corridors:
			if other_id != id and bool(_corridors[other_id]["open"]) and (_corridors[other_id]["cells"] as Array).has(cell):
				in_other = true
		_grid.set_point_solid(cell, wall and not in_other)
		if open:
			_grid.set_point_weight_scale(cell, 1.0)


## Waypoints (world, on the ground) from `from` to `to`, every cell centre along the path except the first,
## ending at `to` itself. A start or goal on a wall is moved to the nearest cell that is not. Empty when there is
## no way (or the goal is outside the grid).
func path(from: Vector3, to: Vector3) -> PackedVector3Array:
	var out := PackedVector3Array()
	var a := _nearest_open(_cell_of(Vector2(from.x, from.z)))
	var b := _nearest_open(_cell_of(Vector2(to.x, to.z)))
	if a.x < 0 or b.x < 0:
		return out
	var ids := _grid.get_id_path(a, b, true)
	for k in range(1, ids.size()):
		var c := _centre(ids[k])
		out.append(Vector3(c.x, _terrain.overview_height(c.x, c.y), c.y))
	if not out.is_empty() and _cell_of(Vector2(to.x, to.z)) == b:
		out[out.size() - 1] = Vector3(to.x, to.y, to.z)
	return out


## Whether the cell under world (x, z) is a wall.
func is_wall(x: float, z: float) -> bool:
	var c := _cell_of(Vector2(x, z))
	return c.x < 0 or _grid.is_point_solid(c)


func _centre(cell: Vector2i) -> Vector2:
	return _origin + Vector2(cell) * CELL_M


func _cell_of(p: Vector2) -> Vector2i:
	var c := Vector2i(((p - _origin) / CELL_M).round())
	if c.x < 0 or c.y < 0 or c.x >= _n or c.y >= _n:
		return Vector2i(-1, -1)
	return c


## `cell` if it is open, else the closest open cell in growing rings (up to 12 cells out); (-1, -1) when none.
func _nearest_open(cell: Vector2i) -> Vector2i:
	if cell.x < 0:
		return cell
	if not _grid.is_point_solid(cell):
		return cell
	for r in range(1, 13):
		var best := Vector2i(-1, -1)
		var best_d := INF
		for dj in range(-r, r + 1):
			for di in range(-r, r + 1):
				if maxi(absi(di), absi(dj)) != r:
					continue
				var c := cell + Vector2i(di, dj)
				if c.x < 0 or c.y < 0 or c.x >= _n or c.y >= _n or _grid.is_point_solid(c):
					continue
				var d := float(di * di + dj * dj)
				if d < best_d:
					best_d = d
					best = c
		if best.x >= 0:
			return best
	return Vector2i(-1, -1)
