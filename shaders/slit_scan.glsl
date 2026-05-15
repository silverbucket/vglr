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
uniform float param_c;  // duotone blend: 0=colour, 1=full desaturated duotone

in vec2 uv;
out vec4 fragColor;

float hash1(float x)   { return fract(sin(x * 127.1) * 43758.5453); }
float hash2(vec2 p)    { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

void main() {
    float freq  = 2.0 + param_a * 18.0;
    float depth = 0.04 + param_b * 0.35;

    // Scan direction flips slowly (stochastic — changes every few seconds)
    float dirSign = sign(sin(floor(time * 0.25 + 0.5) * 7.3));

    float scanT = time * 1.3 * dirSign;
    float offset = sin(uv.y * freq         + scanT) * depth * (0.4 + bass * 0.9)
                 + sin(uv.y * freq * 0.37  + scanT * 0.55) * depth * 0.28;
    offset += beat * 0.18 * sin(uv.y * freq * 2.1 + time * 9.0);

    // Tracking hold lines: sparse rows lock to a held offset, snap on beat
    float rowQ     = floor(uv.y * freq * 2.5) / (freq * 2.5);
    float holdPhase = floor(time * 2.5 + hash1(rowQ) * 9.0);
    float holdOff   = (hash2(vec2(holdPhase, rowQ * 13.7)) - 0.5) * depth * 2.2;
    float isHeld    = step(0.91, hash2(vec2(rowQ, floor(time * 1.8))));
    offset = mix(offset, holdOff, isHeld);

    // Corruption strips: random full-row glitch bands
    float stripRow  = floor(uv.y * 20.0);
    float stripTime = floor(time * 3.5);
    float corrupt   = step(0.87, hash2(vec2(stripRow, stripTime)));
    float corruptOff = (hash2(vec2(stripRow + 0.5, stripTime)) - 0.5) * 0.45;
    offset = mix(offset, corruptOff, corrupt * (0.25 + beat * 0.55));

    // Per-channel separation (narrow, analytical — not rainbow)
    float sep = 0.005 + param_c * 0.025 + bass * 0.012;
    float r = texture(video, vec2(fract(uv.x + offset + sep),        uv.y)).r;
    float g = texture(video, vec2(fract(uv.x + offset),               uv.y)).g;
    float b = texture(video, vec2(fract(uv.x + offset - sep * 0.65),  uv.y)).b;
    vec3 col = vec3(r, g, b);

    // Desaturated duotone: dark navy → warm cream
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    vec3 duotone = mix(vec3(0.05, 0.08, 0.18), vec3(0.94, 0.80, 0.52), lum);
    col = mix(col, duotone, param_c * 0.75 + 0.15);

    // Desaturate overall pass
    float grey = dot(col, vec3(0.333));
    col = mix(col, vec3(grey), 0.55 - param_c * 0.35);

    // Treble micro-jitter (vertical)
    float vJit = treble * 0.005 * sin(uv.x * 65.0 + time * 18.0);
    col.r = mix(col.r, texture(video, vec2(uv.x + offset + sep, fract(uv.y + vJit))).r, treble * 0.4);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
