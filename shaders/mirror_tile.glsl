#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // crop window size (0=tiny detail slice, 1=half-frame)
uniform float param_b;  // tile count (0=2 tiles across, 1=16 tiles across)
uniform float param_c;  // per-tile colour tint intensity

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
float hash1(float x) { return fract(sin(x * 127.1) * 43758.5453); }

vec2 lissajousCentre(float t, float bassVal, float midVal, float beatVal) {
    return vec2(
        0.5 + sin(t * (0.27 + bassVal * 0.45)) * (0.22 + beatVal * 0.12),
        0.5 + cos(t * (0.19 + midVal  * 0.35)) * 0.22
    );
}

void main() {
    float tileCount = 2.0 + floor(param_b * 14.0);
    float tileSize  = 1.0 / tileCount;

    vec2 tileID  = floor(uv / tileSize);
    vec2 localUV = fract(uv / tileSize);

    // Mirror alternate tiles
    if (mod(tileID.x, 2.0) >= 1.0) localUV.x = 1.0 - localUV.x;
    if (mod(tileID.y, 2.0) >= 1.0) localUV.y = 1.0 - localUV.y;

    // Base Lissajous crop centre
    vec2 lissBase = lissajousCentre(time, bass, mid, beat);

    // Stochastic jump: crop snaps to a random point, exponentially returns to Lissajous
    float epochLen  = 2.2 + hash1(floor(time * 0.12) * 5.7) * 2.8;  // 2.2–5s
    float jumpEpoch = floor(time / epochLen);
    float jumpAge   = fract(time / epochLen);
    vec2  jumpTarget = hash2(vec2(jumpEpoch, 37.5));
    float blend      = 1.0 - exp(-jumpAge * 4.8);
    vec2  cropCentre = mix(jumpTarget, lissBase, blend);

    // Lagged crop centre: one epoch behind (some tiles show temporal ghost)
    float lagEpoch  = jumpEpoch - 1.0;
    float lagAge    = jumpAge + 1.0;
    vec2  lagTarget  = hash2(vec2(lagEpoch, 37.5));
    vec2  lagCentre  = mix(lagTarget, lissBase, 1.0 - exp(-lagAge * 4.8));

    // Per-tile properties
    float rotPhase = dot(tileID, vec2(0.37, 0.61));
    float tileHash = hash1(rotPhase + 1.3);

    // Tile variants: 90° rotate or 180° flip based on tile hash
    if (tileHash > 0.84) {
        localUV = 1.0 - localUV;                          // 180° flip
    } else if (tileHash > 0.70) {
        localUV = vec2(1.0 - localUV.y, localUV.x);       // 90° rotation
    }

    // Lag tiles: ~30% show previous crop position (temporal smear effect)
    bool  useLag     = tileHash > 0.68 && tileHash < 0.82;
    vec2  activeCrop = useLag ? lagCentre : cropCentre;

    // Per-tile rotation (treble shimmer)
    float rot = treble * 0.35 * sin(time * 2.5 + rotPhase * 3.14);
    float sr = sin(rot), cr_ = cos(rot);
    vec2  lc = localUV - 0.5;
    lc = vec2(lc.x * cr_ - lc.y * sr, lc.x * sr + lc.y * cr_);

    float cropSize = tileSize * (0.5 + param_a * 2.5);
    vec2 sampleUV  = activeCrop + lc * cropSize;

    vec3 col = texture(video, fract(sampleUV)).rgb;

    // Per-tile colour tint
    float tileHue = fract(rotPhase + beat * 0.4 + time * 0.025);
    vec3  tint    = hsv2rgb(vec3(tileHue, 0.65, 1.0));
    col = mix(col, col * tint, param_c);

    // Lag tiles: slight desaturation hints at temporal distance
    if (useLag) {
        float grey = dot(col, vec3(0.333));
        col = mix(col, vec3(grey), 0.45);
    }

    // Beat: complementary flash
    col = mix(col, 1.0 - col, beat * 0.25);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
