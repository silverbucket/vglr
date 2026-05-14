#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // strip height: 0=thin (2px), 1=thick (32px)
uniform float param_b;  // drip speed
uniform float param_c;  // chaos: 0=uniform drip, 1=every strip its own pace

in vec2 uv;
out vec4 fragColor;

float hash(float n) { return fract(sin(n) * 43758.5453); }

void main() {
    float strip_px = mix(2.0, 32.0, param_a);
    float strip_h  = strip_px / resolution.y;
    float strip_id = floor(uv.y / strip_h);

    // Per-strip random speed factor
    float rnd        = hash(strip_id * 1.618);
    float speed_mult = mix(1.0, 0.1 + rnd * 5.0, param_c);

    // Total drip offset: time-driven + beat lurches strips
    float rate   = param_b * 0.3 + bass * 0.25;
    float drip   = rate * speed_mult * time + beat * 0.18 * rnd;

    // Scroll y, wrapping at top/bottom so it tiles seamlessly
    float src_y  = fract(uv.y - drip);

    // Boundary tear: adjacent strips at different speeds pull apart
    float next_rnd   = hash((strip_id + 1.0) * 1.618);
    float next_mult  = mix(1.0, 0.1 + next_rnd * 5.0, param_c);
    float next_drip  = rate * next_mult * time;
    float boundary   = fract(uv.y / strip_h);
    float tear       = smoothstep(0.80, 1.0, boundary) * abs(drip - next_drip) * 2.5;
    src_y = fract(src_y + tear * 0.035);

    // Subtle horizontal wobble proportional to mid/bass
    float wobble = sin(strip_id * 6.1 + time * 3.5) * 0.003 * (mid + bass * 0.4);

    vec3 col = texture(video, vec2(uv.x + wobble, src_y)).rgb;

    // Heat glow at tear boundaries (warm colour splash)
    col += vec3(tear * bass * 0.55, tear * 0.12, tear * treble * 0.35);

    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
