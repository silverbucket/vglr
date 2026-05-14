#!/usr/bin/env python3
"""vglr — step 5b: PyAV video decode → texture."""
import queue
import threading
import numpy as np
import moderngl
import moderngl_window as mglw
import av

VIDEO_PATH = 'videos/fb_rev_wet_mop_reimagined.mp4'

# Read video metadata before GL init
with av.open(VIDEO_PATH) as _c:
    _s = _c.streams.video[0]
    VIDEO_W, VIDEO_H = _s.width, _s.height
    VIDEO_FPS = float(_s.average_rate or _s.guessed_rate or 30)

frame_queue: queue.Queue = queue.Queue(maxsize=4)


def decode_loop(path: str) -> None:
    while True:
        with av.open(path) as container:
            for frame in container.decode(video=0):
                frame_queue.put(frame.to_ndarray(format='rgb24'), block=True)


VERT = """
#version 140
in vec2 in_position;
out vec2 uv;
void main() {
    uv = vec2(in_position.x * 0.5 + 0.5, 1.0 - (in_position.y * 0.5 + 0.5));
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FRAG = """
#version 140
uniform sampler2D video;
in vec2 uv;
out vec4 fragColor;
void main() {
    fragColor = texture(video, uv);
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
        self.texture = self.ctx.texture((VIDEO_W, VIDEO_H), 3)
        self.prog['video'] = 0
        self.texture.use(location=0)
        self.frame_interval = 1.0 / VIDEO_FPS
        self.last_frame_time = 0.0
        threading.Thread(target=decode_loop, args=(VIDEO_PATH,), daemon=True).start()

    def on_render(self, time, frametime):
        self.ctx.clear()
        if time - self.last_frame_time >= self.frame_interval:
            try:
                frame = frame_queue.get_nowait()
                self.texture.write(frame.tobytes())
                self.last_frame_time = time
            except queue.Empty:
                pass
        self.vao.render(moderngl.TRIANGLE_STRIP)

    def key_event(self, key, action, modifiers):
        if action == self.wnd.keys.ACTION_PRESS and key == self.wnd.keys.Q:
            self.wnd.close()


if __name__ == '__main__':
    mglw.run_window_config(VGLRApp)
