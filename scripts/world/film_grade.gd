class_name FilmGrade
extends RefCounted
## A colour grade as a small 3D lookup table (lane B4), built from one weather entry's "grade" block:
## shadows and highlights each pushed toward a tint (split toning, as film looks are made), on top of
## the environment's own contrast and saturation. The table is 32^3 and costs one texture read in
## the tonemap pass. Missing fields leave the image unchanged.

const SIZE := 32
const LUMA := Vector3(0.2126, 0.7152, 0.0722)


## grade: {"shadow_shift": [r, g, b], "highlight_shift": [r, g, b], "strength": 1.0}. Shifts are small
## offsets (about -0.05 to 0.05) added where the picture is dark or bright.
static func lut(grade: Dictionary) -> ImageTexture3D:
	var sh := _v(grade.get("shadow_shift", [0, 0, 0]))
	var hi := _v(grade.get("highlight_shift", [0, 0, 0]))
	var strength := float(grade.get("strength", 1.0))
	var images: Array[Image] = []
	for b in SIZE:
		var img := Image.create_empty(SIZE, SIZE, false, Image.FORMAT_RGB8)
		for g in SIZE:
			for r in SIZE:
				var c := Vector3(r, g, b) / float(SIZE - 1)
				img.set_pixel(r, g, _grade_colour(c, sh, hi, strength))
		images.append(img)
	var tex := ImageTexture3D.new()
	tex.create(Image.FORMAT_RGB8, SIZE, SIZE, SIZE, false, images)
	return tex


static func _grade_colour(c: Vector3, sh: Vector3, hi: Vector3, strength: float) -> Color:
	var lum := c.dot(LUMA)
	var w_sh := (1.0 - lum) * (1.0 - lum)
	var w_hi := lum * lum
	var out := c + (sh * w_sh + hi * w_hi) * strength
	return Color(clampf(out.x, 0.0, 1.0), clampf(out.y, 0.0, 1.0), clampf(out.z, 0.0, 1.0))


## The graded colour for one input colour, for tests and tools (same maths as the table).
static func grade_colour(c: Color, grade: Dictionary) -> Color:
	return _grade_colour(
		Vector3(c.r, c.g, c.b), _v(grade.get("shadow_shift", [0, 0, 0])), _v(grade.get("highlight_shift", [0, 0, 0])), float(grade.get("strength", 1.0))
	)


static func _v(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))
