extends "res://tests/lib/test_case.gd"
## Worn edges on kit walls (lane LOOK2): every box face carries its size and which of its edges are
## open, so the masonry shader wears the real edges (tops, openings, corners) and not the seams
## between the blocks of one wall.


func _surface(boxes: Array) -> Array:
	var parts := Kit.Parts.new()
	for b: Array in boxes:
		parts.box("brick", Transform3D(Basis(), b[0]), b[1])
	return parts.commit().surface_get_arrays(0)


## The open flag the shader reads for vertex i along the face axis that runs along world x.
func _flag_along_x(arrays: Array, i: int) -> float:
	var uv: Vector2 = (arrays[Mesh.ARRAY_TEX_UV] as PackedVector2Array)[i]
	var c: Color = (arrays[Mesh.ARRAY_COLOR] as PackedColorArray)[i]
	var t := Vector3(arrays[Mesh.ARRAY_TANGENT][i * 4], arrays[Mesh.ARRAY_TANGENT][i * 4 + 1], arrays[Mesh.ARRAY_TANGENT][i * 4 + 2])
	if absf(t.x) > 0.9:
		return c.r if uv.x < 0.0 else c.g
	return c.b if uv.y < 0.0 else c.a


func test_a_lone_box_has_every_edge_open_and_its_half_size() -> void:
	var a := _surface([[Vector3.ZERO, Vector3(2.0, 1.0, 0.4)]])
	var verts: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
	assert_eq(verts.size(), 36, "36 vertices")
	for i in verts.size():
		assert_eq((a[Mesh.ARRAY_COLOR] as PackedColorArray)[i], Color.WHITE, "edges open")
	var nrms: PackedVector3Array = a[Mesh.ARRAY_NORMAL]
	var front := 0
	for i in verts.size():
		if nrms[i].dot(Vector3.BACK) > 0.99:
			front += 1
			var half: Vector2 = (a[Mesh.ARRAY_TEX_UV2] as PackedVector2Array)[i]
			assert_almost_eq(half.x * half.y, 1.0 * 0.5, 0.001, "front face half size 1 by 0.5")
			var uv: Vector2 = (a[Mesh.ARRAY_TEX_UV] as PackedVector2Array)[i]
			assert_almost_eq(absf(uv.x), half.x, 0.001, "uv at a corner")
	assert_eq(front, 6, "one front face")


func test_the_seam_between_two_blocks_is_closed_and_the_outer_edges_open() -> void:
	var a := _surface([[Vector3.ZERO, Vector3.ONE], [Vector3(1.0, 0.0, 0.0), Vector3.ONE]])
	var verts: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
	var nrms: PackedVector3Array = a[Mesh.ARRAY_NORMAL]
	var seen := 0
	for i in verts.size():
		# the front faces of both blocks: the seam at x = 0.5 is closed, the ends at -0.5 and 1.5 open
		if not nrms[i].dot(Vector3.BACK) > 0.99:
			continue
		seen += 1
		var x := verts[i].x
		if is_equal_approx(x, 0.5):
			assert_eq(_flag_along_x(a, i), 0.0, "seam closed at %s" % verts[i])
		else:
			assert_eq(_flag_along_x(a, i), 1.0, "outer end open at %s" % verts[i])
	assert_eq(seen, 12, "two front faces")


func test_the_top_of_a_wall_stays_open_under_nothing() -> void:
	# a block with another on top: the lower block's top edge is closed, the upper one's open
	var a := _surface([[Vector3.ZERO, Vector3.ONE], [Vector3(0.0, 1.0, 0.0), Vector3.ONE]])
	var verts: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
	var nrms: PackedVector3Array = a[Mesh.ARRAY_NORMAL]
	var uvs: PackedVector2Array = a[Mesh.ARRAY_TEX_UV]
	var cols: PackedColorArray = a[Mesh.ARRAY_COLOR]
	var tans: PackedFloat32Array = a[Mesh.ARRAY_TANGENT]
	var tops := 0
	for i in verts.size():
		if not nrms[i].dot(Vector3.BACK) > 0.99:
			continue
		# the front face's tangent runs up (f[1] = UP), so the top edge is +u: flag g
		assert_almost_eq(tans[i * 4 + 1], 1.0, 0.001, "tangent up")
		if uvs[i].x > 0.0:
			var top := verts[i].y
			assert_eq(cols[i].g, 0.0 if is_equal_approx(top, 0.5) else 1.0, "top edge at y %s" % top)
			tops += 1
	assert_eq(tops, 6, "three top corners per front face")


func test_kit_buildings_keep_their_edge_data() -> void:
	var node := Kit.build("ruin_house", 2)
	var mesh := (node.get_node("Mesh") as MeshInstance3D).mesh
	# the walls' seams are closed; small rubble blocks keep every edge open
	var closed := 0
	for s in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(s)
		if arrays[Mesh.ARRAY_TEX_UV2] != null and arrays[Mesh.ARRAY_COLOR] != null:
			for c: Color in arrays[Mesh.ARRAY_COLOR]:
				if c != Color.WHITE:
					closed += 1
	assert_gt(closed, 100, "the walls' seams are closed")
	node.free()
