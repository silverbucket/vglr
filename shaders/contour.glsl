#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // line density: 0=sparse, 1=dense
uniform float param_b;  // palette: 0=monochrome, 1=neon cycling
uniform float param_c;  // video show-through between lines: 0=dark fill, 1=video

in vec2 uv;
out vec4 fragColor;

vec3 neon_palette(float t) {
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 0.9, 0.5);
    vec3 d = vec3(0.80, 0.45, 0.20);
    return a + b * cos(6.28318 * (c * t + d));
}

void main() {
    vec3  video_col = texture(video, uv).rgb;
    float luma      = dot(video_col, vec3(0.299, 0.587, 0.114));

    // Contour spacing: beat collapses lines (more), bass widens them (fewer)
    float density   = 0.5 + param_a * 12.0 + beat * 10.0 + bass * 2.5;
    float interval  = 1.0 / density;

    // Proximity to nearest contour boundary
    float c_val     = mod(luma, interval) / interval;
    float edge_dist = min(c_val, 1.0 - c_val);
    float line      = 1.0 - smoothstep(0.0, 0.06, edge_dist);

    // Cycling neon palette; treble shifts hue, mid speeds cycling
    float pal_t     = luma * 2.5 + time * 0.05 * (1.0 + mid * 4.0) + treble * 0.4;
    vec3  pal_col   = neon_palette(pal_t);
    float mono      = dot(pal_col, vec3(0.333));
    vec3  line_col  = mix(vec3(mono * 1.3), pal_col * (1.4 + bass * 0.6), param_b);

    // Between lines: dark fill or video content
    vec3 fill = mix(vec3(0.04), video_col * 0.55, param_c);
    vec3 col  = mix(fill, line_col, line);

    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
