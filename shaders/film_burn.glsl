#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // halation strength (bright areas bleeding warm into dark)
uniform float param_b;  // colour grade warmth (0=cooler/teal, 1=warmer/orange)
uniform float param_c;  // grain intensity

in vec2 uv;
out vec4 fragColor;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
    vec3 col = texture(video, uv).rgb;

    // ── Orange-teal cinematic grade ───────────────────────────────────────────
    // Lift shadows orange, push midtone blues slightly cool
    float warmth = 0.3 + param_b * 0.7;
    col.r = pow(col.r, 0.82 + (1.0 - warmth) * 0.25);
    col.g = pow(col.g, 0.95);
    col.b = pow(col.b, 1.05 + (1.0 - warmth) * 0.2);
    // Shadow lift: add warm orange tone into the darks
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(col + vec3(0.08, 0.04, 0.0) * warmth, col, smoothstep(0.0, 0.35, lum));

    // ── Halation: bright regions bleed warm glow into darks ───────────────────
    float haloRadius = 0.009 + param_a * 0.022 + bass * 0.018;
    vec3  halo = vec3(0.0);
    for (int i = 0; i < 8; i++) {
        float a = float(i) * 0.7854;   // PI/4 per step
        vec2  off = vec2(cos(a), sin(a)) * haloRadius;
        vec3  s   = texture(video, uv + off).rgb;
        float sl  = dot(s, vec3(0.299, 0.587, 0.114));
        halo += vec3(sl * sl * 1.2, sl * sl * 0.5, sl * sl * 0.15);
    }
    halo /= 8.0;
    col += halo * (0.35 + param_a * 0.55);

    // ── Vignette (breathes with bass) ─────────────────────────────────────────
    float dist     = length(uv - 0.5);
    float vignette = 1.0 - dist * (1.4 + bass * 0.7);
    col *= clamp(vignette, 0.0, 1.0);

    // ── Film grain ────────────────────────────────────────────────────────────
    float grain = hash(uv * resolution + fract(time * 73.1));
    col += (grain - 0.5) * (0.04 + param_c * 0.1);

    // ── Light leak on beat: warm flash sweeping from a pseudo-random edge ─────
    float leakAngle = fract(sin(floor(time * 4.0) * 17.3) * 43758.5) * 6.283;
    vec2  leakDir   = vec2(cos(leakAngle), sin(leakAngle));
    float leakFront = 0.5 - dot(uv - 0.5, leakDir);   // 0..1 across frame
    float leak      = smoothstep(0.5, 0.1, leakFront) * beat;
    col += vec3(1.0, 0.45, 0.08) * leak * 0.8;

    // Mid: subtle saturation pulse
    float sat = dot(col, vec3(0.333));
    col = mix(vec3(sat), col, 1.0 + mid * 0.5);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
