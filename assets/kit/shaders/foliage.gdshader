// Shrubs (lane B3; leaf clusters and stems by lane B4): leaf colour from the cluster's tone and height,
// a slow sway, soft back-lighting. COLOR.b = 1 marks the stems (wood). A few plants per hundred are
// dry (`dry`), picked per plant from its position. No discard, so the depth pre-pass stays cheap.
shader_type spatial;
render_mode cull_back, diffuse_lambert_wrap, specular_disabled;

uniform vec3 colour_a : source_color = vec3(0.13, 0.15, 0.08);
uniform vec3 colour_b : source_color = vec3(0.36, 0.37, 0.22);
uniform vec3 colour_dry : source_color = vec3(0.38, 0.33, 0.25);
uniform vec3 colour_wood : source_color = vec3(0.16, 0.12, 0.09);
uniform float dry = 0.12;
// Far off a shrub is a few pixels of leaf and the light between them, not its darkest inner leaves (alpha 0.1.1:
// far shrubs read as black ink dots on Palouse). From far_start_m to far_end_m the colour eases to colour_far
// and the shading to the ground's (lit from above), by far_amount; 0 keeps the old look.
uniform vec3 colour_far : source_color = vec3(0.36, 0.38, 0.26);
uniform float far_start_m = 18.0;
uniform float far_end_m = 90.0;
uniform float far_amount = 0.75;

varying vec3 tone;
varying float plant;

float hash(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

void vertex() {
	vec3 w = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	VERTEX.xz += vec2(sin(TIME * 1.1 + w.x * 0.3), cos(TIME * 0.9 + w.z * 0.3)) * 0.035 * COLOR.g;
	tone = COLOR.rgb;
	plant = hash(floor(w * 1.7) + 0.5);
}

void fragment() {
	vec3 c = mix(colour_a, colour_b, tone.x);
	c = mix(c, colour_dry, step(1.0 - dry, plant) * 0.75 + tone.x * tone.x * 0.15);
	c *= mix(0.55, 1.05, tone.y);
	float far = smoothstep(far_start_m, far_end_m, length(VERTEX)) * far_amount;
	c = mix(mix(c, colour_wood, tone.z), colour_far, far);
	ALBEDO = c;
	NORMAL = normalize(mix(NORMAL, (VIEW_MATRIX * vec4(0.0, 1.0, 0.0, 0.0)).xyz, far));
	ROUGHNESS = 0.85;
	BACKLIGHT = c * 0.3 * (1.0 - tone.z) * (1.0 - far);
}
