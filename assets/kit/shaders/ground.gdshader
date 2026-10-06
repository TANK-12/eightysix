// Ground of both maps (lane B3, look pass by lane LOOK): ambientCG textures (see assets/SOURCES.md) painted by
// the terrain's splat image: r road, g shore and mud, b scorch, a town rubble. Dirt, real turf and stony
// ground, each sampled at two scales so the tiling does not show, mixed by large-scale noise and kept off
// the slopes; rock on slopes, projected two ways so cliffs do not smear. The colours are the map's palette
// (maps.json "palette" -> "ground", set by GroundLook), not the textures' own.
shader_type spatial;
render_mode diffuse_lambert, specular_schlick_ggx;

uniform sampler2D splat : filter_linear, repeat_disable;
uniform float splat_half = 512.0;
uniform float splat_n = 1025.0;
// lane B5: the big map's tiles each carry their own splat (shift = minus the tile's corner) and its
// far ground one at 8 m (step 8); the small map keeps the defaults
uniform vec2 splat_shift = vec2(0.0);
uniform float splat_step = 1.0;
uniform sampler2D ground_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D ground_nrm : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_nrm : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D turf_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D turf_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D stone_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D stone_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D road_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D road_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D town_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D town_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D macro : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform float ground_scale = 0.25;
uniform float turf_scale = 0.8;
uniform float stone_scale = 0.22;
uniform float road_scale = 0.5;
uniform vec3 stone_tint : source_color = vec3(0.9, 0.86, 0.8);
// how much of the ground is turf (0 none, 1 nearly all) and how much of the dirt is stony
uniform float grass_amount = 0.5;
uniform float stone_amount = 0.5;
uniform float contrast = 1.0;
uniform float rock_scale = 0.16;
uniform float town_scale = 0.33;
uniform vec3 grass_tint : source_color = vec3(0.62, 0.66, 0.42);
uniform vec3 dead_tint : source_color = vec3(0.72, 0.64, 0.4);
uniform vec3 dry_tint : source_color = vec3(0.9, 0.8, 0.64);
uniform vec3 road_tint : source_color = vec3(0.78, 0.74, 0.68);
uniform vec3 mud_tint : source_color = vec3(0.42, 0.38, 0.32);
uniform vec3 rock_tint : source_color = vec3(0.86, 0.84, 0.8);
uniform float water_level = 0.0;
// lane B4 part 3: the pebble detail read as grain, worst under a low sun and in motion. Near the camera
// it keeps this share of its contrast, falling to detail_far by detail_fade_m; the normal map likewise.
uniform float detail_near = 1.0;
uniform float detail_far = 0.7;
uniform float detail_fade_m = 90.0;
uniform float relief_near = 1.0;
uniform float relief_far = 0.5;
// far rock (lane LOOK2): how much of the cliff-scale texture's own contrast to keep, and how strong the
// gullies and strata are
uniform float far_rock_detail = 1.3;
uniform float far_rock_breakup = 1.0;

varying vec3 wp;
varying vec3 wn;

void vertex() {
	wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wn = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

// Lane R1: the texture sampled so that its tiling cannot be found. The plane is cut into patches by a slow
// noise (k, 0..1); each patch reads the texture shifted by its own offset, and the two nearest patches are
// blended where they meet, weighted so the sharper one wins (a plain blend of two uncorrelated samples goes
// grey). Two fetches, with the screen-space slopes of the unshifted uv (dx, dy) so the mip level is right.
// the fractal noise sits close to 0.5 (its spread is about 0.12): stretched to use the whole 0..1 range
float stretch(float m) {
	return clamp((m - 0.5) * 2.6 + 0.5, 0.0, 1.0);
}

struct Cell {
	bool near;
	vec2 a;
	vec2 b;
	float f;
};

Cell cell_of(float k, float dist_m) {
	float l = k * 14.0;
	float f = fract(l);
	Cell c;
	// beyond about 70 m tiling cannot be told from the haze: one fetch is enough
	c.near = dist_m < 70.0;
	c.a = sin(vec2(3.0, 7.0) * floor(l + 0.5));
	c.b = sin(vec2(3.0, 7.0) * floor(l));
	c.f = min(f, 1.0 - f) * 2.0;
	return c;
}

vec4 cell_mix(vec4 a, vec4 b, float f) {
	return mix(a, b, smoothstep(0.2, 0.8, f - 0.1 * (a.r + a.g + a.b - b.r - b.g - b.b)));
}

// (a function cannot take the samplers: they differ in filter and hint)
#define SAMPLE_NT(t, uv, c, dx, dy) (c.near ? cell_mix(textureGrad(t, (uv) + c.a, dx, dy), textureGrad(t, (uv) + c.b, dx, dy), c.f) : textureGrad(t, (uv) + c.a, dx, dy))

// The texture at its own scale with its brightness varied by the coarse noise already sampled (v in 0..1).
#define TWO_SCALE(t, uv, v, c, dx, dy) (SAMPLE_NT(t, uv, c, dx, dy).rgb * mix(0.6, 1.4, v))

// the texture's own detail pulled toward its mean colour by k (1 keeps it all): the grain fix of lane B4
vec3 detail(sampler2D t, vec3 c, float k) {
	vec3 mean = textureLod(t, vec2(0.5), 9.0).rgb;
	return mean + (c - mean) * k;
}

void fragment() {
	vec4 s = texture(splat, ((wp.xz + splat_shift) / splat_step + splat_half + 0.5) / splat_n);
	float m1 = texture(macro, wp.xz * 0.0021).r;
	float m2 = texture(macro, wp.xz * 0.017 + 0.3).r;
	float m3 = texture(macro, wp.xz * 0.11 + 0.5).r;
	// the middle scales (metres and decimetres), the ones a 7 m machine actually walks across: patches of
	// crust and damp, scattered stones. Not tied to any texture's own tile, so they break its repetition.
	float m4 = texture(macro, wp.xz * 0.55 + 0.13).r;
	float m5 = texture(macro, wp.xz * 2.3 + 0.41).r;
	float m6 = texture(macro, wp.xz * 0.037 + 0.9).r;
	float mid = mix(0.62, 1.38, stretch(m3)) * mix(0.8, 1.2, stretch(m6)) * mix(0.86, 1.14, stretch(m4)) * mix(0.94, 1.06, m5);
	Cell cl = cell_of(texture(macro, wp.xz * 0.043 + 0.77).r, length(wp - CAMERA_POSITION_WORLD));
	vec2 dg = dFdx(wp.xz);
	vec2 dh = dFdy(wp.xz);
	float slope = 1.0 - wn.y;
	float far = smoothstep(4.0, detail_fade_m, length(wp - CAMERA_POSITION_WORLD));
	float keep = mix(detail_near, detail_far, far);

	// dirt, with stones coming through in patches
	vec2 guv = wp.xz * ground_scale;
	vec3 dirt = detail(ground_col, TWO_SCALE(ground_col, guv, m2, cl, dg * ground_scale, dh * ground_scale), keep) * dry_tint * mid;
	vec2 suv = wp.xz * stone_scale;
	float stony = smoothstep(0.5, 0.8, m2 * 0.7 + m3 * 0.5 + (m4 - 0.5) * 0.35 + (1.0 - stone_amount) * -0.35) * stone_amount * 1.6;
	stony = clamp(stony + smoothstep(0.1, 0.3, slope) * 0.4, 0.0, 1.0);
	vec3 nrm = SAMPLE_NT(ground_nrm, guv, cl, dg * ground_scale, dh * ground_scale).rgb;
	vec3 col = dirt;
	if (stony > 0.01) {
		vec3 stones = detail(stone_col, TWO_SCALE(stone_col, suv, m3, cl, dg * stone_scale, dh * stone_scale), keep) * stone_tint * mid;
		nrm = mix(nrm, SAMPLE_NT(stone_nrm, suv, cl, dg * stone_scale, dh * stone_scale).rgb, stony);
		col = mix(dirt, stones, stony);
	}
	// close up a finer pass of the dirt's own grain, so near ground is crisp rather than smooth
	float close_k = 1.0 - smoothstep(2.0, 18.0, length(wp - CAMERA_POSITION_WORLD));
	if (close_k > 0.01) {
		vec3 fine = texture(ground_col, wp.xz * ground_scale * 4.3 + 0.17).rgb;
		col *= 1.0 + (dot(fine, vec3(0.333)) - 0.4) * 1.1 * close_k;
		nrm = mix(nrm, normalize(nrm + texture(ground_nrm, wp.xz * ground_scale * 4.3 + 0.17).rgb - 0.5), close_k * 0.5);
	}

	// turf where it is flat and the big noise says so, with its own blade-scale detail
	float green = smoothstep(0.38, 0.62, m1 + (m2 - 0.5) * 0.4 + (grass_amount - 0.5) * 0.6);
	green *= 1.0 - smoothstep(0.1, 0.26, slope);
	green *= 0.55 + 0.45 * smoothstep(0.25, 0.6, m3);
	if (green > 0.01) {
		vec2 tuv = wp.xz * turf_scale;
		vec3 turf = detail(turf_col, TWO_SCALE(turf_col, tuv, m3, cl, dg * turf_scale, dh * turf_scale), keep) * mix(grass_tint, dead_tint, smoothstep(0.35, 0.7, m2 * 0.6 + m3 * 0.5 + (m4 - 0.5) * 0.3)) * mid;
		turf = mix(vec3(dot(turf, vec3(0.333))), turf, 0.8);
		col = mix(col, turf, green);
		nrm = mix(nrm, SAMPLE_NT(turf_nrm, tuv, cl, dg * turf_scale, dh * turf_scale).rgb, green);
	}
	float rough = mix(0.95, 0.88, green);

	// town rubble ground: concrete broken up by the dirt
	// patches of broken paving in the dirt, not one pale square
	float town = s.a * smoothstep(0.5, 0.78, m3 * 0.65 + m2 * 0.55) * 0.85;
	if (town > 0.01) {
		vec2 tuv = wp.xz * town_scale;
		col = mix(col, texture(town_col, tuv).rgb * stone_tint * 0.7, town);
		nrm = mix(nrm, texture(town_nrm, tuv).rgb, town);
	}

	// roads: packed gravel, paler and flatter
	// ragged edges: the painted road is pushed in and out by the mid noise, so dirt and turf creep onto it
	float road = smoothstep(0.3, 0.7, s.r + (m4 - 0.5) * 0.55 + (m5 - 0.5) * 0.3) * smoothstep(0.02, 0.2, s.r);
	if (road > 0.01) {
		vec2 ruv = wp.xz * road_scale;
		vec3 gravel = detail(road_col, TWO_SCALE(road_col, ruv, m4, cl, dg * road_scale, dh * road_scale), keep) * road_tint * 1.6;
		gravel *= mix(0.72, 1.0, smoothstep(0.35, 1.0, s.r));
		col = mix(col, gravel, road);
		nrm = mix(nrm, SAMPLE_NT(road_nrm, ruv, cl, dg * road_scale, dh * road_scale).rgb, road * 0.8);
		rough = mix(rough, 0.97, road);
	}

	// shore and mud, wet (darker, glossier) just above the water line
	float mud = s.g;
	col = mix(col, dirt * mud_tint * 2.2, mud * 0.85);
	float wet = (1.0 - smoothstep(water_level + 0.1, water_level + 0.9, wp.y)) * mud;
	col *= 1.0 - wet * 0.35;
	rough = mix(rough, 0.35, wet);

	// rock on slopes, three-way projection
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
		// far rock: the texture's grain turns into a screen-door pattern on distant ridges, so far away it
		// gives way to the same rock at a cliff-sized scale (about 90 m a tile, lane LOOK2): big faces, ledges
		// and cracks in colour and in the normal, where a fade to the mean colour read as smooth grey plastic
		float rock_far = smoothstep(40.0, 260.0, length(wp - CAMERA_POSITION_WORLD));
		if (rock_far > 0.01) {
			vec3 rb;
			vec3 nb;
			if (wx < 0.01) {
				rb = texture(rock_col, uv_z * 0.07).rgb;
				nb = texture(rock_nrm, uv_z * 0.07).rgb;
			} else if (wx > 0.99) {
				rb = texture(rock_col, uv_x * 0.07).rgb;
				nb = texture(rock_nrm, uv_x * 0.07).rgb;
			} else {
				rb = mix(texture(rock_col, uv_z * 0.07).rgb, texture(rock_col, uv_x * 0.07).rgb, wx);
				nb = mix(texture(rock_nrm, uv_z * 0.07).rgb, texture(rock_nrm, uv_x * 0.07).rgb, wx);
			}
			r = mix(r, detail(rock_col, rb, far_rock_detail), rock_far * 0.85);
			n_side = mix(n_side, nb, rock_far * 0.85);
			// gullies: dark streaks running down the steep faces, and horizontal strata, both from the noise
			float across = mix(wp.x, wp.z, wx);
			float gully = stretch(texture(macro, vec2(across * 0.011, wp.y * 0.0009 + 0.3)).r);
			float strata = stretch(texture(macro, vec2(wp.y * 0.035 + m2 * 0.9, 0.61)).r);
			r *= mix(1.0, mix(0.62, 1.12, gully) * mix(0.86, 1.1, strata), rock_far * far_rock_breakup);
		}
		// strata of warm and cool stone broken up by the noise, so a far ridge is not one grey
		r *= mix(vec3(1.12, 0.98, 0.84), vec3(0.88, 0.96, 1.08), smoothstep(0.3, 0.7, m2 * 0.6 + m3 * 0.5 + wp.y * 0.0015));
		col = mix(col, r * rock_tint, rockiness);
		nrm = mix(nrm, n_side, rockiness);
	}

	// shell scorch
	col *= mix(1.0, 0.32 + 0.2 * m3, s.b * 0.9);
	col *= 0.86 + 0.28 * m3;
	vec3 grey = vec3(dot(col, vec3(0.333)));
	ALBEDO = grey + (col - grey) * contrast;
	ROUGHNESS = mix(rough, 0.9, rockiness);
	NORMAL_MAP = nrm;
	NORMAL_MAP_DEPTH = mix(mix(relief_near, relief_far, far), 1.6, rockiness);
}
