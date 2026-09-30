class_name Ballistics
extends RefCounted
## Projectile flight: gravity plus a simple velocity-proportional drag ("drag_per_s" on the ammo
## entry: the fraction of speed lost per second, as exp(-drag * t)). One step per physics tick; the
## projectile ray-casts the segment it covered, so a 1550 m/s dart (13 m a tick) cannot skip a wall.


## [new position, new velocity] after `dt`.
static func step(pos: Vector3, vel: Vector3, dt: float, gravity: float, drag: float) -> Array:
	var v2 := vel * exp(-drag * dt) + Vector3.DOWN * gravity * dt
	return [pos + (vel + v2) * 0.5 * dt, v2]


## How far below the bore line a round has dropped after flying `distance_m` level (for ranging
## marks on the reticle): steps the same integrator the projectile uses.
static func drop_at(distance_m: float, speed: float, gravity: float, drag: float, dt: float = 1.0 / 120.0) -> float:
	var pos := Vector3.ZERO
	var vel := Vector3(0.0, 0.0, -speed)
	var prev := pos
	var guard := 0
	while -pos.z < distance_m and guard < 100000:
		var s := step(pos, vel, dt, gravity, drag)
		prev = pos
		pos = s[0]
		vel = s[1]
		guard += 1
	# The last tick overshoots by up to a tick's travel (13 m for the dart), more than drag changes
	# the drop, so read the drop where the path actually crosses distance_m.
	var span := -pos.z + prev.z
	var f := (distance_m + prev.z) / span if span > 0.0 else 1.0
	return -lerpf(prev.y, pos.y, f)
