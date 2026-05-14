#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // segment count: 0=2-fold, 1=8-fold (beat adds more)
uniform float param_b;  // rotation speed
uniform float param_c;  // zoom (0=wide, 1=tight)

in vec2 uv;
out vec4 fragColor;

void main() {
    float aspect = resolution.x / resolution.y;

    vec2 p = uv - 0.5;
    p.x *= aspect;

    // Zoom: param_c pulls in, mid pulses it
    float zoom = 1.0 / (0.4 + param_c * 0.8 + mid * 0.25);
    p *= zoom;

    // Continuous rotation driven by bass and param_b
    float rot = time * (0.08 + param_b * 0.4) * (1.0 + bass * 1.5);
    float sr = sin(rot), cr = cos(rot);
    p = vec2(p.x * cr - p.y * sr, p.x * sr + p.y * cr);

    // Polar coordinates
    float r = length(p);
    float a = atan(p.y, p.x);

    // Segment count: base from param_a, beat snaps to higher counts then decays back
    float segs = 2.0 + floor(param_a * 6.0) + floor(beat * 4.0);
    float slice = 3.14159265 / segs;

    // Fold angle into one segment, then mirror
    a = mod(a, 2.0 * slice);
    if (a > slice) a = 2.0 * slice - a;

    // Back to cartesian and UV space
    vec2 q = vec2(r * cos(a), r * sin(a));
    q.x /= aspect;
    q += 0.5;

    vec3 col = texture(video, fract(q)).rgb;
    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
