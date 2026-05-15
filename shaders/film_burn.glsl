#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // halation strength
uniform float param_b;  // colour grade warmth (0=cooler/teal, 1=warmer/orange)
uniform float param_c;  // grain intensity

in vec2 uv;
out vec4 fragColor;

float hash(vec2 p)  { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
float hash1(float x){ return fract(sin(x * 127.1) * 43758.5453); }

void main() {
    // ── Gate weave: entire frame wobbles vertically (film gate instability) ──────
    float weave  = (0.003 + bass * 0.003) * sin(time * 6.3 + 0.71) * sin(time * 11.7);

    // ── Focal breathing: slow zoom oscillation ───────────────────────────────────
    float breathe = 1.0 + 0.013 * sin(time * 0.23) * sin(time * 0.31);
    vec2  srcUV   = (uv - 0.5) / breathe + 0.5 + vec2(0.0, weave);
    srcUV = clamp(srcUV, 0.001, 0.999);

    vec3 col = texture(video, srcUV).rgb;

    // ── Orange-teal cinematic grade ───────────────────────────────────────────────
    float warmth = 0.3 + param_b * 0.7;
    col.r = pow(col.r, 0.82 + (1.0 - warmth) * 0.25);
    col.g = pow(col.g, 0.95);
    col.b = pow(col.b, 1.05 + (1.0 - warmth) * 0.2);
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(col + vec3(0.08, 0.04, 0.0) * warmth, col, smoothstep(0.0, 0.35, lum));

    // ── Flickering halation: strength modulates at ~4-7 Hz ───────────────────────
    float haloFlicker = 1.0 + 0.38 * sin(time * 5.1) * sin(time * 3.7);
    float haloRadius  = (0.009 + param_a * 0.022 + bass * 0.018) * haloFlicker;
    vec3  halo = vec3(0.0);
    for (int i = 0; i < 8; i++) {
        float a  = float(i) * 0.7854;
        vec2  off = vec2(cos(a), sin(a)) * haloRadius;
        vec3  s  = texture(video, srcUV + off).rgb;
        float sl = dot(s, vec3(0.299, 0.587, 0.114));
        halo += vec3(sl * sl * 1.2, sl * sl * 0.5, sl * sl * 0.15);
    }
    halo /= 8.0;
    col += halo * (0.35 + param_a * 0.55) * haloFlicker;

    // ── Vignette (breathes with bass) ─────────────────────────────────────────────
    float dist     = length(uv - 0.5);
    float vignette = 1.0 - dist * (1.4 + bass * 0.7);
    col *= clamp(vignette, 0.0, 1.0);

    // ── Clumped grain: product of two noise scales for organic clustering ─────────
    float grain1 = hash(uv * resolution          + fract(time * 73.1));
    float grain2 = hash(uv * resolution * 0.22   + fract(time * 17.3));
    float grain  = (grain1 - 0.5) * (grain2 * 1.5 + 0.25);
    col += grain * (0.045 + param_c * 0.11);

    // ── Light leak on beat — only fires on ~45% of beats (stochastic gate) ───────
    float beatEpoch = floor(time * 3.5);
    float beatGate  = step(0.55, hash1(beatEpoch * 0.13));
    float leakAngle = fract(hash1(beatEpoch * 0.37)) * 6.2832;
    vec2  leakDir   = vec2(cos(leakAngle), sin(leakAngle));
    float leakFront = 0.5 - dot(uv - 0.5, leakDir);
    float leak      = smoothstep(0.5, 0.1, leakFront) * beat * beatGate;
    col += vec3(1.0, 0.45, 0.08) * leak * 0.85;

    // ── Frame flash: strong white blast on a rare subset of beats (~12%) ─────────
    float flashGate = step(0.88, hash1(beatEpoch * 0.077));
    col = mix(col, vec3(1.0), beat * flashGate * 0.75);

    // ── Mid: saturation pulse ─────────────────────────────────────────────────────
    float sat = dot(col, vec3(0.333));
    col = mix(vec3(sat), col, 1.0 + mid * 0.5);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
