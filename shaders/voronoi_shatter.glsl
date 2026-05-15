#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // cell scale: 0=large chunks, 1=fine shards
uniform float param_b;  // cell displacement: how far each shard samples off-axis
uniform float param_c;  // edge glow width

in vec2 uv;
out vec4 fragColor;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

vec2 hash2(vec2 p) {
    vec2 q = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(q) * 43758.5453);
}

void main() {
    float aspect = resolution.x / resolution.y;
    float scale  = 2.0 + param_a * 9.0;

    vec2 p    = uv * vec2(scale * aspect, scale);
    vec2 cell = floor(p);
    vec2 local = fract(p);

    float minD  = 1e9;
    float minD2 = 1e9;
    vec2  minHash    = vec2(0.0);
    vec2  minSeedOff = vec2(0.0);

    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 nb   = cell + vec2(float(i), float(j));
            vec2 base = hash2(nb);

            // Seeds drift on Lissajous paths driven by bass/mid, jump on beat
            vec2 seed = vec2(float(i), float(j)) + base
                + 0.38 * vec2(
                    sin(time * (0.35 + base.x * 0.9) + bass * 2.8),
                    cos(time * (0.28 + base.y * 0.7) + mid  * 2.2)
                )
                + beat * 0.45 * (hash2(nb + vec2(7.3, 13.7)) * 2.0 - 1.0);

            float d = length(local - seed);
            if (d < minD) {
                minD2      = minD;
                minD       = d;
                minHash    = base;
                minSeedOff = local - seed;
            } else if (d < minD2) {
                minD2 = d;
            }
        }
    }

    // Sample video displaced by the cell's seed offset (each shard looks sideways)
    float disp    = param_b * 0.07 + bass * 0.045;
    vec2 sampleUV = fract(uv + minSeedOff * disp / vec2(scale * aspect, scale));
    vec3 col      = texture(video, sampleUV).rgb;

    // Brightness varies per cell for a faceted-glass look
    col *= 0.55 + minHash.x * 0.9;

    // Neon edge glow at cell boundaries (minD2 - minD ≈ 0 at borders)
    float edgeW   = 0.04 + param_c * 0.12 + beat * 0.06;
    float edge    = 1.0 - smoothstep(0.0, edgeW, minD2 - minD);
    float edgeHue = fract(minHash.x + time * 0.18 + beat * 0.25);
    vec3  edgeCol = hsv2rgb(vec3(edgeHue, 1.0, 1.0));
    col = mix(col, edgeCol, edge * (0.6 + beat * 0.6) * intensity);

    // Treble makes edge glow flicker
    col += edgeCol * edge * treble * 0.4 * sin(time * 35.0 + uv.x * 60.0);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
