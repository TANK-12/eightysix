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
