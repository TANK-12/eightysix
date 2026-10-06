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
// lane LOOK2: kit boxes carry their face's size (Parts.box), so the edges can wear: a rounded bevel that
// catches the light, plaster chipped off along the edges, grime in the corners and soot under the broken
// tops. mortar darkens the joints by the texture's AO (sunlit brick showed none), relief_gain sharpens
// the texture's relief, colour_spread varies the stone itself from building to building and across the wall.
uniform float bevel_m = 0.035;
uniform float edge_wear = 0.8;
uniform float edge_grime = 0.5;
uniform float top_soot = 0.55;
uniform float sill_streaks = 0.45;
uniform float top_dust = 0.45;
uniform float mortar = 0.6;
uniform float relief_gain = 1.7;
uniform float colour_spread = 1.0;

varying vec3 wp;
varying vec3 wn;
varying vec3 origin;
varying float storey;
varying vec3 wt;
varying vec2 face;
varying vec2 face_half;
varying vec4 open_edges;

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
	face = UV;
	face_half = vec2(0.0);
	wt = vec3(1.0, 0.0, 0.0);
	open_edges = COLOR;
	if (!batched && UV2.x > 0.001) {
		face_half = UV2;
		wt = normalize((MODEL_MATRIX * vec4(TANGENT, 0.0)).xyz);
	}
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
	float ao_tex = texture(base_ao, uv * base_scale).r;
	float ao = mix(1.0, ao_tex, 0.85);
	float rough = base_rough * texture(base_rgh, uv * base_scale).r;
	vec3 tn = texture(base_nrm, uv * base_scale).rgb * 2.0 - 1.0;

	// painted plaster in patches: more of it higher up and on the sheltered side, peeled off low and by noise
	float m_big = texture(macro, uv * 0.06 + building * 7.0).r;
	float m_mid = texture(macro, uv * 0.31 + 0.2).r;
	float m_fine = texture(macro, uv * 1.7).r;
	// the stone itself: warmer or greyer per building, and a slow tonal drift over the wall
	b *= mix(vec3(1.0), mix(vec3(1.06, 0.97, 0.9), vec3(0.84, 0.88, 0.94), hash11(building * 29.0 + 1.0)), colour_spread);
	b *= mix(1.0, 0.78 + 0.44 * m_mid, colour_spread);

	// the face's edges (kit boxes only): metres to the nearest edge, and to the upper edge of a wall face
	float edge_m = 99.0;
	float top_m = 99.0;
	vec3 bevel = vec3(0.0);
	if (face_half.x > 0.001) {
		vec3 wb = cross(wn, wt);
		// a closed edge (the wall carries on in another box) counts as far away
		vec2 open = vec2(face.x < 0.0 ? open_edges.r : open_edges.g, face.y < 0.0 ? open_edges.b : open_edges.a);
		vec2 d = face_half - abs(face) + (1.0 - open) * 99.0;
		edge_m = min(d.x, d.y);
		// at least a pixel and a half wide, so far edges still catch the light
		float w = max(bevel_m, 1.5 * length(fwidth(face)));
		vec2 bv = (1.0 - smoothstep(0.0, w, d)) * sign(face);
		bevel = wt * bv.x + wb * bv.y;
		float tu = wt.y;
		float tv = wb.y;
		if (abs(tv) > 0.7) {
			top_m = face.y * sign(tv) > 0.0 ? d.y : 99.0;
		} else if (abs(tu) > 0.7) {
			top_m = face.x * sign(tu) > 0.0 ? d.x : 99.0;
		}
	}
	float wear = edge_wear * (1.0 - smoothstep(0.03, 0.1 + 0.35 * m_mid, edge_m + (m_fine - 0.5) * 0.12));
	float keep = coat_amount * (0.2 + 0.9 * hash11(building * 53.0));
	float edge = m_big * 0.6 + m_mid * 0.4 + clamp(height * 0.045, 0.0, 0.3) - 0.2 + (m_fine - 0.5) * 0.18;
	float coat = smoothstep(1.0 - keep - 0.04, 1.0 - keep + 0.04, edge);
	coat *= 1.0 - wear;
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
	// mortar joints darker by the texture's AO, where the bare stone shows
	b *= mix(1.0, ao_tex, mortar * (1.0 - coat));
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
	// worn edges: grime along every edge, soot running down from the broken tops (streaky, more on some
	// buildings than others), dust and grit lying on the tops themselves
	b *= 1.0 - edge_grime * (1.0 - smoothstep(0.0, 0.3 + 0.5 * m_mid, edge_m)) * (0.4 + 0.6 * m_fine);
	float st_v = texture(macro, vec2(uv.x * 0.7 + building * 5.0, height * 0.05)).r;
	float burnt = top_soot * smoothstep(0.25, 0.75, hash11(building * 71.0 + 2.0) * 0.7 + m_big * 0.5);
	b *= 1.0 - burnt * (1.0 - smoothstep(0.0, 0.4 + 1.6 * st_v, top_m));
	// rain run off every open top (window sills, broken courses): thin dark streaks down the wall below
	float run = texture(macro, vec2(uv.x * 2.2 + building * 3.0, height * 0.02)).r;
	b *= 1.0 - sill_streaks * smoothstep(0.45, 0.75, run) * (1.0 - smoothstep(0.0, 0.5 + 2.5 * st_v, top_m));
	if (axis == 1 && wn.y > 0.0 && face_half.x > 0.001) {
		b = mix(b, dirt_col * (0.9 + 0.5 * m_fine), top_dust * smoothstep(0.35, 0.7, m_mid + 0.3 * m_fine));
	}

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
	float k = relief * relief_gain * (1.0 - coat * 0.35);
	if (axis == 1) {
		n += vec3(tn.x, 0.0, tn.y) * k;
	} else if (axis == 0) {
		n += vec3(0.0, tn.y, tn.x) * k;
	} else {
		n += vec3(tn.x, tn.y, 0.0) * k;
	}
	n = normalize(n) + bevel * 0.8;
	NORMAL = normalize((VIEW_MATRIX * vec4(normalize(n), 0.0)).xyz);
	ALBEDO = b;
	ROUGHNESS = clamp(rough, 0.35, 1.0);
	AO = ao;
	AO_LIGHT_AFFECT = 0.6;
}
