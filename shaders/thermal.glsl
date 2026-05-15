#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // palette: 0=fire, 1=ice/neon
uniform float param_b;  // bloom spread
uniform float param_c;  // heat threshold: lower = more of the image burns

in vec2 uv;
out vec4 fragColor;

vec3 firePalette(float t) {
    t = clamp(t, 0.0, 1.0);
    if (t < 0.2) return mix(vec3(0.0),              vec3(0.15, 0.0,  0.3),  t * 5.0);
    if (t < 0.4) return mix(vec3(0.15, 0.0,  0.3),  vec3(0.8,  0.05, 0.05), (t - 0.2) * 5.0);
    if (t < 0.6) return mix(vec3(0.8,  0.05, 0.05), vec3(1.0,  0.4,  0.0),  (t - 0.4) * 5.0);
    if (t < 0.8) return mix(vec3(1.0,  0.4,  0.0),  vec3(1.0,  0.9,  0.1),  (t - 0.6) * 5.0);
    return             mix(vec3(1.0,  0.9,  0.1),  vec3(1.0,  1.0,  1.0),  (t - 0.8) * 5.0);
}

vec3 icePalette(float t) {
    t = clamp(t, 0.0, 1.0);
    if (t < 0.25) return mix(vec3(0.0),              vec3(0.0,  0.05, 0.25), t * 4.0);
    if (t < 0.5)  return mix(vec3(0.0,  0.05, 0.25), vec3(0.0,  0.4,  0.85), (t - 0.25) * 4.0);
    if (t < 0.75) return mix(vec3(0.0,  0.4,  0.85), vec3(0.5,  1.0,  1.0),  (t - 0.5)  * 4.0);
    return              mix(vec3(0.5,  1.0,  1.0),  vec3(1.0,  1.0,  1.0),  (t - 0.75) * 4.0);
}

void main() {
    vec3 L = vec3(0.299, 0.587, 0.114);
    float spread = 0.005 + param_b * 0.025 + bass * 0.025;

    // 5-tap cross bloom: max luminance within spread radius
    float lum = dot(texture(video, uv).rgb, L);
    lum = max(lum, dot(texture(video, uv + vec2( spread,  0.0  )).rgb, L));
    lum = max(lum, dot(texture(video, uv + vec2(-spread,  0.0  )).rgb, L));
    lum = max(lum, dot(texture(video, uv + vec2( 0.0,     spread)).rgb, L));
    lum = max(lum, dot(texture(video, uv + vec2( 0.0,    -spread)).rgb, L));

    // Heat: raise the floor so more of the image burns
    float thresh = 0.30 - param_c * 0.28;
    float heat   = clamp((lum - thresh) / (1.0 - thresh + 0.01), 0.0, 1.0);

    // Beat flashes the frame toward white-hot
    heat = min(heat + beat * 0.4, 1.0);

    vec3 fire = firePalette(heat);
    vec3 ice  = icePalette(heat);
    vec3 col  = mix(fire, ice, param_a);

    // Mid oscillates a subtle complementary hue sweep
    col = mix(col, col.bgr, mid * 0.22 * sin(time * 4.5 + uv.y * 8.0));

    // Treble flickers bright pixels
    col += treble * 0.15 * heat * heat * vec3(1.0, 0.9, 0.7) * sin(time * 30.0 + uv.x * 40.0);

    fragColor = mix(texture(video, uv), vec4(clamp(col, 0.0, 1.0), 1.0), intensity);
}
