shader_type canvas_item;

// Demo : https://codeberg.org/MarshallNekiu/Log_e_Grid_Demo

#define CUSTOM_ASPECT_RATIO false

const vec3[4] COLOR4 = { vec3(1.0, 0.0, 0.0), vec3(0.0, 1.0, 0.0), vec3(1.0, 0.0, 1.0), vec3(0.0, 1.0, 1.0) };
#if CUSTOM_ASPECT_RATIO
	uniform float aspect_ratio = 1.0; // size.x / size.y
#endif
uniform float base = 3.0;
uniform vec3 color_bg : source_color = vec3(0.5);
uniform vec3 color_grid_1 : source_color = vec3(1.0);
uniform vec3 color_grid_2 : source_color = vec3(0.0);
uniform bool floor_grid;
uniform float grid_size = 6.0;
uniform float grid_1_step = 3.0;
uniform float grid_2_step = 3.0;
uniform float line_width = 6.0;
uniform vec2 uv_offset;
uniform float uv_rotation;
uniform float uv_scale = 8.0;

varying float calc_grid_exponent;
varying float calc_grid_pow_this;
varying float calc_grid_pow_next;
varying float calc_line_width;

bool get_axis(vec2 pos) {
	return abs(pos.x) < calc_line_width / 2.0 || abs(pos.y) < calc_line_width / 2.0;
}

bool get_offset_reference(vec2 pos, vec2 off) {
	vec2 pos_abs = abs(pos);
	vec2 off_abs = abs(off);
	float lw = calc_line_width / 2.0;
	
	return sign(pos) == sign(off)
		&& (pos_abs.x < off_abs.x + lw && pos_abs.y < off_abs.y + lw)
		&& (pos_abs.x > off_abs.x - lw || pos_abs.y > off_abs.y - lw);
}

bool set_grid_line(vec2 pos, out bool[4] p_out) {
	float lw = calc_line_width / 2.0;
	
	vec2 a = mod(pos + lw, grid_1_step * calc_grid_pow_this);
	vec2 b = mod(pos + lw, grid_1_step * calc_grid_pow_next);
	vec2 c = mod(pos + lw, grid_1_step / grid_2_step * calc_grid_pow_this);
	vec2 d = mod(pos + lw, grid_1_step / grid_2_step * calc_grid_pow_next);
	
	
	p_out = {
		a.x - lw < lw || a.y - lw < lw,
		b.x - lw < lw || b.y - lw < lw,
		c.x - lw < lw || c.y - lw < lw,
		d.x - lw < lw || d.y - lw < lw
	};
	
	return p_out[0] || p_out[1] || p_out[2] || p_out[3];
}

bool set_grid_bg(vec2 pos, out float p_out) {
	vec2 a = floor(abs(mod(pos / calc_grid_pow_this, grid_size) - grid_size / 2.0) + 0.5) / grid_size;
	vec2 b = floor(abs(mod(pos / calc_grid_pow_next, grid_size) - grid_size / 2.0) + 0.5) / grid_size;
	
	p_out = mix(mix(a.x, b.x, fract(calc_grid_exponent)), mix(a.y, b.y, fract(calc_grid_exponent)), 0.5);
	
	return true;
}

vec2 rotated(vec2 v, float phi) {
	float cosi = cos(phi), sine = sin(phi);
	
	return vec2(cosi * v.x + sine * v.y, cosi * v.y - sine * v.x);
}

void vertex() {
	calc_grid_exponent = log(max(uv_scale / grid_size, 1.0)) / log(base);
	calc_grid_pow_this = pow(base, floor(calc_grid_exponent));
	calc_grid_pow_next = pow(base, ceil(calc_grid_exponent));
	calc_line_width = line_width / 1000.0 * uv_scale;
	
	if (floor_grid) calc_grid_exponent = floor(calc_grid_exponent);
}

void fragment() {
	#if !CUSTOM_ASPECT_RATIO
		vec2 d = fwidth(UV);
		float aspect_ratio = d.y / d.x;
	#endif
	vec2 position = rotated((UV - 0.5) * vec2(aspect_ratio, 1.0), uv_rotation) * uv_scale + uv_offset;
	bool[4] grid_line;
	float grid_bg;
	
	COLOR.rgb = (
		get_axis(position)
			? COLOR4[int(ceil(4.0 / TAU * atan(-position.y, position.x) + 3.5)) % 4]
		: get_offset_reference(position, uv_offset)
			? COLOR4[int(ceil(4.0 / TAU * atan(-position.y / abs(uv_offset.y), position.x / abs(uv_offset.x)) + 3.5)) % 4]
		: get_offset_reference(position, vec2(-0.025 * uv_scale))
			? vec3(1.0)
		: set_grid_bg(position, grid_bg) && set_grid_line(position, grid_line)
			? mix(
				mix(
					grid_line[0] ? color_grid_1 : grid_line[2] ? color_grid_2 : ((grid_bg + 0.2) * color_bg),
					(grid_bg + 0.2) * color_bg,
					fract(calc_grid_exponent)
				),
				grid_line[1] ? color_grid_1 : grid_line[3] ? color_grid_2 : ((grid_bg + 0.2) * color_bg),
				fract(calc_grid_exponent)
			)
		 : (grid_bg + 0.2) * color_bg
	);
}
