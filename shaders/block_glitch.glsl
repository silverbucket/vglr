#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float param_a;  // block coarseness: 0=fine bands, 1=thick bands
uniform float param_b;  // chromatic aberration strength
uniform float param_c;  // glitch density: 0=sparse, 1=every band

in vec2 uv;
out vec4 fragColor;

float hash(float n) {
    return fract(sin(n) * 43758.5453);
}

void main() {
    // Band height: param_a maps 4px (fine) to 48px (chunky)
    float blockPx = mix(4.0, 48.0, param_a);
    float blockH  = blockPx / resolution.y;
    float band    = floor(uv.y / blockH);

    // Two time rates: slow for stable state, fast for twitchy beats
    float slowSeed  = hash(band + floor(time * 4.0) * 0.1);
    float fastSeed  = hash(band * 3.7 + floor(time * 24.0));

    // Which bands are glitching: density from param_c + audio
    float prob     = clamp(param_c * 0.6 + bass * 0.35 + beat * 0.55, 0.0, 1.0);
    float glitched = step(1.0 - prob, slowSeed);

    // Horizontal shift — bass drives steady wobble, beat causes big lurches
    float maxShift = 0.12 * bass + 0.25 * beat;
    float shift    = (slowSeed * 2.0 - 1.0) * maxShift * glitched;
    shift         += (fastSeed * 2.0 - 1.0) * 0.07 * beat * glitched;

    vec2 p = vec2(fract(uv.x + shift), uv.y);

    // Chromatic aberration: RGB channels split horizontally
    float ca = param_b * 0.03 + mid * 0.012 + beat * 0.035;
    float r  = texture(video, vec2(fract(p.x + ca), p.y)).r;
    float g  = texture(video, p).g;
    float b  = texture(video, vec2(fract(p.x - ca), p.y)).b;
    vec3 col = vec3(r, g, b);

    // Corruption bars: solid random-color blocks on beats
    float corruptSeed = hash(band * 7.3 + floor(time * 4.0) * 2.1);
    float corrupt     = step(0.80, corruptSeed) * glitched * beat;
    vec3 corruptCol   = vec3(
        hash(band * 1.1 + floor(time * 4.0)),
        hash(band * 2.3 + floor(time * 4.0) + 1.0),
        hash(band * 3.7 + floor(time * 4.0) + 2.0)
    );
    col = mix(col, corruptCol, corrupt);

    // Inversion bursts on strong beats (different bands from corrupt)
    float invertSeed = hash(band * 11.3 + floor(time * 24.0));
    float invert     = step(0.88, invertSeed) * beat * glitched;
    col = mix(col, 1.0 - col, invert);

    // Thin dark scanline at each band edge (gives a digital look)
    float scanEdge = step(0.91, fract(uv.y / blockH));
    col *= 1.0 - scanEdge * 0.55 * param_a;

    // Beat white flash
    col += beat * 0.2;

    fragColor = vec4(col, 1.0);
}
