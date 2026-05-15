#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // palette: 0=fire, 1=ice/neon
uniform float param_b;  // convection strength
uniform float param_c;  // threshold: 0=only bright areas burn, 1=everything burns

in vec2 uv;
out vec4 fragColor;

vec3 firePalette(float t) {
    t = clamp(t, 0.0, 1.0);
    if (t < 0.2) return mix(vec3(0.0),              vec3(0.15, 0.0,  0.3),  t * 5.0);
    if (t < 0.4) return mix(vec3(0.15, 0.0,  0.3),  vec3(0.8,  0.05, 0.05), (t - 0.2) * 5.0);
    if (t < 0.6) return mix(vec3(0.8,  0.05, 0.05), vec3(1.0,  0.4,  0.0),  (t - 0.4) * 5.0);
    if (t < 0.8) return mix(vec3(1.0,  0.4,  0.0),  vec3(1.0,  0.9,  0.1),  (t - 0.6) * 5.0);
    return             mix(vec3(1.0,  0.9,  0.1),  vec3(1.0,  1.0,  1.0),  (t - 0.8) * 5.0);
}

vec3 icePalette(float t) {
    t = clamp(t, 0.0, 1.0);
    if (t < 0.25) return mix(vec3(0.0),             vec3(0.0,  0.05, 0.25), t * 4.0);
    if (t < 0.5)  return mix(vec3(0.0, 0.05, 0.25), vec3(0.0,  0.4,  0.85), (t - 0.25) * 4.0);
    if (t < 0.75) return mix(vec3(0.0, 0.4,  0.85), vec3(0.5,  1.0,  1.0),  (t - 0.5)  * 4.0);
    return              mix(vec3(0.5, 1.0,  1.0),  vec3(1.0,  1.0,  1.0),  (t - 0.75) * 4.0);
}

void main() {
    vec3 L = vec3(0.299, 0.587, 0.114);

    // Palette breathes on two incommensurate oscillators
    float breathe   = 0.5 + 0.5 * sin(time * 0.23) * sin(time * 0.31);
    // Bass surge fires earlier and drops threshold harder
    float bassSurge = smoothstep(0.1, 0.5, bass);
    float thresh    = 0.38 - param_c * 0.34 - breathe * 0.14 - bassSurge * 0.22;

    // Bass shifts the PHASE of the warp rather than its size — changes character, not scale
    float bPhase = bass * 9.0;
    float shimmer = sin(uv.y * 28.0 + time * 7.3 + bPhase      ) * 0.007
                  + sin(uv.y * 11.0 + time * 3.1 + bPhase * 0.4) * 0.003;
    float upDrift = (0.005 + param_b * 0.025 + beat * 0.04)
                  * sin(uv.x * 13.0 + time * 0.9 + bPhase * 0.25);

    // Mid turbulence: unpredictable boiling at two spatial frequencies
    float turbX = mid * 0.012 * sin(uv.y * 17.0 + time * 4.1) * sin(uv.x *  9.0 + time * 2.3);
    float turbY = mid * 0.012 * cos(uv.x * 13.0 + time * 3.7) * cos(uv.y *  7.0 + time * 1.9);

    vec2 convUV = uv + vec2(shimmer + turbX, -upDrift + turbY);

    // 5-tap bloom
    float spread = 0.005 + param_b * 0.018 + bassSurge * 0.022;
    float lum = dot(texture(video, convUV).rgb, L);
    lum = max(lum, dot(texture(video, convUV + vec2( spread,  0.0  )).rgb, L));
    lum = max(lum, dot(texture(video, convUV + vec2(-spread,  0.0  )).rgb, L));
    lum = max(lum, dot(texture(video, convUV + vec2( 0.0,     spread)).rgb, L));
    lum = max(lum, dot(texture(video, convUV + vec2( 0.0,    -spread)).rgb, L));

    float heat = clamp((lum - thresh) / (1.0 - thresh + 0.01), 0.0, 1.0);
    heat = min(heat + beat * 0.65, 1.0);

    // Palette slowly drifts with accumulated energy — beats advance it, silence drifts it back
    // Rate: ~0.015/s base + 0.04/s per beat + bass contribution → full cycle ~20-60s
    float colorDrift  = fract(time * 0.015 + beat * 0.08 + bass * 0.025);
    float heatOffset  = sin(colorDrift * 6.2832) * 0.18;   // offset cycles through the palette
    float heatShifted = clamp(heat + heatOffset, 0.0, 1.0);

    vec3 fire = firePalette(heatShifted);
    vec3 ice  = icePalette(heatShifted);
    vec3 col  = mix(fire, ice, param_a);

    // Treble flickers hot pixels more aggressively
    float flicker = 1.0 + treble * 0.8 * sin(time * 65.0 + uv.x * 38.0);
    col *= mix(1.0, flicker, smoothstep(0.35, 0.7, heat));

    // Mid rolls a slow complementary hue
    col = mix(col, col.gbr, mid * 0.30 * sin(time * 3.7 * sin(time * 0.19) + uv.y * 6.0));

    // Beat: white surge on hottest pixels
    col = mix(col, vec3(1.0), beat * 0.3 * smoothstep(0.5, 0.9, heat));

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
