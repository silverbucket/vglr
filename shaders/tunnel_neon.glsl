#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // spoke count: 0=4 wide sectors, 1=16 narrow spokes
uniform float param_b;  // tunnel speed: 0=slow drift, 1=fast rush
uniform float param_c;  // video bleed: 0=pure neon on black, 1=video through dark areas

in vec2 uv;
out vec4 fragColor;

void main() {
    vec2 p = (uv - 0.5) * 2.0;
    p.x *= resolution.x / resolution.y;

    float r = length(p);
    float a = atan(p.y, p.x) / (2.0 * 3.141592) + 0.5;  // 0→1 around circle

    float spokes = floor(4.0 + param_a * 12.0);
    float speed  = 0.5 + param_b * 2.5 + bass * 1.2 + beat * 3.5;

    // Rushing tunnel rings: hyperbolic bands converging at centre
    float depth = fract(0.18 / max(r, 0.005) - time * speed);

    // Angular sector position
    float ga    = fract(a * spokes);   // 0→1 within current sector
    float cellA = floor(a * spokes);   // which sector

    // Spoke-edge glow: sharp bright line at each sector boundary
    float spokeDist = min(ga, 1.0 - ga);
    float spokeLine = pow(1.0 - spokeDist * 2.0, 8.0);

    // Ring glow: rushing-away tail behind each ring
    float ringLine = pow(1.0 - depth, 3.5) * 1.5;

    // Mid shifts hue groupings (stepped so color changes feel intentional)
    float hueShift = floor(mid * 4.0);
    float h4 = mod(cellA + hueShift, 4.0);

    vec3 neon;
    if      (h4 < 1.0) neon = vec3(1.0,  0.05, 0.85);  // hot pink
    else if (h4 < 2.0) neon = vec3(0.0,  0.90, 1.0);   // electric cyan
    else if (h4 < 3.0) neon = vec3(0.30, 1.0,  0.05);  // acid green
    else               neon = vec3(1.0,  0.45, 0.0);   // neon orange

    float glow = max(spokeLine, ringLine * 0.7);
    glow *= 0.4 + bass * 0.6;

    // Treble: rapid shimmer along spoke lines
    glow += treble * 0.5 * (sin(time * 40.0 + r * 55.0 + cellA) * 0.5 + 0.5) * spokeLine;

    // Radial fade: hole at dead centre, soft fade at screen edge
    float fade = smoothstep(0.04, 0.22, r) * (1.0 - smoothstep(0.88, 1.15, r));

    vec3 col = neon * glow * fade;

    // Beat strobe: surge to full neon brightness
    col = mix(col, neon * fade * 2.0, beat * 0.80);

    // Video bleed: video shows through dark areas of tunnel
    vec3 vid = texture(video, uv).rgb;
    col += vid * param_c * (1.0 - clamp(glow * fade * 2.0, 0.0, 1.0));

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
