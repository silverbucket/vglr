#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // segment count base (0=2-fold, 1=8-fold)
uniform float param_b;  // rotation sway amount
uniform float param_c;  // zoom (0=wide, 1=tight)

in vec2 uv;
out vec4 fragColor;

void main() {
    float aspect = resolution.x / resolution.y;

    vec2 p = uv - 0.5;
    p.x *= aspect;

    // Zoom breathes with bass
    float zoom = 1.0 / (0.4 + param_c * 0.7 + bass * 0.3);
    p *= zoom;

    // Rotation oscillates instead of spinning continuously.
    // Slow pendulum base + bass-driven faster oscillation + beat kick.
    float sway  = sin(time * 0.18) * (0.6 + param_b * 1.2);
    float pulse = bass * sin(time * 3.5) * 1.5;
    float rot   = sway + pulse + beat * 1.8;
    float sr = sin(rot), cr = cos(rot);
    p = vec2(p.x * cr - p.y * sr, p.x * sr + p.y * cr);

    float r = length(p);
    float a = atan(p.y, p.x);

    // Segment count: base from param_a, beat snaps to higher count then decays
    float segs  = 2.0 + floor(param_a * 6.0) + floor(beat * 3.0);
    float slice = 3.14159265 / segs;

    a = mod(a, 2.0 * slice);
    if (a > slice) a = 2.0 * slice - a;

    // Treble stretches segments radially, giving a pulsing fringe on hi-hats
    r *= 1.0 + treble * 0.35 * sin(time * 8.0 + a * 4.0);

    vec2 q = vec2(r * cos(a), r * sin(a));
    q.x /= aspect;
    q += 0.5;

    vec3 col = texture(video, fract(q)).rgb;
    col.r *= 1.0 + beat * 0.4;
    col.b *= 1.0 + beat * 0.25;
    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
