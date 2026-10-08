class_name FilmGrade
extends RefCounted
## A colour grade as a small 3D lookup table (lane B4), built from one weather entry's "grade" block:
## shadows and highlights each pushed toward a tint (split toning, as film looks are made), after a soft
## contrast curve (Alpha 0.1.1), on top of the environment's own saturation. The table is 32^3 and costs
## one texture read in the tonemap pass. Missing fields leave the image unchanged.

const SIZE := 32
const LUMA := Vector3(0.2126, 0.7152, 0.0722)


## grade: {"contrast": 1.1, "shadow_shift": [r, g, b], "highlight_shift": [r, g, b], "strength": 1.0}. Contrast is
## the soft S-curve of contrast_curve; shifts are small offsets (about -0.05 to 0.05) added where the picture is dark
## or bright.
static func lut(grade: Dictionary) -> ImageTexture3D:
	var tex := ImageTexture3D.new()
	tex.create(Image.FORMAT_RGB8, SIZE, SIZE, SIZE, false, slices(grade))
	return tex


## The table's slices, one image per blue step (lut wraps them in a texture).
static func slices(grade: Dictionary) -> Array[Image]:
	var k := float(grade.get("contrast", 1.0))
	var sh := _v(grade.get("shadow_shift", [0, 0, 0]))
	var hi := _v(grade.get("highlight_shift", [0, 0, 0]))
	var strength := float(grade.get("strength", 1.0))
	var images: Array[Image] = []
	for b in SIZE:
		var img := Image.create_empty(SIZE, SIZE, false, Image.FORMAT_RGB8)
		for g in SIZE:
			for r in SIZE:
				# Godot reads the table at the colour itself, with no half-texel offset, so texel i is what the
				# colour (i + 0.5) / SIZE gets (Alpha 0.1.1: filled for i / (SIZE - 1), it sent 0-4 of 255 to black)
				var c := (Vector3(r, g, b) + Vector3.ONE * 0.5) / float(SIZE)
				img.set_pixel(r, g, _grade_colour(c, k, sh, hi, strength))
		images.append(img)
	return images


## Contrast as a soft S-curve about mid grey (Alpha 0.1.1). The slope at 0.5 is the contrast, as with
## Environment.adjustment_contrast, but that is a straight line that clamps: at 1.14 every value under 16 of 255
## went to pure black and shadows read as ink. Here the ends bend into 0 and 1 instead. The toe is four times as
## wide as the part the line would clip (its slope at black is half the contrast, so deep shadows keep detail);
## the shoulder is only as wide as it must be, so highlights stay close to the line. Contrast of 1 or less is the
## line itself (it clips nothing); above 1.45 the toe and shoulder would meet, so it stops there.
static func contrast_curve(x: float, contrast: float) -> float:
	if contrast <= 1.0:
		return clampf(0.5 + (x - 0.5) * contrast, 0.0, 1.0)
	var k := minf(contrast, 1.45)
	var toe := 2.0 * (k - 1.0) / k
	var shoulder := (k - 1.0) / k
	if x < toe:
		return (k - 1.0) / (2.0 * toe * toe) * x * x + (k - (k - 1.0) / toe) * x
	if x > 1.0 - shoulder:
		var y := 1.0 - x
		return 1.0 - (k - 1.0) / (2.0 * shoulder * shoulder) * y * y - (k - (k - 1.0) / shoulder) * y
	return 0.5 + (x - 0.5) * k


static func _grade_colour(c: Vector3, k: float, sh: Vector3, hi: Vector3, strength: float) -> Color:
	c = Vector3(contrast_curve(c.x, k), contrast_curve(c.y, k), contrast_curve(c.z, k))
	var lum := c.dot(LUMA)
	var w_sh := (1.0 - lum) * (1.0 - lum)
	var w_hi := lum * lum
	var out := c + (sh * w_sh + hi * w_hi) * strength
	return Color(clampf(out.x, 0.0, 1.0), clampf(out.y, 0.0, 1.0), clampf(out.z, 0.0, 1.0))


## The graded colour for one input colour, for tests and tools (same maths as the table).
static func grade_colour(c: Color, grade: Dictionary) -> Color:
	return _grade_colour(
		Vector3(c.r, c.g, c.b),
		float(grade.get("contrast", 1.0)),
		_v(grade.get("shadow_shift", [0, 0, 0])),
		_v(grade.get("highlight_shift", [0, 0, 0])),
		float(grade.get("strength", 1.0))
	)


static func _v(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))
