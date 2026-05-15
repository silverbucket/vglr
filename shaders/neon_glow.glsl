#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;
uniform float intensity;
uniform float param_a;  // edge threshold: 0=subtle edges, 1=only sharp contours
uniform float param_b;  // glow spread
uniform float param_c;  // video bleed: 0=black bg, 1=dim video visible

in vec2 uv;
out vec4 fragColor;

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec3 L = vec3(0.299, 0.587, 0.114);
    float s = (1.5 + param_b * 7.0 + bass * 4.0) / min(resolution.x, resolution.y);

    // Sobel gradient — gives edge magnitude AND direction
    vec3 tl = texture(video, uv + vec2(-s,  s)).rgb;
    vec3 tr = texture(video, uv + vec2( s,  s)).rgb;
    vec3 bl = texture(video, uv + vec2(-s, -s)).rgb;
    vec3 br = texture(video, uv + vec2( s, -s)).rgb;
    vec3 l_ = texture(video, uv + vec2(-s,  0)).rgb;
    vec3 r_ = texture(video, uv + vec2( s,  0)).rgb;
    vec3 t_ = texture(video, uv + vec2( 0,  s)).rgb;
    vec3 b_ = texture(video, uv + vec2( 0, -s)).rgb;

    float gx = dot(-tl - 2.0*l_ - bl + tr + 2.0*r_ + br, L);
    float gy = dot( tl + 2.0*t_ + tr - bl - 2.0*b_ - br, L);
    float mag = length(vec2(gx, gy));

    // Edge angle → one of 4 chemical neon hues (not a smooth rainbow)
    float angle  = atan(gy, gx);              // -PI..PI
    float sector = fract(angle / 6.2832 + 0.5);

    vec3 neonA, neonB;
    if (sector < 0.25)      { neonA = vec3(1.0, 0.04, 0.4);  neonB = vec3(0.0, 1.0, 0.85); }
    else if (sector < 0.5)  { neonA = vec3(0.0, 1.0, 0.85);  neonB = vec3(0.7, 1.0, 0.0);  }
    else if (sector < 0.75) { neonA = vec3(0.7, 1.0, 0.0);   neonB = vec3(1.0, 0.45, 0.0); }
    else                    { neonA = vec3(1.0, 0.45, 0.0);  neonB = vec3(1.0, 0.04, 0.4); }

    // Mid shifts palette slowly between adjacent neon colours
    vec3 neon = mix(neonA, neonB, mid * 0.45 * sin(time * 0.71));

    // Edge threshold
    float thresh = 0.12 - param_a * 0.10;
    float edge   = pow(clamp((mag - thresh) / (0.5 - thresh + 0.01), 0.0, 1.0), 0.65);

    // 8-12 Hz cathode buzz, treble-amplified
    float buzzHz  = 8.0 + treble * 4.0;
    float buzz    = 1.0 + treble * 2.0 * (0.5 + 0.5 * sin(time * buzzHz * 6.2832));

    // Cathode sweep line re-excites edges along its path
    float sweepY = fract(time * 0.35 + mid * 0.12);
    float sweep  = smoothstep(0.035, 0.0, abs(uv.y - sweepY)) * (0.6 + bass * 0.9);
    float edgeFull = max(edge, sweep * 0.4);

    vec3 col = neon * edgeFull * (2.2 + beat * 3.8) * buzz;

    // Beat: blow all edges white
    col = mix(col, vec3(1.0) * edgeFull * 5.0, beat * 0.45);

    // Phosphor-green grain on dark areas
    float lum     = dot(texture(video, uv).rgb, L);
    float grain   = hash(uv * resolution + vec2(floor(time * 60.0), 0.0));
    float phosphor = grain * 0.14 * (1.0 - smoothstep(0.0, 0.28, lum));
    vec3 bg = texture(video, uv).rgb * (0.05 + param_c * 0.2)
            + vec3(0.0, phosphor * 0.7, phosphor * 0.4);

    col = clamp(bg + col, 0.0, 1.0);

    fragColor = mix(texture(video, uv), vec4(col, 1.0), intensity);
}
