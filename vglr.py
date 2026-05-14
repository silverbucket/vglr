#!/usr/bin/env python3
"""vglr — step 5a: moderngl-window + static test pattern."""
import numpy as np
import moderngl
import moderngl_window as mglw

VERT = """
#version 140
in vec2 in_position;
out vec2 uv;
void main() {
    uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FRAG = """
#version 140
uniform float time;
in vec2 uv;
out vec4 fragColor;
void main() {
    float r = 0.5 + 0.5 * sin(time + uv.x * 6.28318);
    float g = 0.5 + 0.5 * sin(time * 1.3 + uv.y * 6.28318);
    float b = 0.5 + 0.5 * sin(time * 0.7 + (uv.x + uv.y) * 3.14159);
    fragColor = vec4(r, g, b, 1.0);
}
"""

QUAD = np.array([
    -1.0,  1.0,
    -1.0, -1.0,
     1.0,  1.0,
     1.0, -1.0,
], dtype='f4')


class VGLRApp(mglw.WindowConfig):
    title = "vglr"
    gl_version = (3, 1)
    window_size = (1920, 1080)
    resizable = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prog = self.ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
        vbo = self.ctx.buffer(QUAD)
        self.vao = self.ctx.vertex_array(self.prog, [(vbo, '2f', 'in_position')])

    def on_render(self, time, frametime):
        self.ctx.clear()
        self.prog['time'].value = time
        self.vao.render(moderngl.TRIANGLE_STRIP)

    def key_event(self, key, action, modifiers):
        if action == self.wnd.keys.ACTION_PRESS and key == self.wnd.keys.Q:
            self.wnd.close()


if __name__ == '__main__':
    mglw.run_window_config(VGLRApp)
