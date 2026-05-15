#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // scan frequency: 0=slow wide waves, 1=rapid fine ripples
uniform float param_b;  // scan depth: how far each line shifts
uniform float param_c;  // colour separation width

in vec2 uv;
out vec4 fragColor;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    float freq  = 2.0 + param_a * 18.0;
    float depth = 0.05 + param_b * 0.4;

    // Each row gets an X offset driven by a sin pattern down the screen
    // Two overlapping frequencies give complex, non-repeating patterns
    float offset = sin(uv.y * freq          + time * 1.2) * depth * bass
                 + sin(uv.y * freq * 0.37   + time * 0.7) * depth * 0.4
                 + beat * 0.25 * sin(uv.y * freq * 2.0 + time * 8.0);

    // Colour channels separate — R gets pushed further, B pulled back
    float sep = 0.015 + param_c * 0.06 + bass * 0.04;
    vec2 uvR = vec2(fract(uv.x + offset + sep * 1.3), uv.y);
    vec2 uvG = vec2(fract(uv.x + offset),              uv.y);
    vec2 uvB = vec2(fract(uv.x + offset - sep * 0.8),  uv.y);

    // Treble adds vertical micro-jitter between channels
    float vJit = treble * 0.006 * sin(uv.x * 50.0 + time * 15.0);
    uvR.y = fract(uvR.y + vJit);
    uvB.y = fract(uvB.y - vJit * 0.6);

    float r = texture(video, uvR).r;
    float g = texture(video, uvG).g;
    float b = texture(video, uvB).b;

    // Rainbow tint: hue slowly drifts down the scan axis
    float hue = fract(uv.y * 0.6 + time * 0.04 + bass * 0.15);
    vec3 tint  = hsv2rgb(vec3(hue, 0.45, 1.0));
    vec3 col   = vec3(r, g, b) * tint;

    // Beat: brief complementary flash across the whole frame
    col = mix(col, 1.0 - col, beat * 0.3);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
