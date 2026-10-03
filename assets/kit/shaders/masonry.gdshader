// Walls of the ruins and towns (lane LOOK): worn brick or concrete under a patchy coat of painted plaster, a
// darker painted dado along the foot, rain streaks, splashed dirt at the base and a colour that differs from
// building to building (the palette is set per map, see Kit.apply_palette). Textures are CC0, listed in
// assets/SOURCES.md. Kit boxes carry no UVs, so every layer is projected along the face's dominant axis in
// world space (one projection, not three: the pieces are axis-aligned boxes).
shader_type spatial;
render_mode diffuse_lambert, specular_schlick_ggx;

uniform sampler2D base_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D base_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D base_rgh : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D base_ao : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D coat_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D coat_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D macro : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform float base_scale = 0.6;
uniform float coat_scale = 0.5;
uniform vec3 base_tint : source_color = vec3(1.0);
uniform float base_rough = 0.9;
uniform float relief = 1.0;
// share of the walls that still wear a coat (0 = bare), and the paint colours buildings pick from
uniform float coat_amount = 0.6;
uniform vec3 coat_a : source_color = vec3(0.78, 0.7, 0.55);
uniform vec3 coat_b : source_color = vec3(0.6, 0.66, 0.6);
uniform vec3 coat_c : source_color = vec3(0.7, 0.55, 0.42);
uniform vec3 coat_d : source_color = vec3(0.68, 0.7, 0.72);
uniform vec3 dado_col : source_color = vec3(0.2, 0.26, 0.24);
uniform float dado_m = 1.15;
uniform float streaks = 0.45;
uniform float base_dirt = 0.55;
uniform vec3 dirt_col : source_color = vec3(0.3, 0.24, 0.18);
uniform float soot = 0.25;
// many buildings in one mesh (BigCity, real towns from OpenStreetMap): each vertex carries its building's
// foot in UV2 (x, z) and UV.x (height), so colours still differ from building to building, and UV.y the
// storey height (m) for a grid of dark window panes on the walls (0: none)
uniform bool batched = false;
uniform float window_every_m = 3.1;

varying vec3 wp;
varying vec3 wn;
varying vec3 origin;
varying float storey;

float hash11(float p) {
	p = fract(p * 0.1031);
	p *= p + 33.33;
	p *= p + p;
	return fract(p);
}

float hash21(vec2 p) {
	vec3 p3 = fract(vec3(p.xyx) * 0.1031);
	p3 += dot(p3, p3.yzx + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

void vertex() {
	wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wn = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	origin = MODEL_MATRIX[3].xyz;
	storey = 0.0;
	if (batched) {
		origin = vec3(UV2.x, UV.x, UV2.y);
		storey = UV.y;
	}
}

void fragment() {
	vec3 an = abs(wn);
	vec2 uv;
	int axis;
	if (an.y >= an.x && an.y >= an.z) {
		uv = wp.xz;
		axis = 1;
	} else if (an.x >= an.z) {
		uv = wp.zy;
		axis = 0;
	} else {
		uv = wp.xy;
		axis = 2;
	}
	float height = wp.y - origin.y;
	float building = hash21(floor(origin.xz * 0.37));
	// the wall panels are about 2 m by 1 m: a little tone change from one to the next
	float panel = hash21(floor(vec2(uv.x * 0.5 + uv.y * 0.31, wp.y * 1.1)) + building * 91.0);

	vec3 b = texture(base_col, uv * base_scale).rgb * base_tint;
	b *= 0.88 + 0.24 * panel;
	float ao = mix(1.0, texture(base_ao, uv * base_scale).r, 0.85);
	float rough = base_rough * texture(base_rgh, uv * base_scale).r;
	vec3 tn = texture(base_nrm, uv * base_scale).rgb * 2.0 - 1.0;

	// painted plaster in patches: more of it higher up and on the sheltered side, peeled off low and by noise
	float m_big = texture(macro, uv * 0.06 + building * 7.0).r;
	float m_mid = texture(macro, uv * 0.31 + 0.2).r;
	float m_fine = texture(macro, uv * 1.7).r;
	float keep = coat_amount * (0.2 + 0.9 * hash11(building * 53.0));
	float edge = m_big * 0.6 + m_mid * 0.4 + clamp(height * 0.045, 0.0, 0.3) - 0.2 + (m_fine - 0.5) * 0.18;
	float coat = smoothstep(1.0 - keep - 0.04, 1.0 - keep + 0.04, edge);
	vec3 paint = coat_a;
	float pick = fract(building * 4.0);
	if (pick > 0.75) {
		paint = coat_d;
	} else if (pick > 0.5) {
		paint = coat_c;
	} else if (pick > 0.25) {
		paint = coat_b;
	}
	float dado = 1.0 - smoothstep(dado_m - 0.06, dado_m + 0.06, height + (m_mid - 0.5) * 0.35);
	paint = mix(paint, dado_col, dado * step(0.35, hash11(building * 17.0 + 3.0)));
	vec3 c = texture(coat_col, uv * coat_scale).rgb;
	float c_lum = dot(c, vec3(0.333));
	vec3 coated = paint * (0.75 + 0.6 * c_lum) * (0.9 + 0.2 * panel);
	vec3 ctn = texture(coat_nrm, uv * coat_scale).rgb * 2.0 - 1.0;
	b = mix(b, coated, coat);
	tn = mix(tn, ctn, coat);
	rough = mix(rough, 0.85, coat);
	// where the coat has just flaked away the brick shows darker and rougher
	float rim = smoothstep(0.0, 0.1, abs(edge - (1.0 - keep))) ;
	b *= mix(0.78, 1.0, rim);
	ao *= mix(1.0, 0.9, coat);

	// rain streaks, dirt splashed up the foot, soot in patches
	float st = texture(macro, vec2((wp.x + wp.z) * 0.9 + uv.x * 0.0, wp.y * 0.07 + building)).r;
	b *= 1.0 - streaks * smoothstep(0.45, 0.8, st) * (0.3 + 0.7 * smoothstep(0.0, 6.0, height));
	float splash = base_dirt * (1.0 - smoothstep(0.0, 1.1 + 0.6 * m_mid, height));
	b = mix(b, dirt_col * (0.8 + 0.4 * m_fine), splash * 0.65);
	b *= 1.0 - soot * smoothstep(0.55, 0.9, m_big) * smoothstep(1.0, 4.0, height);

	if (storey > 0.5 && an.y < 0.5) {
		float along = axis == 0 ? wp.z : wp.x;
		float fl = (height - 0.5) / storey;
		float wx = fract(along / window_every_m + building * 3.0);
		float wy = fract(fl);
		float pane = step(0.3, wx) * step(wx, 0.7) * step(0.3, wy) * step(wy, 0.78) * step(0.0, fl);
		b = mix(b, vec3(0.02, 0.025, 0.03) + 0.04 * m_fine, pane);
		rough = mix(rough, 0.3, pane);
		tn = mix(tn, vec3(0.0, 0.0, 1.0), pane);
		ao *= 1.0 - 0.3 * pane;
	}

	vec3 n = wn;
	float k = relief * (1.0 - coat * 0.35);
	if (axis == 1) {
		n += vec3(tn.x, 0.0, tn.y) * k;
	} else if (axis == 0) {
		n += vec3(0.0, tn.y, tn.x) * k;
	} else {
		n += vec3(tn.x, tn.y, 0.0) * k;
	}
	NORMAL = normalize((VIEW_MATRIX * vec4(normalize(n), 0.0)).xyz);
	ALBEDO = b;
	ROUGHNESS = clamp(rough, 0.35, 1.0);
	AO = ao;
	AO_LIGHT_AFFECT = 0.6;
}
