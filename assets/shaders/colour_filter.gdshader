// Colour-vision filter (Settings > Accessibility > Colour). Daltonisation: simulate the colour
// deficiency in LMS space, then shift the lost difference into channels that stay visible.
// Mode 4 is plain greyscale.
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;
uniform int mode = 0;
uniform float strength = 1.0;

void fragment() {
	vec3 c = texture(screen_tex, SCREEN_UV).rgb;
	vec3 outc = c;
	if (mode == 4) {
		outc = vec3(dot(c, vec3(0.2126, 0.7152, 0.0722)));
	} else if (mode > 0) {
		mat3 rgb2lms = mat3(vec3(17.8824, 3.45565, 0.0299566), vec3(43.5161, 27.1554, 0.184309),
			vec3(4.11935, 3.86714, 1.46709));
		mat3 lms2rgb = mat3(vec3(0.0809444479, -0.0102485335, -0.000365296938),
			vec3(-0.130504409, 0.0540193266, -0.00412161469),
			vec3(0.116721066, -0.113614708, 0.693511405));
		vec3 lms = rgb2lms * c;
		vec3 sim = lms;
		if (mode == 1) {
			sim.x = 2.02344 * lms.y - 2.52581 * lms.z;
		} else if (mode == 2) {
			sim.y = 0.494207 * lms.x + 1.24827 * lms.z;
		} else {
			sim.z = -0.395913 * lms.x + 0.801109 * lms.y;
		}
		vec3 err = c - lms2rgb * sim;
		outc = clamp(c + vec3(0.0, 0.7 * err.r + err.g, 0.7 * err.r + err.b), 0.0, 1.0);
	}
	COLOR = vec4(mix(c, outc, strength), 1.0);
}
