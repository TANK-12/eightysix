// River and lake water (lane B3): colour and clarity from the depth behind the surface, two scrolling
// noise normal maps, a shallow-edge foam line, and the sky reflected by the renderer.
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx, cull_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_linear;
uniform sampler2D wave_a : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D wave_b : hint_normal, filter_linear_mipmap, repeat_enable;
uniform vec3 shallow : source_color = vec3(0.23, 0.27, 0.22);
uniform vec3 deep : source_color = vec3(0.035, 0.07, 0.075);
uniform vec2 flow = vec2(0.012, 0.03);

varying vec3 wp;

void vertex() {
	wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float d = texture(depth_tex, SCREEN_UV).r;
	vec4 view = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, d, 1.0);
	view.xyz /= view.w;
	float thick = max(VERTEX.z - view.z, 0.0);
	float t = clamp(thick / 3.5, 0.0, 1.0);
	vec3 na = texture(wave_a, wp.xz * 0.045 + TIME * flow).rgb;
	vec3 nb = texture(wave_b, wp.xz * 0.11 - TIME * flow.yx * 1.3).rgb;
	float foam = (1.0 - smoothstep(0.05, 0.45, thick)) * 0.55;
	ALBEDO = mix(mix(shallow, deep, t), vec3(0.8, 0.82, 0.8), foam);
	ALPHA = clamp(0.55 + t * 0.45 + foam, 0.0, 0.97);
	ROUGHNESS = mix(0.05, 0.4, foam);
	SPECULAR = 0.6;
	NORMAL_MAP = normalize(mix(na, nb, 0.5));
	NORMAL_MAP_DEPTH = 0.55;
}
