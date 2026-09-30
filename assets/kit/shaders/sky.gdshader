// Small-map sky (lane B3): a gradient from the weather entry, the sun disc and glow, and a cloud deck
// (noise projected on a high plane) lit toward the sun. quality 0 = no clouds, 1 = one light sample,
// 2 = four samples through the deck for thicker, softer clouds. No TIME here, so the sky's lighting
// is only recomputed when the weather changes.
shader_type sky;

uniform vec3 sky_top : source_color = vec3(0.25, 0.34, 0.46);
uniform vec3 sky_horizon : source_color = vec3(0.66, 0.66, 0.64);
uniform vec3 ground_colour : source_color = vec3(0.2, 0.19, 0.17);
uniform vec3 cloud_lit : source_color = vec3(1.0, 0.95, 0.88);
uniform vec3 cloud_shade : source_color = vec3(0.42, 0.45, 0.5);
uniform float coverage = 0.55;
uniform int quality = 1;
uniform vec2 wind_offset = vec2(0.0);
uniform sampler2D cloud_noise : filter_linear_mipmap, repeat_enable;

float clouds(vec2 p) {
	float a = texture(cloud_noise, p * 0.23 + wind_offset).r;
	float b = texture(cloud_noise, p * 0.71 + vec2(0.3, 0.6)).r;
	float c = texture(cloud_noise, p * 2.3 + vec2(0.7, 0.1)).r;
	return a * 0.62 + b * 0.27 + c * 0.11;
}

void sky() {
	vec3 d = EYEDIR;
	float up = d.y;
	vec3 col = mix(sky_horizon, sky_top, pow(clamp(up, 0.0, 1.0), 0.55));
	if (up < 0.0) {
		col = mix(sky_horizon, ground_colour, clamp(-up * 5.0, 0.0, 1.0));
	}
	float sd = 0.0;
	if (LIGHT0_ENABLED) {
		sd = max(dot(d, LIGHT0_DIRECTION), 0.0);
		vec3 sun = LIGHT0_COLOR * LIGHT0_ENERGY;
		col += sun * (smoothstep(0.99975, 0.9999, sd) * 18.0 + pow(sd, 90.0) * 0.35 + pow(sd, 7.0) * 0.1);
	}
	if (quality > 0 && up > 0.0) {
		vec2 p = d.xz / (up + 0.1);
		float c = clouds(p);
		float lo = 1.0 - coverage;
		float dens = smoothstep(lo - 0.06, lo + 0.22, c);
		float light = 0.0;
		vec2 toward = LIGHT0_DIRECTION.xz * 0.06;
		int steps = quality > 1 ? 4 : 1;
		for (int i = 1; i <= steps; i++) {
			light += max(clouds(p + toward * float(i)) - c, -0.2);
		}
		light = clamp(0.62 - light / float(steps) * 3.5, 0.0, 1.0);
		vec3 ccol = mix(cloud_shade, cloud_lit, light);
		ccol += LIGHT0_COLOR * pow(sd, 12.0) * (1.0 - dens) * 0.6;
		dens *= smoothstep(0.0, 0.12, up);
		col = mix(col, ccol, dens * 0.96);
	}
	COLOR = col;
}
