#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // spoke density: 0=open/few, 1=tight grid
uniform float param_b;  // warp depth: 0=clean tunnel, 1=heavily folded
uniform float param_c;  // video on walls: 0=pure neon, 1=footage wraps the tube

in vec2 uv;
out vec4 fragColor;

void main() {
    const float PI  = 3.141592653;
    const float TAU = 6.283185307;

    vec2 p = (uv - 0.5) * 2.0;
    p.x *= resolution.x / resolution.y;

    // Drift the tunnel centre — gives psychedelic drunk-camera POV
    vec2 drift = vec2(sin(time * 0.11) * sin(time * 0.17),
                      cos(time * 0.13) * cos(time * 0.19));
    p -= drift * (0.10 + mid * 0.06);

    float r = length(p);
    float a = atan(p.y, p.x);   // -PI .. PI

    // Organic breath: two incommensurate oscillator pairs (~never repeat)
    float b1 = sin(time * 0.23) * sin(time * 0.31);   // period ~27s
    float b2 = cos(time * 0.17) * cos(time * 0.29);   // independent phase

    // Bass threshold: nothing at silence, kicks in hard above the floor
    float bassLvl = smoothstep(0.15, 0.75, bass);

    // ── geometry warp ─────────────────────────────────────────────────────────
    // Always-on base breathing + param_b static depth + bass surge
    float warpDrv = 0.10 + b1 * 0.05           // resting breath (subtle, always present)
                  + param_b * 0.55              // knob adds static warp
                  + bassLvl * 0.50;             // bass pushes it dramatically

    // Angular fold: different radii twist different amounts → sectors fold back
    float angFold = warpDrv * (
        sin(r * 4.2 + time * 0.43 + b1 * 1.5) * 0.55 +
        sin(r * 2.1 - time * 0.19 + b2 * 1.0) * 0.28
    );
    float wa = a + angFold * PI;    // at high bass can fold >180° → sectors alias

    // Radial breathing: tube walls expand/contract
    float radPulse = 1.0 + warpDrv * 0.22 * (
        sin(a * 3.0 + time * 0.37 + b1) * 0.5 +
        sin(a * 5.0 - time * 0.23 + b2) * 0.3
    );
    float wr = r * radPulse;

    // ── tunnel rush ───────────────────────────────────────────────────────────
    float speed = 0.55 + param_b * 0.45 + bass * 1.4 + beat * 2.8;
    float depth = fract(0.20 / max(wr, 0.006) - time * speed);

    // ── spokes ────────────────────────────────────────────────────────────────
    float spokes = floor(5.0 + param_a * 11.0);  // 5–16
    float normA  = wa / TAU + 0.5;               // 0→1 (wraps naturally)
    float ga     = fract(normA * spokes);          // 0→1 within sector
    float cellA  = floor(normA * spokes);

    // ── colour ────────────────────────────────────────────────────────────────
    // Hue drifts per-cell; beats advance it so palette accumulates over sections
    float hueDrift = fract(cellA / spokes + time * 0.025 + beat * 0.04);
    // Cold: electric blue → cyan (hyperspace rest state)
    vec3 cold = mix(vec3(0.05, 0.4, 1.0), vec3(0.0, 1.0, 0.9), hueDrift);
    // Warm: hot magenta → amber (mid frequencies push toward heat)
    vec3 warm = mix(vec3(0.9, 0.0, 0.9), vec3(1.0, 0.55, 0.0), fract(hueDrift + 0.4));
    vec3 neon = mix(cold, warm, mid * 0.7 + bassLvl * 0.25);

    // ── glow ──────────────────────────────────────────────────────────────────
    float spokeDist = min(ga, 1.0 - ga);
    float spokeLine = pow(1.0 - spokeDist * 2.0, 7.0);
    float ringLine  = pow(1.0 - depth, 4.5) * 1.8;

    float glow = max(spokeLine, ringLine * 0.65);
    glow *= 0.35 + bassLvl * 0.65 + beat * 0.35;

    // Treble shimmer on spoke edges
    glow += treble * 0.55 * (sin(time * 44.0 + wr * 58.0 + cellA * 5.1) * 0.5 + 0.5)
          * spokeLine;

    // ── fade from centre + edge ───────────────────────────────────────────────
    float fade = smoothstep(0.03, 0.20, r) * (1.0 - smoothstep(0.90, 1.2, r));
    vec3 col = neon * glow * fade;

    // ── beat: hyperspace star-stretch + brightness surge ─────────────────────
    // Extra-thin radial lines that flash on kick (star-to-streak look)
    float streakLine = pow(1.0 - spokeDist * 2.0, 22.0);
    col += vec3(0.85, 0.93, 1.0) * streakLine * beat * fade * 1.4;
    col  = mix(col, neon * fade * 1.8, beat * 0.55);

    // ── video walls ───────────────────────────────────────────────────────────
    // Map the video onto the inside of the tube: (angle, depth) as UV
    // Footage wraps the cylinder; visible where ring glow is bright
    float wallMask = ringLine * (0.3 + bassLvl * 0.4) * fade;
    vec3 vidWall   = texture(video, vec2(fract(normA), depth)).rgb;
    col = mix(col, col * 0.35 + vidWall * 0.85, param_c * wallMask);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
