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
uniform float param_b;  // displacement + blur intensity
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

    // Bass makes cells animate faster
    float bassAnim = 1.0 + smoothstep(0.1, 0.6, bass) * 2.5;

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
                    sin(time * (0.26 + base.x * 0.65) * bassAnim),
                    cos(time * (0.19 + base.y * 0.58) * bassAnim)
                )
                + beat * 1.2 * (hash2(nb + vec2(3.7, 9.1)) * 2.0 - 1.0);

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

    // Cell center luminance → damage
    vec2 cellCtrUV = (bestCell + bestHash) / vec2(scale * aspect, scale);
    cellCtrUV.x   /= aspect;
    float cellLum  = dot(texture(video, fract(cellCtrUV)).rgb, vec3(0.299, 0.587, 0.114));
    float damage   = clamp(cellLum * 1.6 + smoothstep(0.1, 0.6, bass) * 0.7 + beat * 0.4, 0.0, 1.0);

    // Displacement: param_b now directly in UV space (was divided by ~12, making it tiny)
    float disp    = (param_b * 0.18 + smoothstep(0.1, 0.6, bass) * 0.1) * damage;
    vec2  dispDir = normalize(local - bestSeedPos + vec2(0.001));
    vec2  sampleUV = fract(uv + dispDir * disp);
    vec3  col      = texture(video, sampleUV).rgb;

    // Bass blur: high bass = cells vibrate (4-tap jitter simulates motion blur)
    float blurAmt = smoothstep(0.2, 0.8, bass) * param_b * 0.8 + beat * 0.3;
    float bOff    = blurAmt * 0.025;
    vec3 blurred  = col;
    blurred += texture(video, fract(sampleUV + vec2( bOff,   0.0))).rgb;
    blurred += texture(video, fract(sampleUV + vec2(-bOff,   0.0))).rgb;
    blurred += texture(video, fract(sampleUV + vec2(  0.0,  bOff))).rgb;
    blurred += texture(video, fract(sampleUV + vec2(  0.0, -bOff))).rgb;
    col = mix(col, blurred / 5.0, clamp(blurAmt, 0.0, 1.0));

    // Moderate desaturation — keep colour proportional to bass energy
    float grey = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(grey), col, 0.45 + smoothstep(0.1, 0.7, bass) * 0.4);

    // Damage-based colour tint: olive-grey → amber → blood orange
    vec3 tint = mix(vec3(0.55, 0.52, 0.35),
                    vec3(0.75, 0.50, 0.20),
                    smoothstep(0.2, 0.6, damage));
    tint       = mix(tint,
                     vec3(0.90, 0.25, 0.05),
                     smoothstep(0.6, 1.0, damage));
    col = mix(col, col * tint, 0.45 + damage * 0.35);

    // Per-cell damage behaviours
    float behavior = hash1(bestCell + vec2(99.1, 13.3));
    if (behavior < 0.25 && damage > 0.38) {
        float scanLine = step(0.5, fract((uv.y * scale - bestSeedPos.y) * 28.0));
        col *= mix(1.0, 0.45, scanLine * damage * 0.9);
    } else if (behavior < 0.5 && damage > 0.52) {
        col = col.brg;
    } else if (behavior < 0.72 && damage > 0.44) {
        col = mix(col, 1.0 - col, damage * 0.6);
    }

    col *= 0.55 + bestHash.x * 0.75;

    // Crack lines: rust at rest, flare orange on beat
    float edgeW   = 0.025 + param_c * 0.085 + beat * 0.04;
    float crackE  = 1.0 - smoothstep(0.0, edgeW, minD2 - minD);
    vec3  crackCol = mix(vec3(0.20, 0.09, 0.04),
                         vec3(0.90, 0.45, 0.10),
                         beat * 0.85)
                   * (0.4 + treble * 0.6);
    col = mix(col, crackCol, crackE * 0.85);

    float shiver = treble * 0.30 * sin(time * 30.0 + uv.x * 47.0 + uv.y * 32.0);
    col += crackCol * crackE * max(shiver, 0.0);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
