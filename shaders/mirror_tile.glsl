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

void main() {
    float aspect    = resolution.x / resolution.y;
    float tileCount = 2.0 + floor(param_b * 14.0);    // 2..16 tiles across
    float tileSize  = 1.0 / tileCount;

    // Find which tile we're in and the local (0..1) position within it
    vec2 tileID  = floor(uv / tileSize);
    vec2 localUV = fract(uv / tileSize);

    // Mirror alternate tiles horizontally and vertically
    if (mod(tileID.x, 2.0) >= 1.0) localUV.x = 1.0 - localUV.x;
    if (mod(tileID.y, 2.0) >= 1.0) localUV.y = 1.0 - localUV.y;

    // Crop centre roams on a Lissajous path through the video
    float cx = 0.5 + sin(time * (0.27 + bass * 0.45)) * (0.22 + beat * 0.12);
    float cy = 0.5 + cos(time * (0.19 + mid  * 0.35)) * 0.22;
    vec2 cropCentre = vec2(cx, cy);

    // Crop size: param_a controls how much of the video each tile shows
    float cropSize = tileSize * (0.5 + param_a * 2.5);

    // Slight per-tile rotation driven by treble for shimmer
    float rotPhase = dot(tileID, vec2(0.37, 0.61));
    float rot      = treble * 0.35 * sin(time * 2.5 + rotPhase * 3.14);
    float sr = sin(rot), cr_ = cos(rot);
    vec2  lc = localUV - 0.5;
    lc = vec2(lc.x * cr_ - lc.y * sr, lc.x * sr + lc.y * cr_);

    vec2 sampleUV = cropCentre + lc * cropSize;

    vec3 col = texture(video, fract(sampleUV)).rgb;

    // Per-tile colour tint: each tile gets a unique hue from its grid position
    float tileHue = fract(rotPhase + beat * 0.4 + time * 0.025);
    vec3  tint    = hsv2rgb(vec3(tileHue, 0.65, 1.0));
    col = mix(col, col * tint, param_c);

    // Beat: snap to a new crop offset via a brief complementary flash
    col = mix(col, 1.0 - col, beat * 0.25);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
