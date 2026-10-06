// House walls of a real town (BigCity, 2026-10-03; Emerson: "actual AAA graphics, not this weird low
// poly stuff"). A CC0 PBR wall (plaster, brick or slate, see assets/SOURCES.md) carries a grid of windows:
// a stone surround and sill, a painted frame with glazing bars, glass that mirrors the sky (or is blown
// out on damaged houses, with soot above it), shop windows on some ground floors, a plinth along the
// foot, rising damp and rain streaks under every sill. Vertex data from BigCity: UV = (metres along the
// wall, metres above the foot), UV2 = the building's centre (x, z), CUSTOM0 = (wall length m, storey m,
// ruin 0-1, storeys + seed 0-0.99).
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform sampler2D wall_col : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D wall_nrm : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D wall_rgh : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D wall_ao : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D macro : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform float wall_scale_m = 2.5; // one texture repeat covers this many metres
uniform vec3 tint_a : source_color = vec3(1.0);
uniform vec3 tint_b : source_color = vec3(0.93, 0.88, 0.78);
uniform vec3 tint_c : source_color = vec3(0.84, 0.88, 0.9);
uniform vec3 trim_col : source_color = vec3(0.78, 0.76, 0.7);
uniform vec3 frame_col : source_color = vec3(0.88, 0.88, 0.85);
uniform vec3 plinth_col : source_color = vec3(0.3, 0.29, 0.28);
uniform float floor0_m = 1.0; // the ground floor's level above the wall's foot
uniform float plinth_m = 1.3;
uniform float bay_m = 3.3;
uniform float window_w = 0.4; // share of a bay
uniform float window_h = 0.48; // share of a storey
uniform float sill_m = 0.95;
uniform float shop_share = 0.3; // ground floors with shop windows (of the houses with 3+ storeys)
uniform float streaks = 0.5;
uniform float damp = 0.5;
uniform float soot = 0.7;

varying vec4 info;
varying float upness; // |normal.y| in model space: walls 0, roofs and floors 1

float hash(float p) {
	p = fract(p * 0.1031);
	p *= p + 33.33;
	p *= p + p;
	return fract(p);
}

void vertex() {
	info = CUSTOM0;
	upness = abs(NORMAL.y);
}

void fragment() {
	vec2 m = UV;
	float len = info.x;
	float storey = info.y;
	float ruin = info.z;
	float levels = floor(info.w);
	float seed = fract(info.w) + UV2.x * 0.0013 + UV2.y * 0.0017;
	vec2 tuv = m / wall_scale_m + vec2(hash(seed * 7.0), hash(seed * 3.0)) * 5.0;
	float mac = texture(macro, m * 0.045 + seed).r;
	float k = hash(seed * 91.0);
	vec3 tint = k < 0.34 ? tint_a : (k < 0.67 ? tint_b : tint_c);
	tint *= 0.86 + 0.26 * hash(seed * 17.0);
	vec3 alb = texture(wall_col, tuv).rgb * tint;
	float rough = texture(wall_rgh, tuv).r;
	vec3 nm = texture(wall_nrm, tuv).rgb;
	float ao = texture(wall_ao, tuv).r;
	float specular = 0.4;

	// the plinth: a darker band of render or stone along the foot
	float plinth = 1.0 - step(plinth_m + 0.25 * hash(seed * 5.0), m.y);
	alb = mix(alb, plinth_col * (0.8 + 0.4 * texture(wall_col, tuv * 1.7).r), plinth * 0.85);

	if (storey > 0.5 && len > 2.4 && upness < 0.6) {
		float bays = max(floor(len / bay_m), 1.0);
		float bw = len / bays;
		float bi = floor(m.x / bw);
		float fx = (fract(m.x / bw) - 0.5) * bw; // metres from the bay's centre
		float fl = floor((m.y - floor0_m) / storey);
		float fy = (m.y - floor0_m) - fl * storey; // metres above this storey's floor
		bool shop = fl < 0.5 && levels >= 3.0 && hash(seed * 13.0) < shop_share;
		float hw = (shop ? 0.42 : window_w * 0.5) * bw;
		float y0 = shop ? 0.35 : sill_m;
		float y1 = shop ? storey - 0.45 : sill_m + window_h * storey + 0.15;
		if (fl >= 0.0 && fl < levels && len > bw * 0.9) {
			float wid = bi * 7.0 + fl * 31.0 + seed * 101.0;
			// signed distance into the opening (metres): > 0 inside
			float inside = min(hw - abs(fx), min(fy - y0, y1 - fy));
			float surround = smoothstep(-0.16, -0.14, inside) * (1.0 - step(0.0, inside));
			float frame = step(0.0, inside) * (1.0 - step(0.07, inside));
			float bars = step(0.0, inside) * max(1.0 - step(0.025, abs(fx)), 1.0 - step(0.025, abs(fy - mix(y0, y1, 0.66))));
			float glass = step(0.07, inside) * (1.0 - bars);
			bool broken = hash(wid) < ruin * 1.3 + 0.03;
			// sill: a ledge under the window, wider than it, catching the light from above
			float sill = (1.0 - step(hw + 0.12, abs(fx))) * step(y0 - 0.09, fy) * (1.0 - step(y0, fy)) * (shop ? 0.0 : 1.0);
			// rain streaks running down from the sill's ends and middle
			float under = clamp((y0 - fy) / 2.4, 0.0, 1.0) * step(fy, y0 - 0.09) * (1.0 - step(hw, abs(fx)));
			float streak = under > 0.0 ? (1.0 - under) * smoothstep(0.35, 0.8, texture(macro, vec2(m.x * 0.9, m.y * 0.06)).r) : 0.0;
			alb *= 1.0 - streaks * 0.45 * streak;
			// soot above blown-out windows
			if (broken) {
				float above = clamp((fy - y1) / 1.6, 0.0, 1.0) * step(y1, fy) * (1.0 - step(hw + 0.4 + (fy - y1) * 0.3, abs(fx)));
				alb *= 1.0 - soot * (1.0 - above) * step(0.001, above) * (0.6 + 0.4 * mac);
			}
			alb = mix(alb, trim_col * (0.85 + 0.25 * mac), max(surround, sill) * (shop ? 0.4 : 1.0));
			nm = mix(nm, sill > 0.0 ? vec3(0.5, 0.95, 0.6) : vec3(0.5, 0.5, 1.0), max(surround, sill) * 0.8);
			if (frame + bars + glass > 0.0) {
				float paint = hash(seed * 29.0);
				vec3 fc = paint < 0.6 ? frame_col : (paint < 0.85 ? vec3(0.25, 0.2, 0.15) : vec3(0.2, 0.28, 0.22));
				if (broken) {
					// the opening is dark and empty, a few charred frame pieces left
					alb = mix(vec3(0.015, 0.012, 0.01), fc * 0.25, (frame + bars) * step(0.5, hash(wid * 3.0 + fy)));
					rough = 0.95;
					ao *= 0.4;
				} else {
					// glass mirrors the sky; behind it a dim room, a curtain on some windows
					float curtain = step(hash(wid * 5.0), 0.5) * smoothstep(0.0, 0.05, abs(fx) - hw * 0.45);
					vec3 room = mix(vec3(0.03, 0.035, 0.04), vec3(0.32, 0.28, 0.22), curtain * 0.6);
					alb = mix(room, fc, frame + bars);
					rough = mix(0.04, 0.5, frame + bars);
					specular = mix(0.75, 0.4, frame + bars);
					ao *= mix(0.55 + 0.45 * smoothstep(0.07, 0.3, inside), 1.0, frame + bars);
				}
				nm = vec3(0.5, 0.5, 1.0);
			}
		}
	}
	// rising damp and splashed dirt at the foot, soot and grime over ruins
	alb *= 1.0 - damp * 0.35 * (1.0 - smoothstep(0.4, 2.2, m.y)) * (0.6 + 0.4 * mac);
	alb *= 1.0 - ruin * 0.35 * smoothstep(0.45, 0.85, mac);
	ALBEDO = alb;
	ROUGHNESS = rough;
	SPECULAR = specular;
	NORMAL_MAP = nm;
	AO = ao;
	AO_LIGHT_AFFECT = 0.5;
}
