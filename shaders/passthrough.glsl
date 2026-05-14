#version 140

uniform sampler2D video;

in vec2 uv;
out vec4 fragColor;

void main() {
    fragColor = texture(video, uv);
}
