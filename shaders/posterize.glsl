#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // colour levels: 0=2 (harshest), 1=12 (rich)
uniform float param_b;  // hue rotation speed
uniform float param_c;  // saturation boost

in vec2 uv;
out vec4 fragColor;

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + 1e-10)), d / (q.x + 1e-10), q.x);
}

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
    vec3 col = texture(video, uv).rgb;

    // Quantize: beat snaps down to 2-level Warhol graphic, bass pumps it back up
    float levels = max(2.0, floor(2.0 + param_a * 10.0 + bass * 4.0 - beat * 4.5));
    col = floor(col * levels + 0.5) / levels;

    // HSV: rotate hue, boost saturation
    vec3 hsv = rgb2hsv(col);
    float hueShift = time * 0.07 * (0.2 + param_b * 0.9) + mid * 0.35;
    hsv.x = fract(hsv.x + hueShift);
    hsv.y = clamp(hsv.y * (1.6 + param_c * 2.2), 0.0, 1.0);
    col = hsv2rgb(hsv);

    // Dithering at colour boundaries (visible on treble)
    float noise  = (hash(uv * resolution) - 0.5) * treble * 0.18 / max(levels, 1.0);
    col = clamp(col + noise, 0.0, 1.0);

    // Beat: second quantization flash in complementary hue
    vec3 hsvComp = vec3(fract(hsv.x + 0.5), hsv.y, hsv.z);
    col = mix(col, hsv2rgb(hsvComp), beat * 0.5);

    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
