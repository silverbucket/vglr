#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // twist strength (0=none, 1=full spiral)
uniform float param_b;  // falloff sharpness (0=even warp, 1=inner-only)
uniform float param_c;  // spin speed

in vec2 uv;
out vec4 fragColor;

void main() {
    float aspect = resolution.x / resolution.y;
    vec2 p = uv - 0.5;
    p.x *= aspect;

    float r = length(p);
    float a = atan(p.y, p.x);

    // Twist angle: strongest at center, falls off outward
    float falloff = 1.0 / (1.0 + r * r * (5.0 + param_b * 35.0));
    float twist   = (param_a * 8.0 + bass * 5.0) * falloff;

    // Beat causes a sharp inner burst that decays with the envelope
    twist += beat * 3.5 * falloff;

    // Continuous spin; mid subtly modulates the rate
    a += twist + time * (0.1 + param_c * 0.6) * (1.0 + mid * 0.4);

    vec2 q = vec2(r * cos(a), r * sin(a));
    q.x /= aspect;
    q += 0.5;

    vec3 col = texture(video, fract(q)).rgb;
    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
