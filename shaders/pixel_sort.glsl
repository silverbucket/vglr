#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // brightness threshold: 0=only darkest fall, 1=everything falls
uniform float param_b;  // fall distance (how far pixels cascade)
uniform float param_c;  // column width: 0=1px, 1=24px wide columns

in vec2 uv;
out vec4 fragColor;

float hash(float n) { return fract(sin(n) * 43758.5453); }

void main() {
    // Quantise x into columns
    float col_px = mix(1.0, 24.0, param_c);
    float col_w  = col_px / resolution.x;
    float col_id = floor(uv.x / col_w);
    float col_x  = (col_id + 0.5) * col_w;

    // Per-column random speed; reseeds slowly + on beat
    float rnd = hash(col_id * 1.618 + floor(time * 0.3 + beat * 4.0) * 7.3);

    vec3  orig  = texture(video, uv).rgb;
    float luma  = dot(orig, vec3(0.299, 0.587, 0.114));

    // Dark pixels cascade downward, pulling the bright pixel from above them
    float thresh    = 0.08 + param_a * 0.70;
    float max_fall  = (param_b * 0.55 + bass * 0.35 + beat * 0.20) * rnd;
    float fall      = (luma < thresh) ? max_fall * (thresh - luma) / thresh : 0.0;

    vec2 src = vec2(col_x, mod(uv.y - fall, 1.0));
    vec3 col = texture(video, src).rgb;

    // Cool-blue tint on sorted (displaced) regions
    float sorted = step(0.01, fall);
    col = mix(col, col * vec3(0.85, 0.92, 1.12) + treble * 0.04, sorted * 0.45);

    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
