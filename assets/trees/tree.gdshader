shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;
// Forest trees (BigForest, 2026-10-03): one shader for the three parts of a tree. part 0: the trunk's
// bark; 1: the bough cards; 2: the far billboard, turned about its upright to face the camera. Every
// instance is drawn on one side of near_m only (measured from the main camera to the tree's foot), so
// the near mesh and the billboard hand over at one distance and never both draw. Distances use the
// main camera even in the shadow pass, so a tree casts the shadow of what is drawn.
// LOOK3 (2026-10-06): each tree gets its own shade of green (blue-grey to yellow-green, darker or
// lighter) from a hash of its foot; the crown darkens toward its inside and its lower whorls (sky light
// does not get in there); needles let the sun through when lit from behind (BACKLIGHT from the
// needle colour); the billboard's normal bends across the quad like a cone, so a far tree has a sunny
// and a shaded side; alpha is sharpened with the mip level, so the mipmapped cards keep their coverage
// at distance instead of thinning out.

uniform int part = 0;
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool has_normal = false;
uniform vec3 tint : source_color = vec3(1.0);
uniform float near_m = 240.0;
uniform float sway = 0.25;
uniform float alpha_cut = 0.45;
uniform float roughness = 0.85;
uniform float tree_h = 20.0;
// how far apart trees' greens are (0 = all the same)
uniform float variation = 1.0;
uniform vec3 shade_cool : source_color = vec3(0.78, 0.92, 1.0);
uniform vec3 shade_warm : source_color = vec3(1.12, 1.06, 0.78);
// sky light reaching the crown's inside and its lowest whorls, 0-1
uniform float crown_ao = 0.45;
// sun through the needles, as a share of the needle colour
uniform float translucency = 0.9;

varying float lift;
varying float height;
varying vec3 shade;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void vertex() {
	vec3 foot = MODEL_MATRIX[3].xyz;
	vec3 cam = MAIN_CAM_INV_VIEW_MATRIX[3].xyz;
	float d = distance(foot.xz, cam.xz);
	bool show = part == 2 ? d >= near_m : d < near_m;
	float h1 = hash(floor(foot.xz * 0.5));
	float h2 = hash(floor(foot.zx * 0.5) + 17.0);
	shade = mix(vec3(1.0), mix(shade_cool, shade_warm, h1) * mix(0.82, 1.12, h2), variation);
	lift = 0.0;
	height = clamp(VERTEX.y / tree_h, 0.0, 1.0);
	if (!show) {
		VERTEX = vec3(0.0);
	} else if (part == 2) {
		// the far instances carry scale only (no turn), so model space is world space scaled
		vec3 to = cam - foot;
		to.y = 0.0;
		to = normalize(to + vec3(0.0001, 0.0, 0.0));
		vec3 right = vec3(to.z, 0.0, -to.x);
		float across = VERTEX.x / (tree_h * 0.25);
		VERTEX = right * VERTEX.x + vec3(0.0, VERTEX.y, 0.0);
		// a cone's normal: out to the side the texel sits on, a little up, a little toward the viewer
		NORMAL = normalize(right * across * 1.1 + to * 0.55 + vec3(0.0, 0.6, 0.0));
		lift = 0.5;
	} else if (part == 1) {
		// boughs sway with distance from the trunk (UV.x), each tree on its own phase; normals point
		// out from the trunk and up, so the crown shades as one mass instead of flat cards
		float t = TIME * 0.8 + foot.x * 0.05 + foot.z * 0.07;
		VERTEX.xz += vec2(sin(t), cos(t * 0.8)) * sway * UV.x * UV.x;
		NORMAL = normalize(vec3(VERTEX.x, 0.9 + 0.4 * length(VERTEX.xz), VERTEX.z));
		lift = clamp(UV.x, 0.0, 1.0);
	}
}

void fragment() {
	vec4 c = texture(albedo_tex, UV);
	if (part == 0) {
		ALBEDO = c.rgb * tint * mix(0.8, 1.0, shade.g);
		ROUGHNESS = roughness;
		if (has_normal) {
			NORMAL_MAP = texture(normal_tex, UV).rgb;
		}
	} else {
		// the crown's inside (near the trunk, low whorls) gets little sky light
		float inside = part == 2 ? 1.0 - UV.y : lift;
		float open = mix(1.0 - crown_ao, 1.0, smoothstep(0.0, 0.75, inside * 0.6 + height * 0.55));
		vec3 col = c.rgb * tint * shade * (0.85 + 0.3 * lift);
		ALBEDO = col;
		AO = open;
		AO_LIGHT_AFFECT = 0.25;
		ROUGHNESS = roughness;
		SPECULAR = 0.3;
		BACKLIGHT = col * translucency * (0.4 + 0.6 * lift);
		// keep the cards' coverage in the smaller mip levels (alpha averages down with the mip)
		vec2 px = UV * vec2(textureSize(albedo_tex, 0));
		float lod = max(0.0, 0.5 * log2(max(dot(dFdx(px), dFdx(px)), dot(dFdy(px), dFdy(px)))));
		ALPHA = clamp(c.a * (1.0 + lod * 0.28), 0.0, 1.0);
		ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	}
}
