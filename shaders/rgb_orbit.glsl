#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // base orbit radius
uniform float param_b;  // oscillation speed
uniform float param_c;  // phase spread (0=tight, 1=120° apart)

in vec2 uv;
out vec4 fragColor;

void main() {
    float aspect = resolution.x / resolution.y;
    float spread = 2.094395 * (0.2 + param_c * 0.8);
    float base_r = param_a * 0.16;

    // Orbit angle oscillates — channels swing back and forth rather than spin.
    // Quiet = barely moving; loud bass/beat = wide arcing sweeps.
    float energy = bass * 2.0 + beat * 1.5;
    float angle  = sin(time * (0.25 + param_b * 0.8)) * (0.8 + energy * 1.6);

    float r_r = base_r + bass   * 0.24 + beat * 0.10;
    float r_g = base_r + mid    * 0.18 + beat * 0.06;
    float r_b = base_r + treble * 0.16 + beat * 0.08;

    vec2 off_r = vec2(cos(angle             ) * r_r / aspect, sin(angle             ) * r_r);
    vec2 off_g = vec2(cos(angle + spread    ) * r_g / aspect, sin(angle + spread    ) * r_g);
    vec2 off_b = vec2(cos(angle + spread*2.0) * r_b / aspect, sin(angle + spread*2.0) * r_b);

    float r = texture(video, fract(uv + off_r)).r;
    float g = texture(video, fract(uv + off_g)).g;
    float b = texture(video, fract(uv + off_b)).b;

    fragColor = mix(texture(video, uv), vec4(r, g, b, 1.0), intensity);
}
