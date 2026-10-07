// Map sky (lane B3; rebuilt for alpha 0.1.1): a gradient from the weather entry, the sun disc and glow, and a
// cloud deck (noise projected on a high plane). quality 0 = no clouds, 1 = two light samples, 2 = five samples
// toward the sun for deeper shading. No TIME here, so the sky's lighting is only recomputed when the weather
// changes.
// Alpha 0.1.1: the mid sky kept its weather colours but blended them through grey, so every map got a flat
// lilac dome; the band between horizon and zenith is now pushed back toward the sky's own hue (sky_saturation),
// the horizon gets a thin bright haze band, and the clouds are cumulus forms (warped noise, eroded edges) with
// thick grey bellies, thin sunlit rims and a silver lining toward the sun, fading into the haze far off.
shader_type sky;
render_mode use_half_res_pass;

uniform vec3 sky_top : source_color = vec3(0.25, 0.34, 0.46);
uniform vec3 sky_horizon : source_color = vec3(0.66, 0.66, 0.64);
uniform vec3 ground_colour : source_color = vec3(0.2, 0.19, 0.17);
uniform vec3 cloud_lit : source_color = vec3(1.0, 0.95, 0.88);
uniform vec3 cloud_shade : source_color = vec3(0.42, 0.45, 0.5);
uniform float coverage = 0.55;
uniform int quality = 1;
uniform vec2 wind_offset = vec2(0.0);
// LOOK3: bigger than 1 makes bigger, fewer cloud forms (weather "cloud_scale")
uniform float cloud_scale = 1.0;
// alpha 0.1.1: how much the mid sky keeps its hue (1 = the plain blend, which reads grey-lilac)
uniform float sky_saturation = 1.3;
uniform sampler2D cloud_noise : filter_linear_mipmap, repeat_enable;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

// The big cloud forms: warped low-frequency noise, so the edges curl instead of tiling in blobs.
float cloud_base(vec2 p) {
	vec2 w = vec2(texture(cloud_noise, p * 0.05).r, texture(cloud_noise, p * 0.05 + vec2(0.37, 0.71)).r) - 0.5;
	p += w * 1.2;
	return texture(cloud_noise, p * 0.11 + wind_offset).r * 0.68 + texture(cloud_noise, p * 0.29 + vec2(0.3, 0.6)).r * 0.32;
}

// The noise sits around 0.49 with a spread of about 0.12 (measured on the 512 px texture), so a raw threshold
// gives almost no cloud at low coverage; this spreads it to about 0..1 evenly, so "coverage" is the sky share.
float spread(float base) {
	return 1.0 / (1.0 + exp(-14.6 * (base - 0.49)));
}

// Small detail that eats into the edges of the forms (billows).
float cloud_detail(vec2 p) {
	return texture(cloud_noise, p * 0.9 + vec2(0.7, 0.1)).r * 0.6 + texture(cloud_noise, p * 2.6 + vec2(0.2, 0.9)).r * 0.4;
}

void sky() {
	vec3 d = EYEDIR;
	float up = d.y;
	float h = clamp(up, 0.0, 1.0);
	// blend in display space (as the colours were picked): a linear blend of deep blue and warm grey goes
	// grey-lilac halfway up
	vec3 col = pow(mix(pow(sky_horizon, vec3(0.4545)), pow(sky_top, vec3(0.4545)), pow(h, 0.6)), vec3(2.2));
	// and keep the sky's hue in the middle band
	float band = 4.0 * h * (1.0 - h);
	float lum = dot(col, LUMA);
	col = max(mix(vec3(lum), col, 1.0 + (sky_saturation - 1.0) * band), vec3(0.0));
	// a thin bright haze right at the horizon, the long path through the air
	col = mix(col, sky_horizon * 1.08, exp(-h * 22.0) * 0.55);
	if (up < 0.0) {
		col = mix(sky_horizon, ground_colour, clamp(-up * 5.0, 0.0, 1.0));
	}
	float sd = 0.0;
	vec3 sun = vec3(0.0);
	if (LIGHT0_ENABLED) {
		sd = max(dot(d, LIGHT0_DIRECTION), 0.0);
		sun = LIGHT0_COLOR * LIGHT0_ENERGY;
		// lane B4 part 3: disc 18 -> 6, halo and wide glow about a third (Emerson: far too bright and bloomy)
		col += sun * (smoothstep(0.99975, 0.9999, sd) * 6.0 + pow(sd, 90.0) * 0.12 + pow(sd, 7.0) * 0.035);
		// warm forward scatter low in the sky toward the sun
		col += LIGHT0_COLOR * pow(sd, 3.0) * 0.05 * (1.0 - h);
	}
	// the clouds are soft, so they are worked out at half resolution (a quarter of the pixels) and laid over the
	// full-resolution gradient and sun
	if (AT_HALF_RES_PASS) {
		vec4 cloud = vec4(0.0);
		if (quality > 0 && up > 0.0) {
			vec2 p = d.xz / (up + 0.08) / cloud_scale;
			float lo = 1.0 - coverage;
			// thickness: how far the form rises over the coverage threshold
			float thick = clamp((spread(cloud_base(p)) - lo) / 0.25, 0.0, 1.0);
			// billows: the detail pushes the thin edges in and out
			float detail = cloud_detail(p) - 0.5;
			float dens = clamp((thick + detail * 0.6 * (1.0 - thick) - 0.05) * 1.5, 0.0, 1.0);
			// light: cloud between this point and the sun dims it (Beer's law over a few samples)
			vec2 toward = LIGHT0_DIRECTION.xz * 0.12 / cloud_scale;
			int steps = quality > 1 ? 5 : 2;
			float occ = 0.0;
			for (int i = 1; i <= steps; i++) {
				occ += clamp((spread(cloud_base(p + toward * float(i))) - lo) / 0.25, 0.0, 1.0);
			}
			float lit = exp(-occ / float(steps) * 2.4);
			// seen from below: thick middles are grey bellies, thin edges catch the light
			vec3 ccol = mix(cloud_shade, cloud_lit, clamp(lit * (1.0 - thick * 0.8) + 0.08, 0.0, 1.0));
			ccol *= 0.92 + detail * 0.3;
			// silver lining: thin cloud toward the sun glows
			ccol += sun * pow(sd, 10.0) * (1.0 - thick) * 0.9;
			// far clouds melt into the horizon haze
			float far = exp(-h * 6.0);
			ccol = mix(ccol, mix(sky_horizon, cloud_lit, 0.3), far * 0.75);
			dens *= 1.0 - far * 0.35;
			dens *= smoothstep(0.0, 0.1, up);
			cloud = vec4(ccol, dens * 0.97);
		}
		COLOR = cloud.rgb;
		ALPHA = cloud.a;
	} else {
		COLOR = mix(col, HALF_RES_COLOR.rgb, HALF_RES_COLOR.a);
	}
}
