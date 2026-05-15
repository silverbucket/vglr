#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float stereo_width;
uniform float param_a;  // base distortion strength
uniform float param_b;  // chromatic aberration split
uniform float param_c;  // vignette darkness

in vec2 uv;
out vec4 fragColor;

vec2 barrelUV(vec2 uv, float k, float aspect) {
    vec2 p = (uv - 0.5) * vec2(aspect, 1.0);
    float r2 = dot(p, p);
    p *= 1.0 + k * r2 + k * 0.4 * r2 * r2;
    p /= vec2(aspect, 1.0);
    return p + 0.5;
}

void main() {
    float aspect = resolution.x / resolution.y;

    // Distortion strength: param_a sets base, bass surges, beat fires a shockwave
    // Shockwave: sharp kick that decays with the beat envelope
    float shock  = beat * 1.8 * exp(-beat * 2.5);
    float k      = 0.08 + param_a * 0.5 + bass * 0.4 + shock;

    // Chromatic aberration: R pushed out harder, B pulled in softer
    float split  = param_b * 0.6 + mid * 0.15;
    float kR = k * (1.0 + split);
    float kG = k;
    float kB = k * (1.0 - split * 0.5);

    // stereo_width drives an asymmetric horizontal pull (spatial/dynamic content)
    float asymX = stereo_width * 0.015 * sin(time * 2.5);

    vec2 uvR = barrelUV(uv + vec2( asymX, 0.0), kR, aspect);
    vec2 uvG = barrelUV(uv,                      kG, aspect);
    vec2 uvB = barrelUV(uv - vec2( asymX, 0.0), kB, aspect);

    // Clamp to edge to avoid sampling outside texture
    uvR = clamp(uvR, 0.001, 0.999);
    uvG = clamp(uvG, 0.001, 0.999);
    uvB = clamp(uvB, 0.001, 0.999);

    float r = texture(video, uvR).r;
    float g = texture(video, uvG).g;
    float b = texture(video, uvB).b;
    vec3 col = vec3(r, g, b);

    // Treble adds fine prismatic fringing near edges
    float distFromCenter = length(uv - 0.5);
    float prism = treble * 0.5 * distFromCenter * distFromCenter;
    col.r += prism * 0.3;
    col.b -= prism * 0.2;

    // Vignette: darkens edges, pulses with bass
    float vignette = 1.0 - distFromCenter * (1.5 + param_c * 1.5 + bass * 0.5);
    col *= clamp(vignette, 0.0, 1.0);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
