class_name BigStream
extends Node3D
## Streams the big map's ground (lane B5). Every 128 m tile always has its 8 m overview mesh and
## collider. Around every mech (the "mechs" group) and the camera, tiles get 1 m ground made on a
## worker thread from BigTerrain.tile(): a mesh (1 m in the camera's first ring, 2 m in the next)
## and a 1 m HeightMapShape3D collider; the overview tile under it is hidden and its collider
## switched off, so a mech only ever stands on the fine ground. Tiles beyond keep_rings are dropped.
## The rings and per-frame budget come from the map entry's "stream" block.

const NEAR_SKIRT_M := 1.5
const MID_SKIRT_M := 3.0
const FAR_SKIRT_M := 8.0

var terrain: BigTerrain
var ground_material: ShaderMaterial  # template; each near tile gets a copy with its own splat
var focus: Node3D = null  # what the mesh rings follow (the current camera when null)
var _cfg: Dictionary
var _far_mesh := {}  # Vector2i -> MeshInstance3D
var _far_body := {}  # Vector2i -> StaticBody3D
var _near := {}  # Vector2i -> {"data", "arrays": [lod1, lod2], "mesh": MeshInstance3D, "lod": int, "body"}
var _pending := {}  # Vector2i -> WorkerThreadPool task id
var _inbox := _Inbox.new()  # worker results; not this node, so the level can be freed mid-task
var built_tiles := 0  # fine tiles made since start (for tests and the bot)
var _protos := {}  # BigScatter.prototypes(): scatter meshes and boulder bodies


func setup(t: BigTerrain, material: ShaderMaterial) -> void:
	terrain = t
	ground_material = material
	_cfg = t.entry.get("stream", {})
	_protos = BigScatter.prototypes()
	Settings.changed.connect(_on_setting)
	var far_mat := material.duplicate() as ShaderMaterial
	far_mat.set_shader_parameter("splat", ImageTexture.create_from_image(t.overview_splat))
	far_mat.set_shader_parameter("splat_half", t.half / BigTerrain.FAR_STEP)
	far_mat.set_shader_parameter("splat_n", float(t.on))
	far_mat.set_shader_parameter("splat_step", float(BigTerrain.FAR_STEP))
	far_mat.set_shader_parameter("splat_shift", Vector2.ZERO)
	for tz in t.tiles:
		for tx in t.tiles:
			var key := Vector2i(tx, tz)
			var o := t.tile_origin(tx, tz)
			var data := t.overview_tile(tx, tz)
			var mi := MeshInstance3D.new()
			mi.mesh = BigTerrain.tile_mesh(data, FAR_SKIRT_M)
			mi.material_override = far_mat
			mi.position = Vector3(o.x, 0.0, o.y)
			add_child(mi)
			_far_mesh[key] = mi
			_far_body[key] = _collider(data, o)


## Makes the 1 m tiles around `at` now, on this thread (before a mech is placed there).
func prime(at: Vector3) -> void:
	var c := terrain.tile_of(at.x, at.z)
	var r := int(_cfg.get("fine_rings", 1))
	for dz in range(-r, r + 1):
		for dx in range(-r, r + 1):
			var key := Vector2i(c.x + dx, c.y + dz)
			if _valid(key) and not _near.has(key):
				_build(key, _work_result(terrain, key), 1)


## Fine tiles wanted now: {key: mesh lod (1, 2, or 0 for a collider only)}.
func wanted() -> Dictionary:
	var want := {}
	var fine := int(_cfg.get("fine_rings", 1))
	for m: Node in get_tree().get_nodes_in_group("mechs"):
		var p := (m as Node3D).global_position
		var c := terrain.tile_of(p.x, p.z)
		for dz in range(-fine, fine + 1):
			for dx in range(-fine, fine + 1):
				var key := Vector2i(c.x + dx, c.y + dz)
				if _valid(key):
					want[key] = 0
	var eye: Variant = _focus_position()
	if eye != null:
		var rings: Array = _cfg.get("mesh_rings", [1, 2])
		var c := terrain.tile_of((eye as Vector3).x, (eye as Vector3).z)
		var outer := int(rings[-1])
		for dz in range(-outer, outer + 1):
			for dx in range(-outer, outer + 1):
				var key := Vector2i(c.x + dx, c.y + dz)
				if _valid(key):
					want[key] = 1 if maxi(absi(dx), absi(dz)) <= int(rings[0]) else 2
	return want


func near_count() -> int:
	return _near.size()


func has_fine(key: Vector2i) -> bool:
	return _near.has(key)


func _process(_delta: float) -> void:
	update()


func update() -> void:
	var want := wanted()
	for key: Vector2i in want:
		if not _near.has(key) and not _pending.has(key):
			_pending[key] = WorkerThreadPool.add_task(BigStream._work.bind(terrain, key, _inbox), false, "big map tile")
	var budget := int(_cfg.get("builds_per_frame", 2))
	for key: Vector2i in _inbox.keys():
		if budget <= 0:
			break
		var result := _inbox.take(key)
		WorkerThreadPool.wait_for_task_completion(_pending[key])
		_pending.erase(key)
		if want.has(key) and not _near.has(key):
			_build(key, result, int(want[key]))
			budget -= 1
	for key: Vector2i in _near.keys():
		if want.has(key):
			_set_lod(key, int(want[key]))
		elif not _within_keep(key, want):
			_drop(key)


func _exit_tree() -> void:
	for id: int in _pending.values():
		WorkerThreadPool.wait_for_task_completion(id)
	_pending.clear()
	if Settings.changed.is_connected(_on_setting):
		Settings.changed.disconnect(_on_setting)
	for b: Node in _protos.get("boulders", []):
		b.free()
	_protos.clear()


func _on_setting(key: String, _value: Variant) -> void:
	if key != "graphics.foliage_density":
		return
	var d := clampf(Settings.get_f("graphics.foliage_density"), 0.0, 1.0)
	for rec: Dictionary in _near.values():
		for c: Node in (rec["mesh"] as Node).get_children():
			if c is MultiMeshInstance3D:
				var mm := (c as MultiMeshInstance3D).multimesh
				mm.visible_instance_count = int(mm.instance_count * d)


## True while tiles are still being made or waiting to be built.
func busy() -> bool:
	return not _pending.is_empty()


static func _work(t: BigTerrain, key: Vector2i, inbox: _Inbox) -> void:
	inbox.put(key, _work_result(t, key))


static func _work_result(t: BigTerrain, key: Vector2i) -> Dictionary:
	var data := t.tile(key.x, key.y, 1)
	var scatter: Dictionary = BigScatter.plan(data, t.entry.get("scatter", {}), t.water_level)
	return {"data": data, "scatter": scatter, "arrays": [BigTerrain.mesh_arrays(data, NEAR_SKIRT_M), BigTerrain.mesh_arrays(BigTerrain.coarsen(data), MID_SKIRT_M)]}


func _build(key: Vector2i, result: Dictionary, lod: int) -> void:
	var data: Dictionary = result["data"]
	var o := terrain.tile_origin(key.x, key.y)
	var mat := ground_material.duplicate() as ShaderMaterial
	var n := int(data["n"])
	mat.set_shader_parameter("splat", ImageTexture.create_from_image(Image.create_from_data(n, n, false, Image.FORMAT_RGBA8, data["splat"])))
	mat.set_shader_parameter("splat_half", 0.0)
	mat.set_shader_parameter("splat_n", float(n))
	mat.set_shader_parameter("splat_step", 1.0)
	mat.set_shader_parameter("splat_shift", -o)
	var mi := MeshInstance3D.new()
	mi.material_override = mat
	mi.position = Vector3(o.x, 0.0, o.y)
	add_child(mi)
	if not _protos.is_empty():
		BigScatter.build(mi, result["scatter"], _protos["meshes"], _protos["boulders"], clampf(Settings.get_f("graphics.foliage_density"), 0.0, 1.0))
	var rec := {"data": data, "arrays": result["arrays"], "mesh": mi, "lod": -1, "body": _collider(data, o)}
	_near[key] = rec
	_set_lod(key, lod)
	(_far_mesh[key] as MeshInstance3D).visible = false
	(_far_body[key] as StaticBody3D).collision_layer = 0
	built_tiles += 1


func _set_lod(key: Vector2i, lod: int) -> void:
	var rec: Dictionary = _near[key]
	var mi: MeshInstance3D = rec["mesh"]
	var show: int = 2 if lod == 0 else lod
	if int(rec["lod"]) == show:
		return
	rec["lod"] = show
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, rec["arrays"][show - 1])
	mi.mesh = mesh


func _drop(key: Vector2i) -> void:
	var rec: Dictionary = _near[key]
	(rec["mesh"] as Node).queue_free()
	(rec["body"] as Node).queue_free()
	_near.erase(key)
	(_far_mesh[key] as MeshInstance3D).visible = true
	(_far_body[key] as StaticBody3D).collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE


func _within_keep(key: Vector2i, want: Dictionary) -> bool:
	var keep := int(_cfg.get("keep_rings", 1))
	for dz in range(-keep, keep + 1):
		for dx in range(-keep, keep + 1):
			if want.has(Vector2i(key.x + dx, key.y + dz)):
				return true
	return false


func _collider(data: Dictionary, o: Vector2) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE
	body.collision_mask = 0
	var cs := CollisionShape3D.new()
	cs.shape = BigTerrain.tile_shape(data)
	var step := float(data["step"])
	cs.position = Vector3(o.x + BigTerrain.TILE_M * 0.5, 0.0, o.y + BigTerrain.TILE_M * 0.5)
	if step != 1.0:
		cs.scale = Vector3.ONE * step
	body.add_child(cs)
	add_child(body)
	return body


func _focus_position() -> Variant:
	if focus != null and is_instance_valid(focus):
		return focus.global_position
	var cam := get_viewport().get_camera_3d() if is_inside_tree() else null
	return cam.global_position if cam != null else null


func _valid(key: Vector2i) -> bool:
	return key.x >= 0 and key.y >= 0 and key.x < terrain.tiles and key.y < terrain.tiles


## Finished tiles handed from the worker threads to the main thread.
class _Inbox:
	extends RefCounted
	var _lock := Mutex.new()
	var _done := {}

	func put(key: Vector2i, result: Dictionary) -> void:
		_lock.lock()
		_done[key] = result
		_lock.unlock()

	func keys() -> Array:
		_lock.lock()
		var k := _done.keys()
		_lock.unlock()
		return k

	func take(key: Vector2i) -> Dictionary:
		_lock.lock()
		var r: Dictionary = _done[key]
		_done.erase(key)
		_lock.unlock()
		return r
