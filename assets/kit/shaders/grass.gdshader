// Grass clumps (lane B3): colour from root to tip and per blade, a gentle wind sway that grows toward
// the tip (UV.y), normals bent upward so the clumps light like a lawn rather than paper.
shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap, specular_disabled;

uniform vec3 colour_a : source_color = vec3(0.16, 0.2, 0.09);
uniform vec3 colour_b : source_color = vec3(0.52, 0.5, 0.28);
uniform float sway = 0.09;

varying float tone;
varying float tip;

void vertex() {
	vec3 w = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float wave = sin(TIME * 1.6 + w.x * 0.21 + w.z * 0.17) + 0.5 * sin(TIME * 3.1 + w.x * 0.7);
	VERTEX.xz += vec2(wave, wave * 0.6) * sway * UV.y * UV.y;
	NORMAL = normalize(mix(NORMAL, vec3(0.0, 1.0, 0.0), 0.8));
	tone = COLOR.r;
	tip = UV.y;
}

void fragment() {
	vec3 c = mix(colour_a, colour_b, clamp(tone * 0.7 + tip * 0.45, 0.0, 1.0));
	// alpha 0.1.1: roots only a little darker (0.45 read as black sticks against the sunlit ground)
	ALBEDO = c * mix(0.62, 1.0, tip);
	ROUGHNESS = 0.9;
	BACKLIGHT = c * 0.35;
}
