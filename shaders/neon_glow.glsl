#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // edge threshold: 0=subtle edges, 1=everything glows
uniform float param_b;  // glow spread (widens the neon line)
uniform float param_c;  // video bleed: 0=pitch black bg, 1=dim video visible

in vec2 uv;
out vec4 fragColor;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

// Cross-pattern gradient magnitude at pixel p, sample spacing s
float edgeAt(vec2 p, float s) {
    vec2 px = s / resolution;
    vec3 L  = vec3(0.299, 0.587, 0.114);
    float r = dot(texture(video, p + vec2( px.x, 0.0 )).rgb, L);
    float l = dot(texture(video, p + vec2(-px.x, 0.0 )).rgb, L);
    float u = dot(texture(video, p + vec2( 0.0,  px.y)).rgb, L);
    float d = dot(texture(video, p + vec2( 0.0, -px.y)).rgb, L);
    return length(vec2(r - l, u - d));
}

void main() {
    // Three-scale edge detection: narrow edge + mid spread + outer glow halo
    float glowSpread = 1.0 + param_b * 8.0 + bass * 5.0;
    float e1 = edgeAt(uv, 1.0);
    float e2 = edgeAt(uv, glowSpread * 0.5) * 0.75;
    float e3 = edgeAt(uv, glowSpread)       * 0.45;
    float edge = max(e1, max(e2, e3));

    // Threshold + power curve: kills noise, pops bright edges
    float thresh = 0.08 - param_a * 0.07;
    edge = pow(max(edge - thresh, 0.0) / (1.0 - thresh + 0.01), 0.6);

    // Hue cycles with time, bass, and spatial position for rainbow drift
    float hue = fract(time * 0.12 + bass * 0.5 + uv.x * 0.15 + uv.y * 0.2);
    vec3 glowCol = hsv2rgb(vec3(hue, 1.0, 1.0));

    // Crackle from treble: rapid flicker on edges
    float crackle = 1.0 + treble * 2.5 * sin(time * 40.0 + uv.x * 80.0 + uv.y * 60.0);
    vec3 col = glowCol * edge * (2.5 + beat * 4.0) * crackle;

    // Beat pulse: radial wave from center
    float beatPulse = beat * 0.6 * max(0.0, 1.0 - length(uv - 0.5) * 2.0);
    col += hsv2rgb(vec3(hue + 0.5, 1.0, 1.0)) * beatPulse;

    // Dark base: dim video tinted dark, or pure black depending on param_c
    vec3 bg = texture(video, uv).rgb * (0.06 + param_c * 0.18);
    col = clamp(bg + col, 0.0, 1.0);

    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
