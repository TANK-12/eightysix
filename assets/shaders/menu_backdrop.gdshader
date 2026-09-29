// Menu backdrop: the Handler's map table. A vertical gradient, faint topographic contour lines,
// a fine grid, a slow radar sweep, vignette and grain. Colours come from the theme (UiTheme).
shader_type canvas_item;

uniform vec4 top_color : source_color = vec4(0.04, 0.08, 0.11, 1.0);
uniform vec4 bottom_color : source_color = vec4(0.01, 0.015, 0.02, 1.0);
uniform vec4 grid_color : source_color = vec4(0.56, 0.89, 1.0, 1.0);
uniform float grid_strength = 0.06;
uniform float grid_size = 64.0;
uniform vec4 sweep_color : source_color = vec4(0.56, 0.89, 1.0, 1.0);
uniform float sweep_strength = 0.07;
uniform float sweep_speed = 0.05;
uniform float vignette = 0.75;
uniform float grain = 0.035;

float hash(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float value_noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
		mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
	float sum = 0.0;
	float amp = 0.5;
	for (int i = 0; i < 5; i++) {
		sum += value_noise(p) * amp;
		p = p * 2.03 + vec2(17.1, 9.2);
		amp *= 0.5;
	}
	return sum;
}

void fragment() {
	vec2 px = UV / SCREEN_PIXEL_SIZE * SCREEN_PIXEL_SIZE.y * 1080.0;
	vec3 col = mix(top_color.rgb, bottom_color.rgb, smoothstep(0.0, 1.0, UV.y));

	float h = fbm(px / 380.0 + vec2(TIME * 0.003, TIME * 0.001)) * 10.0;
	float f = fract(h);
	float d = min(f, 1.0 - f) / max(fwidth(h), 0.0001);
	float contour = 1.0 - smoothstep(0.0, 1.2, d);
	float major = step(0.5, fract(floor(h) * 0.2 + 0.01)) * 0.6 + 0.4;
	col += grid_color.rgb * contour * grid_strength * 1.6 * major;

	vec2 g = abs(fract(px / grid_size - 0.5) - 0.5) * grid_size;
	float grid_line = 1.0 - smoothstep(0.0, 1.0, min(g.x, g.y));
	col += grid_color.rgb * grid_line * grid_strength;

	float sweep_x = fract(TIME * sweep_speed) * 1.5 - 0.25;
	float dx = UV.x - sweep_x;
	float trail = dx < 0.0 ? exp(dx * 9.0) : exp(-dx * 140.0);
	col += sweep_color.rgb * trail * sweep_strength;

	vec2 c = UV - 0.5;
	col *= clamp(1.0 - dot(c, c) * vignette * 1.6, 0.0, 1.0);
	col += (hash(px + fract(TIME) * 97.0) - 0.5) * grain;
	COLOR = vec4(col, 1.0);
}
