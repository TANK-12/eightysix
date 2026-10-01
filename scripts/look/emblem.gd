class_name Emblem
extends RefCounted
## Personal emblems on the armour (lane B4), from one data/emblems.json entry: a one-colour SVG
## chipped by noise into worn paint, projected as a Decal from each of the entry's sockets (a mech
## definition's "sockets", body frame, the socket's forward being the way the panel faces). The
## decal box starts just inside the panel and reaches out past it, so it only paints the panel.

const INSET_M := 0.12  # how far inside the socket the projection box starts
const DEPTH_M := 0.4
const PREFIX := "Emblem_"

static var _cache := {}


## Puts the emblem on every socket the entry names, under parent (the mech body), and removes any
## emblem put there before. Returns the new decals ("none" or an unknown id: none).
static func attach(parent: Node3D, sockets: Dictionary, emblem_id: String) -> Array[Decal]:
	for old: Node in parent.find_children(PREFIX + "*", "Decal", false, false):
		parent.remove_child(old)
		old.queue_free()
	var out: Array[Decal] = []
	if not Registry.has_entry("emblems", emblem_id):
		return out
	var e := Registry.entry("emblems", emblem_id)
	if not e.has("image"):
		return out
	var c: Array = e.get("colour", [0, 0, 0])
	var size := float(e.get("size_m", 0.36))
	for socket: String in e.get("sockets", []):
		if not sockets.has(socket):
			continue
		var s: Dictionary = sockets[socket]
		var at := _vec(s.get("at", [0, 0, 0]))
		var outward := _vec(s.get("forward", [signf(at.x), 0, 0])).normalized()
		# a decal projects down its -y and maps x/z to the picture: y = outward, -z = up
		var basis := Basis(outward.cross(Vector3.DOWN), outward, Vector3.DOWN).orthonormalized()
		# mirrored on the side where the picture's right would point backward
		var mirror := bool(e.get("face_forward", true)) and basis.x.dot(Vector3.FORWARD) < 0.0
		var d := Decal.new()
		d.name = PREFIX + socket
		d.texture_albedo = texture(emblem_id, mirror)
		d.modulate = Color(float(c[0]), float(c[1]), float(c[2]))
		d.size = Vector3(size, DEPTH_M, size)
		d.upper_fade = 0.0
		d.lower_fade = 0.0
		d.normal_fade = 0.2  # nothing on surfaces turned nearly side-on to the panel (tops, edges)
		d.distance_fade_enabled = true
		d.distance_fade_begin = 60.0
		d.distance_fade_length = 20.0
		d.transform = Transform3D(basis, at + outward * (DEPTH_M * 0.5 - INSET_M))
		parent.add_child(d)
		out.append(d)
	return out


## The emblem's picture, white where painted (the decal's modulate gives the colour) with chips
## knocked out of its alpha by noise; mirrored left-right when asked. wear < 0 reads the entry's.
static func texture(emblem_id: String, mirrored: bool, wear: float = -1.0) -> ImageTexture:
	var e := Registry.entry("emblems", emblem_id)
	if wear < 0.0:
		wear = float(e.get("wear", 0.0))
	var key := "%s|%s|%.3f" % [emblem_id, mirrored, wear]
	if _cache.has(key):
		return _cache[key]
	var img := (load(str(e["image"])) as Texture2D).get_image()
	img.decompress()
	img.convert(Image.FORMAT_RGBA8)
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.045
	noise.fractal_octaves = 4
	noise.seed = 86
	var cut := 1.0 - wear * 0.9  # noise above the cut is chipped bare; wider band fades
	for y in img.get_height():
		for x in img.get_width():
			var a := img.get_pixel(x, y).a
			if a <= 0.0:
				img.set_pixel(x, y, Color(1, 1, 1, 0))
				continue
			var n := noise.get_noise_2d(x, y) * 0.5 + 0.5
			var keep := 1.0 - smoothstep(cut - 0.08, cut, n * 0.75 + 0.25 * _hash(x, y))
			img.set_pixel(x, y, Color(1, 1, 1, a * keep * (1.0 - wear * 0.25)))
	if mirrored:
		img.flip_x()
	img.generate_mipmaps()
	var tex := ImageTexture.create_from_image(img)
	_cache[key] = tex
	return tex


## Share of the picture that is painted (alpha-weighted), 0-1.
static func coverage(img: Image) -> float:
	var sum := 0.0
	for y in range(0, img.get_height(), 2):
		for x in range(0, img.get_width(), 2):
			sum += img.get_pixel(x, y).a
	return sum / float((img.get_width() / 2) * (img.get_height() / 2))


static func _hash(x: int, y: int) -> float:
	return fposmod(sin(float(x) * 12.9898 + float(y) * 78.233) * 43758.5453, 1.0)


static func _vec(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))
