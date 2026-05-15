#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // colour levels: 0=2 (harshest posterize), 1=10 (rich)
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

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec3 col = texture(video, uv).rgb;
    float lum = dot(col, vec3(0.299, 0.587, 0.114));

    // Per-channel quantization: each channel gets different levels
    float baseL = max(2.0, floor(2.0 + param_a * 8.0 + bass * 3.0 - beat * 4.5));
    float levR  = max(2.0, baseL + floor(mid    * 2.5) - 1.0);
    float levG  = baseL;
    float levB  = max(2.0, baseL - floor(treble * 1.8) + 1.0);
    col.r = floor(col.r * levR + 0.5) / levR;
    col.g = floor(col.g * levG + 0.5) / levG;
    col.b = floor(col.b * levB + 0.5) / levB;

    // Per-luminance-band hue: shadows, midtones, highlights each shift independently
    float speed    = 0.06 + param_b * 0.18;
    float hueShadow    = fract(time * speed + 0.0);
    float hueMidtone   = fract(time * speed + 0.33 + mid  * 0.22);
    float hueHighlight = fract(time * speed + 0.67 - bass * 0.18);

    vec3 hsv = rgb2hsv(col);
    float hueShift = mix(hueShadow,   hueMidtone,   smoothstep(0.0,  0.45, lum));
    hueShift       = mix(hueShift,    hueHighlight, smoothstep(0.5,  1.0,  lum));
    hsv.x = fract(hsv.x + hueShift * 0.55);
    hsv.y = clamp(hsv.y * (1.5 + param_c * 2.2), 0.0, 1.0);
    col = hsv2rgb(hsv);

    // Halftone: dot radius grows with bass
    float dotScale = 55.0 + bass * 90.0;
    vec2  dotGrid  = fract(uv * dotScale) - 0.5;
    float dotR     = 0.14 + bass * 0.30 + lum * 0.12;
    float dotMask  = step(length(dotGrid), dotR);
    float dotMix   = (0.08 + bass * 0.38) * (1.0 - lum * 0.4);
    col = mix(col, col * dotMask, dotMix);

    // Beat: Warhol snap to 2-level complementary flash
    vec3 compFlash = vec3(floor(col.r * 2.0 + 0.5) / 2.0,
                          floor((1.0 - col.g) * 2.0 + 0.5) / 2.0,
                          0.5);
    col = mix(col, compFlash, beat * 0.55);

    // Treble dithering at quantization edges
    float noise = (hash(uv * resolution) - 0.5) * treble * 0.14 / max(baseL, 1.0);
    col = clamp(col + noise, 0.0, 1.0);

    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
