// Test-range ground: dry grass and dirt on the flats, rock on the slopes, broken up by three
// scales of noise so it reads at every distance. Lane B3 replaces this with real textures.
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform sampler2D noise_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D noise_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec3 grass_col : source_color = vec3(0.33, 0.35, 0.21);
uniform vec3 dirt_col : source_color = vec3(0.38, 0.32, 0.25);
uniform vec3 rock_col : source_color = vec3(0.43, 0.42, 0.4);

varying vec3 world_pos;
varying vec3 world_n;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_n = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	float slope = 1.0 - world_n.y;
	float n1 = texture(noise_tex, world_pos.xz * 0.011).r;
	float n2 = texture(noise_tex, world_pos.xz * 0.09).r;
	float n3 = texture(noise_tex, world_pos.xz * 0.7).r;
	vec3 ground = mix(dirt_col, grass_col, smoothstep(0.38, 0.62, n1 + (n2 - 0.5) * 0.3));
	float rockiness = smoothstep(0.16, 0.3, slope + (n2 - 0.5) * 0.14);
	vec3 col = mix(ground, rock_col * (0.8 + 0.4 * n2), rockiness);
	col *= 0.82 + 0.34 * n3;
	ALBEDO = col;
	ROUGHNESS = mix(0.94, 0.82, rockiness);
	NORMAL_MAP = texture(noise_normal, world_pos.xz * mix(0.25, 0.5, rockiness)).rgb;
	NORMAL_MAP_DEPTH = mix(0.5, 1.5, rockiness);
}
