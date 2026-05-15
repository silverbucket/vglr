#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // cell scale: 0=large shards, 1=fine fragments
uniform float param_b;  // displacement: how far each shard samples off-axis
uniform float param_c;  // crack width

in vec2 uv;
out vec4 fragColor;

vec2 hash2(vec2 p) {
    vec2 q = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(q) * 43758.5453);
}
float hash1(vec2 p) { return hash2(p).x; }

void main() {
    float aspect = resolution.x / resolution.y;
    float scale  = 2.0 + param_a * 10.0;

    vec2 p     = uv * vec2(scale * aspect, scale);
    vec2 cell  = floor(p);
    vec2 local = fract(p);

    float minD  = 1e9;
    float minD2 = 1e9;
    vec2  bestHash    = vec2(0.0);
    vec2  bestCell    = vec2(0.0);
    vec2  bestSeedPos = vec2(0.0);

    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 nb   = cell + vec2(float(i), float(j));
            vec2 base = hash2(nb);

            vec2 seed = vec2(float(i), float(j)) + base
                + 0.28 * vec2(
                    sin(time * (0.26 + base.x * 0.65)),
                    cos(time * (0.19 + base.y * 0.58))
                )
                + beat * 0.55 * (hash2(nb + vec2(3.7, 9.1)) * 2.0 - 1.0);

            float d = length(local - seed);
            if (d < minD) {
                minD2       = minD;
                minD        = d;
                bestHash    = base;
                bestCell    = nb;
                bestSeedPos = seed;
            } else if (d < minD2) {
                minD2 = d;
            }
        }
    }

    // Sample video at this cell's center to get its luminance (video-responsive damage)
    vec2 cellCtrUV = (bestCell + bestHash) / vec2(scale * aspect, scale);
    cellCtrUV.x   /= aspect;
    float cellLum  = dot(texture(video, fract(cellCtrUV)).rgb, vec3(0.299, 0.587, 0.114));

    // Bright/detailed cells shatter more; quiet dark areas stay calm
    float damage = clamp(cellLum * 1.9 + bass * 0.5, 0.0, 1.0);

    // Displace sample UV by cell offset, scaled by damage
    float disp    = (param_b * 0.07 + bass * 0.04) * damage;
    vec2  localOff = local - bestSeedPos;
    vec2  sampleUV = fract(uv + localOff * disp / vec2(scale * aspect, scale));
    vec3  col      = texture(video, sampleUV).rgb;

    // Heavy desaturation — dirty, worn palette
    float grey = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(grey), col, 0.22 + (1.0 - damage) * 0.28);

    // Per-cell damage behaviors, chosen by cell hash
    float behavior = hash1(bestCell + vec2(99.1, 13.3));
    if (behavior < 0.25 && damage > 0.38) {
        // Horizontal scan-line corruption
        float scanLine = step(0.5, fract((uv.y * scale - bestSeedPos.y) * 28.0));
        col *= mix(1.0, 0.5, scanLine * damage * 0.85);
    } else if (behavior < 0.5 && damage > 0.52) {
        // RGB channel swap
        col = col.brg;
    } else if (behavior < 0.72 && damage > 0.44) {
        // Partial inversion
        col = mix(col, 1.0 - col, damage * 0.65);
    }

    // Cell brightness variation (faceted-glass feel)
    col *= 0.55 + bestHash.x * 0.75;

    // Dark crack lines — rust/brown, not neon
    float edgeW   = 0.025 + param_c * 0.085 + beat * 0.035;
    float crackE  = 1.0 - smoothstep(0.0, edgeW, minD2 - minD);
    vec3  crackCol = vec3(0.20, 0.09, 0.04) * (0.35 + treble * 0.65);
    col = mix(col, crackCol, crackE * 0.88);

    // Treble shiver at crack edges
    float shiver = treble * 0.28 * sin(time * 30.0 + uv.x * 47.0 + uv.y * 32.0);
    col += crackCol * crackE * max(shiver, 0.0);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
