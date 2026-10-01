// Small-map ground (lane B3): ambientCG textures (see assets/SOURCES.md) painted by the terrain's splat
// image: r road, g shore and mud, b scorch, a town rubble. Grass and dry dirt from the ground set,
// tinted by large-scale noise; rock on slopes, projected three ways so cliffs do not smear; each set
// sampled at two scales so the tiling does not show at a distance.
shader_type spatial;
render_mode diffuse_lambert, specular_schlick_ggx;

uniform sampler2D splat : filter_linear, repeat_disable;
uniform float splat_half = 512.0;
uniform float splat_n = 1025.0;
uniform sampler2D ground_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D ground_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D rock_col : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D rock_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D town_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D town_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D macro : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform float ground_scale = 0.3;
uniform float rock_scale = 0.16;
uniform float town_scale = 0.33;
uniform vec3 grass_tint : source_color = vec3(0.62, 0.66, 0.42);
uniform vec3 dry_tint : source_color = vec3(0.9, 0.8, 0.64);
uniform vec3 road_tint : source_color = vec3(0.78, 0.74, 0.68);
uniform vec3 mud_tint : source_color = vec3(0.42, 0.38, 0.32);
uniform vec3 rock_tint : source_color = vec3(0.86, 0.84, 0.8);
uniform float water_level = 0.0;
// lane B4 part 3: the pebble detail read as grain, worst under a low sun and in motion. Near the camera
// it keeps this share of its contrast, falling to detail_far by detail_fade_m; the normal map likewise.
uniform float detail_near = 0.75;
uniform float detail_far = 0.35;
uniform float detail_fade_m = 45.0;
uniform float relief_near = 0.7;
uniform float relief_far = 0.25;

varying vec3 wp;
varying vec3 wn;

void vertex() {
	wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wn = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

vec3 two_scale(sampler2D t, vec2 uv, float mixv) {
	return mix(texture(t, uv).rgb, texture(t, uv * 0.29 + vec2(0.37, 0.71)).rgb, mixv);
}

void fragment() {
	vec4 s = texture(splat, (wp.xz + splat_half + 0.5) / splat_n);
	float m1 = texture(macro, wp.xz * 0.0021).r;
	float m2 = texture(macro, wp.xz * 0.017 + 0.3).r;
	float m3 = texture(macro, wp.xz * 0.11 + 0.5).r;
	vec2 guv = wp.xz * ground_scale;
	vec3 g = two_scale(ground_col, guv, 0.35 + 0.3 * m2);
	float far = smoothstep(4.0, detail_fade_m, length(wp - CAMERA_POSITION_WORLD));
	vec3 g_mean = textureLod(ground_col, guv * 0.29 + vec2(0.37, 0.71), 6.0).rgb;
	g = g_mean + (g - g_mean) * mix(detail_near, detail_far, far);
	float green = smoothstep(0.32, 0.68, m1 + (m2 - 0.5) * 0.35);
	vec3 col = g * mix(dry_tint, grass_tint, green) * 1.25;
	vec3 nrm = texture(ground_nrm, guv).rgb;
	float rough = 0.95;

	// town rubble ground: concrete broken up by the dirt
	// patches of broken paving in the dirt, not one pale square
	float town = s.a * smoothstep(0.5, 0.78, m3 * 0.65 + m2 * 0.55) * 0.85;
	if (town > 0.01) {
		vec2 tuv = wp.xz * town_scale;
		col = mix(col, texture(town_col, tuv).rgb * 0.85, town);
		nrm = mix(nrm, texture(town_nrm, tuv).rgb, town);
	}

	// roads: packed gravel, paler and flatter
	float road = s.r;
	col = mix(col, g * road_tint * (0.9 + 0.2 * m3), road);
	nrm = mix(nrm, vec3(0.5, 0.5, 1.0), road * 0.5);
	rough = mix(rough, 0.97, road);

	// shore and mud, wet (darker, glossier) just above the water line
	float mud = s.g;
	col = mix(col, g * mud_tint, mud * 0.85);
	float wet = (1.0 - smoothstep(water_level + 0.1, water_level + 0.9, wp.y)) * mud;
	col *= 1.0 - wet * 0.35;
	rough = mix(rough, 0.35, wet);

	// rock on slopes, three-way projection
	float slope = 1.0 - wn.y;
	float rockiness = smoothstep(0.2, 0.36, slope + (m2 - 0.5) * 0.16);
	if (rockiness > 0.01) {
		// the two side projections only: rock only shows on slopes, where the top one smears
		// both side projections blended by the normal (lane B4): a hard switch left a straight seam down the cliffs
		// only the projections that show are sampled (most pixels need one side): the rim's cliffs
		// cover a lot of the screen
		float wx = smoothstep(0.3, 0.7, abs(wn.x) / (abs(wn.x) + abs(wn.z) + 1e-4));
		vec2 uv_x = wp.zy * rock_scale;
		vec2 uv_z = wp.xy * rock_scale;
		vec3 r_side;
		vec3 n_side;
		if (wx < 0.01) {
			r_side = texture(rock_col, uv_z).rgb;
			n_side = texture(rock_nrm, uv_z).rgb;
		} else if (wx > 0.99) {
			r_side = texture(rock_col, uv_x).rgb;
			n_side = texture(rock_nrm, uv_x).rgb;
		} else {
			r_side = mix(texture(rock_col, uv_z).rgb, texture(rock_col, uv_x).rgb, wx);
			n_side = mix(texture(rock_nrm, uv_z).rgb, texture(rock_nrm, uv_x).rgb, wx);
		}
		float top = clamp(wn.y * 1.4 - 0.4, 0.0, 1.0);
		vec3 r = top > 0.01 ? mix(r_side, texture(rock_col, wp.xz * rock_scale).rgb, top) : r_side;
		col = mix(col, r * rock_tint, rockiness);
		nrm = mix(nrm, n_side, rockiness);
	}

	// shell scorch
	col *= mix(1.0, 0.32 + 0.2 * m3, s.b * 0.9);
	col *= 0.86 + 0.28 * m3;
	ALBEDO = col;
	ROUGHNESS = mix(rough, 0.9, rockiness);
	NORMAL_MAP = nrm;
	NORMAL_MAP_DEPTH = mix(mix(relief_near, relief_far, far), 1.6, rockiness);
}
