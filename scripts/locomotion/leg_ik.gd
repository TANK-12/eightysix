class_name LegIK
extends RefCounted
## Two-bone leg solver: where the knee goes for a hip, a foot target and two segment lengths.
## The knee bends towards `pole` (for a Juggernaut: up and outwards, like a spider's leg).


static func knee(hip: Vector3, foot: Vector3, upper: float, lower: float, pole: Vector3) -> Vector3:
	var to_foot := foot - hip
	var dist := clampf(to_foot.length(), absf(upper - lower) + 0.001, upper + lower - 0.001)
	var dir := to_foot.normalized() if to_foot.length() > 0.0001 else Vector3.DOWN
	var along := (upper * upper - lower * lower + dist * dist) / (2.0 * dist)
	var height := sqrt(maxf(upper * upper - along * along, 0.0))
	var bend := pole - dir * pole.dot(dir)
	if bend.length() < 0.0001:
		bend = dir.cross(Vector3.RIGHT)
	return hip + dir * along + bend.normalized() * height


## The foot target pulled back inside the leg's reach.
static func reachable(hip: Vector3, foot: Vector3, upper: float, lower: float) -> Vector3:
	var to_foot := foot - hip
	var reach := upper + lower - 0.002
	if to_foot.length() <= reach:
		return foot
	return hip + to_foot.normalized() * reach


## Transform for a box segment running from `a` to `b` (its long axis is local Z). `up_hint` sets
## its roll (local Y towards it; a leg passes its bend direction so the knee hinge stays square as
## the leg swings); by default world up.
static func segment(a: Vector3, b: Vector3, up_hint: Vector3 = Vector3.ZERO) -> Transform3D:
	var dir := b - a
	if dir.length() < 0.0001:
		return Transform3D(Basis.IDENTITY, a)
	var up := up_hint.normalized() if up_hint.length() > 0.0001 else Vector3.UP
	if absf(dir.normalized().dot(up)) >= 0.98:
		up = Vector3.UP if absf(dir.normalized().dot(Vector3.UP)) < 0.98 else Vector3.FORWARD
	return Transform3D(Basis.looking_at(dir, up), (a + b) * 0.5)


## `pole` turned by `angle` about the hip-to-foot line: the knee then bends towards that, so the leg's
## fold swivels like an elbow while hip and foot stay put.
static func swivelled(hip: Vector3, foot: Vector3, pole: Vector3, angle: float) -> Vector3:
	var axis := foot - hip
	if angle == 0.0 or axis.length() < 0.0001:
		return pole
	return pole.rotated(axis.normalized(), angle)


## The closest two line segments (a1 to b1, a2 to b2) come to each other.
static func segment_distance(a1: Vector3, b1: Vector3, a2: Vector3, b2: Vector3) -> float:
	var d1 := b1 - a1
	var d2 := b2 - a2
	var r := a1 - a2
	var len1 := d1.dot(d1)
	var len2 := d2.dot(d2)
	var f := d2.dot(r)
	var c := d1.dot(r)
	var b := d1.dot(d2)
	var denom := len1 * len2 - b * b
	var s := clampf((b * f - c * len2) / denom, 0.0, 1.0) if denom > 1e-9 else 0.0
	var t := (b * s + f) / len2
	if t < 0.0:
		t = 0.0
		s = clampf(-c / len1, 0.0, 1.0)
	elif t > 1.0:
		t = 1.0
		s = clampf((b - c) / len1, 0.0, 1.0)
	return (a1 + d1 * s).distance_to(a2 + d2 * t)
