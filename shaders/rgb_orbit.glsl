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
uniform float param_b;  // orbit speed
uniform float param_c;  // phase spread between channels (0=tight, 1=120° apart)

in vec2 uv;
out vec4 fragColor;

void main() {
    float aspect  = resolution.x / resolution.y;
    float speed   = time * (0.5 + param_b * 2.0);
    float spread  = 2.094395 * (0.2 + param_c * 0.8);  // up to 120° (2π/3)
    float base_r  = param_a * 0.18;

    // Each channel orbit radius driven by its frequency band + beat
    float r_r = base_r + bass   * 0.28 + beat * 0.08;
    float r_g = base_r + mid    * 0.22 + beat * 0.06;
    float r_b = base_r + treble * 0.20 + beat * 0.10;

    // Offsets: circle in UV space (corrected for aspect)
    vec2 off_r = vec2(cos(speed              ) * r_r / aspect, sin(speed              ) * r_r);
    vec2 off_g = vec2(cos(speed + spread     ) * r_g / aspect, sin(speed + spread     ) * r_g);
    vec2 off_b = vec2(cos(speed + spread*2.0 ) * r_b / aspect, sin(speed + spread*2.0 ) * r_b);

    float r = texture(video, fract(uv + off_r)).r;
    float g = texture(video, fract(uv + off_g)).g;
    float b = texture(video, fract(uv + off_b)).b;

    fragColor = mix(texture(video, uv), vec4(r, g, b, 1.0), intensity);
}
