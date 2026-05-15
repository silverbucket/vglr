#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float stereo_width;
uniform float param_a;  // distortion strength
uniform float param_b;  // chromatic aberration split
uniform float param_c;  // vignette darkness

in vec2 uv;
out vec4 fragColor;

vec2 barrelUV(vec2 p, float k, vec2 centre, float aspect) {
    vec2 d = (p - centre) * vec2(aspect, 1.0);
    float r2 = dot(d, d);
    d *= 1.0 + k * r2 + k * 0.35 * r2 * r2;
    d /= vec2(aspect, 1.0);
    return d + centre;
}

void main() {
    float aspect = resolution.x / resolution.y;

    // Focal point roams on incommensurate dual-rate oscillators
    float cx = 0.5 + sin(time * 0.17) * sin(time * 0.29) * 0.16;
    float cy = 0.5 + cos(time * 0.13) * cos(time * 0.23) * 0.13;
    cx += stereo_width * 0.07 * sin(time * 2.3);
    vec2 focal = vec2(cx, cy);

    // Bass distortion via smoothstep — nothing at silence, aggressive on kick
    float bassK = smoothstep(0.1, 0.55, bass) * 1.4;
    // Beat snap: use beat directly — it already decays via BEAT_DECAY each frame
    // (Previous exp(-beat*3.2) evaluated to ~0.034 at beat=1, killing the effect)
    float snap  = beat * 3.0;
    float k     = 0.03 + param_a * 0.55 + bassK + snap;

    // Chromatic aberration direction rotates over time
    float aberAngle = time * 0.38 + mid * 1.4;
    vec2  aberDir   = vec2(cos(aberAngle), sin(aberAngle));
    float split     = param_b * 0.12 + treble * 0.02 + beat * 0.06;

    vec2 uvR = clamp(barrelUV(uv + aberDir *  split,        k * 1.15, focal, aspect), 0.001, 0.999);
    vec2 uvG = clamp(barrelUV(uv,                           k,        focal, aspect), 0.001, 0.999);
    vec2 uvB = clamp(barrelUV(uv - aberDir *  split * 0.8,  k * 0.88, focal, aspect), 0.001, 0.999);

    float r = texture(video, uvR).r;
    float g = texture(video, uvG).g;
    float b = texture(video, uvB).b;
    vec3 col = vec3(r, g, b);

    // Rolling scan flare
    float flareY = fract(time * 0.21 + mid * 0.09);
    float flare  = smoothstep(0.010, 0.0, abs(uv.y - flareY)) * (0.45 + bass * 0.75);
    col += vec3(flare * 0.85, flare * 0.65, flare * 0.35);

    // Vignette from focal point
    float dist = length((uv - focal) * vec2(1.0, 1.0 / aspect));
    float vignette = 1.0 - dist * (1.1 + param_c * 1.9 + bass * 0.3);
    col *= clamp(vignette, 0.0, 1.0);

    // Treble prismatic fringing
    float prism = treble * 0.35 * dist * dist;
    col.r = clamp(col.r + prism * 0.22, 0.0, 1.0);
    col.b = clamp(col.b - prism * 0.16, 0.0, 1.0);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
