#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // twist strength
uniform float param_b;  // falloff sharpness (0=even warp, 1=inner-only)
uniform float param_c;  // sway speed

in vec2 uv;
out vec4 fragColor;

void main() {
    float aspect = resolution.x / resolution.y;
    vec2 p = uv - 0.5;
    p.x *= aspect;

    float r = length(p);
    float a = atan(p.y, p.x);

    float falloff = 1.0 / (1.0 + r * r * (5.0 + param_b * 35.0));

    // No constant spin. Oscillating sway + audio surges.
    float base_sway = sin(time * (0.2 + param_c * 0.5)) * (param_a * 6.0 + 0.5);
    float bass_push = bass * 7.0 * sin(time * 4.0 + r * 3.0);
    float beat_kick = beat * 5.0;
    float twist = (base_sway + bass_push + beat_kick) * falloff;

    // Mid adds a ripple across the radius — feels like the image is breathing
    twist += mid * 1.5 * sin(r * 12.0 - time * 5.0) * falloff;

    a += twist;

    vec2 q = vec2(r * cos(a), r * sin(a));
    q.x /= aspect;
    q += 0.5;

    vec3 col = texture(video, fract(q)).rgb;
    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
