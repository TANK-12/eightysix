// Shrubs (lane B3): leaf colour from the vertex tone and height, a slow sway, soft back-lighting.
shader_type spatial;
render_mode cull_back, diffuse_lambert_wrap, specular_disabled;

uniform vec3 colour_a : source_color = vec3(0.2, 0.26, 0.12);
uniform vec3 colour_b : source_color = vec3(0.34, 0.36, 0.18);

varying vec2 tone;

void vertex() {
	vec3 w = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	VERTEX.xz += vec2(sin(TIME * 1.1 + w.x * 0.3), cos(TIME * 0.9 + w.z * 0.3)) * 0.035 * COLOR.g;
	tone = COLOR.rg;
}

void fragment() {
	vec3 c = mix(colour_a, colour_b, tone.x);
	ALBEDO = c * mix(0.55, 1.05, tone.y);
	ROUGHNESS = 0.85;
	BACKLIGHT = c * 0.3;
}
