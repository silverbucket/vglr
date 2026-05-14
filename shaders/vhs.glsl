#version 140

uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;
uniform float mid;
uniform float treble;
uniform float beat;

in vec2 uv;
out vec4 fragColor;

vec3 rgb2yiq(vec3 c) {
    return vec3(
        0.2989*c.r + 0.5959*c.g + 0.2115*c.b,
        0.5870*c.r - 0.2744*c.g - 0.5229*c.b,
        0.1140*c.r - 0.3216*c.g + 0.3114*c.b
    );
}

vec3 yiq2rgb(vec3 c) {
    return vec3(
        1.0*c.r   +  1.0*c.g    +  1.0*c.b,
        0.956*c.r -  0.2720*c.g - 1.1060*c.b,
        0.6210*c.r - 0.6474*c.g + 1.7046*c.b
    );
}

vec2 Circle(float Start, float Points, float Point) {
    float Rad = (3.141592 * 2.0 * (1.0 / Points)) * (Point + Start);
    return vec2(-(.3+Rad), cos(Rad));
}

vec3 Blur(vec2 p, float d, float rf) {
    vec2 Scale = 0.66 * 4.0 * 2.0 * vec2(d + 0.0005, 0.0) * rf;
    float Start = 2.0 / 14.0;
    float W = 1.0 / 15.0;
    vec3 col =
        texture(video, p + Circle(Start, 14.0,  0.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  1.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  2.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  3.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  4.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  5.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  6.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  7.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  8.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0,  9.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0, 10.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0, 11.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0, 12.0) * Scale).rgb +
        texture(video, p + Circle(Start, 14.0, 13.0) * Scale).rgb +
        texture(video, p).rgb;
    return col * W;
}

float onOff(float a, float b, float c, float framecount) {
    return step(c, sin((framecount * 0.001) + a*cos((framecount * 0.001)*b)));
}

vec2 jumpy(vec2 p, float framecount, float wiggle, float rf) {
    float window = 1.0/(1.0+80.0*(p.y-mod(framecount/4.0,1.0))*(p.y-mod(framecount/4.0,1.0)));
    p.x += 0.05 * sin(p.y*10.0 + framecount)/20.0 * onOff(4.0,4.0,0.3,framecount)
           * (0.5+cos(framecount*20.0)) * window * rf;
    float vShift = (0.1*wiggle) * 0.4 * onOff(2.0,3.0,0.9,framecount)
                   * (sin(framecount)*sin(framecount*20.0)
                   + (0.5 + 0.1*sin(framecount*200.0)*cos(framecount)));
    p.y = mod(p.y - 0.01 * vShift, 1.0);
    return p;
}

void main() {
    float rf = min(resolution.y / 1080.0, 1.0);

    // audio modulation: bass drives wiggle, mid drives smear, beat spikes wiggle
    float wiggle = 3.0 * rf * (1.0 + bass * 3.0) + beat * 4.0 * rf;
    float smear  = 0.5 * rf * (1.0 + mid * 2.0 + treble * 3.0);

    float framecount = time * 60.0;
    float d = 0.1 - ceil(mod(time/3.0, 1.0) + 0.5) * 0.1;

    vec2 p = jumpy(uv, framecount, wiggle, rf);
    float s = 0.0001 * -d + 0.0001 * wiggle * sin(time);
    float e = min(0.30, pow(max(0.0, cos(p.y*4.0+0.3)-0.75)*(s+0.5), 3.0)) * 25.0 * rf;
    p.x += abs(s * pow(min(0.003, (-p.y + (0.01*mod(time, 17.0)))*3.0), 2.0)) * rf;
    float c = max(0.0001, 0.002*d) * smear * rf;

    d = 0.051 + abs(sin(s/4.0));

    vec4 final;
    final.rgb = Blur(p, c + c*p.x, rf);
    float y = rgb2yiq(final.rgb).r;

    p.x += 0.01*d;
    c *= 6.0;
    final.rgb = Blur(p, c, rf);
    float iq_i = rgb2yiq(final.rgb).g;

    p.x += 0.005*d;
    c *= 2.50;
    final.rgb = Blur(p, c, rf);
    float iq_q = rgb2yiq(final.rgb).b;

    fragColor = vec4(yiq2rgb(vec3(y, iq_i, iq_q)) - pow(s + e*2.0, 3.0), 1.0);
}
