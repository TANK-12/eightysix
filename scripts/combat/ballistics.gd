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


## The recoil impulse of one shot, N s: the projectile's momentum plus the propellant gas's (the gas
## leaves at about gas_speed_factor x the muzzle speed; 1.5 is the usual figure for high-velocity
## guns). A muzzle brake would turn part of the gas momentum forward; the 57 mm has none. Weapons
## whose ammo gives no propellant_kg fall back to the weapon's fixed recoil_impulse_ns.
static func recoil_impulse(gun_def: Dictionary, ammo: Dictionary) -> float:
	if not ammo.has("propellant_kg"):
		return float(gun_def.get("recoil_impulse_ns", 0.0))
	var v := float(ammo.get("muzzle_m_s", 0.0))
	var gas := float(ammo["propellant_kg"]) * v * float(gun_def.get("gas_speed_factor", 1.5))
	if bool(gun_def.get("muzzle_brake", false)):
		gas *= 1.0 - float(gun_def.get("brake_efficiency", 0.35)) * 2.0
	return float(ammo.get("projectile_kg", 0.0)) * v + gas
