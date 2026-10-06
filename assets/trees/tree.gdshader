shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;
// Forest trees (BigForest, 2026-10-03): one shader for the three parts of a tree. part 0: the trunk's
// bark; 1: the bough cards; 2: the far billboard, turned about its upright to face the camera. Every
// instance is drawn on one side of near_m only (measured from the main camera to the tree's foot), so
// the near mesh and the billboard hand over at one distance and never both draw. Distances use the
// main camera even in the shadow pass, so a tree casts the shadow of what is drawn.

uniform int part = 0;
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool has_normal = false;
uniform vec3 tint : source_color = vec3(1.0);
uniform float near_m = 240.0;
uniform float sway = 0.25;
uniform float alpha_cut = 0.45;
uniform float roughness = 0.85;

varying float lift;

void vertex() {
	vec3 foot = MODEL_MATRIX[3].xyz;
	vec3 cam = MAIN_CAM_INV_VIEW_MATRIX[3].xyz;
	float d = distance(foot.xz, cam.xz);
	bool show = part == 2 ? d >= near_m : d < near_m;
	lift = 0.0;
	if (!show) {
		VERTEX = vec3(0.0);
	} else if (part == 2) {
		// the far instances carry scale only (no turn), so model space is world space scaled
		vec3 to = cam - foot;
		to.y = 0.0;
		to = normalize(to + vec3(0.0001, 0.0, 0.0));
		vec3 right = vec3(to.z, 0.0, -to.x);
		VERTEX = right * VERTEX.x + vec3(0.0, VERTEX.y, 0.0);
		NORMAL = normalize(to + vec3(0.0, 0.7, 0.0));
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
	ALBEDO = c.rgb * tint * (0.85 + 0.3 * lift);
	ROUGHNESS = roughness;
	if (part == 0) {
		if (has_normal) {
			NORMAL_MAP = texture(normal_tex, UV).rgb;
		}
	} else {
		ALPHA = c.a;
		ALPHA_SCISSOR_THRESHOLD = alpha_cut;
		BACKLIGHT = vec3(0.12, 0.16, 0.08);
	}
}
