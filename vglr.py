#!/usr/bin/env python3
"""vglr — multi-shader audio-reactive video player."""
import queue
import threading
import numpy as np
import moderngl
import moderngl_window as mglw
import av
import sounddevice as sd

VIDEO_PATH   = 'videos/fb_rev_wet_mop_reimagined.mp4'
AUDIO_DEVICE = 1      # Zoom F1: USB Audio (hw:2,0)
SAMPLE_RATE  = 44100
BLOCK_SIZE   = 1024
GAIN         = 50.0   # scale FFT into 0-1; tune to mic level
SMOOTH       = 0.3    # exponential smoothing
BEAT_THRESH  = 1.8    # energy ratio to trigger beat
BEAT_DECAY   = 0.85   # beat decay per audio callback

# Shaders (keyboard 1/2/3 to switch)
SHADERS = [
    'shaders/vhs.glsl',
    'shaders/block_glitch.glsl',
    'shaders/passthrough.glsl',
]

# Default param_a/b/c per shader (knob A=intensity, B=color fx, C=density/dryness)
SHADER_DEFAULTS = [
    {'param_a': 0.5, 'param_b': 0.4, 'param_c': 0.4},  # vhs
    {'param_a': 0.4, 'param_b': 0.5, 'param_c': 0.4},  # block_glitch
    {'param_a': 0.0, 'param_b': 0.0, 'param_c': 0.0},  # passthrough
]

# Read video metadata before GL init
with av.open(VIDEO_PATH) as _c:
    _s = _c.streams.video[0]
    VIDEO_W, VIDEO_H = _s.width, _s.height
    VIDEO_FPS = float(_s.average_rate or _s.guessed_rate or 30)

print(f"video: {VIDEO_W}x{VIDEO_H} @ {VIDEO_FPS:.3f} fps")
print("keys: 1=VHS  2=block_glitch  3=passthrough  Q=quit")

frame_queue: queue.Queue = queue.Queue(maxsize=4)

_FREQS       = np.fft.rfftfreq(BLOCK_SIZE, d=1.0 / SAMPLE_RATE)
_BASS_MASK   = (_FREQS >= 20)  & (_FREQS < 250)
_MID_MASK    = (_FREQS >= 250) & (_FREQS < 4000)
_TREBLE_MASK = _FREQS >= 4000

_lock          = threading.Lock()
_bands         = {'bass': 0.0, 'mid': 0.0, 'treble': 0.0, 'beat': 0.0}
_energy_smooth = 0.0


def audio_callback(indata, frames, time_info, status):
    global _energy_smooth
    mono   = indata[:, 0]
    fft    = np.abs(np.fft.rfft(mono, n=BLOCK_SIZE)) / BLOCK_SIZE
    bass   = min(float(np.mean(fft[_BASS_MASK]))   * GAIN, 1.0)
    mid    = min(float(np.mean(fft[_MID_MASK]))    * GAIN, 1.0)
    treble = min(float(np.mean(fft[_TREBLE_MASK])) * GAIN, 1.0)
    energy = float(np.sum(fft ** 2))
    beat   = 1.0 if (_energy_smooth > 0 and energy > _energy_smooth * BEAT_THRESH) else 0.0
    _energy_smooth = _energy_smooth * 0.9 + energy * 0.1
    with _lock:
        _bands['bass']   += SMOOTH * (bass   - _bands['bass'])
        _bands['mid']    += SMOOTH * (mid    - _bands['mid'])
        _bands['treble'] += SMOOTH * (treble - _bands['treble'])
        _bands['beat']    = max(_bands['beat'] * BEAT_DECAY, beat)


def decode_loop(path: str) -> None:
    while True:
        with av.open(path) as container:
            for frame in container.decode(video=0):
                frame_queue.put(frame.to_ndarray(format='rgb24'), block=True)


def set_uniform(prog, name, value):
    try:
        prog[name] = value
    except KeyError:
        pass


VERT = """
#version 140
in vec2 in_position;
out vec2 uv;
void main() {
    uv = vec2(in_position.x * 0.5 + 0.5, 1.0 - (in_position.y * 0.5 + 0.5));
    gl_Position = vec4(in_position, 0.0, 1.0);
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
    window_size = (1280, 720)
    resizable = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        vbo = self.ctx.buffer(QUAD)
        self._vbo = vbo
        self.texture = self.ctx.texture((VIDEO_W, VIDEO_H), 3)
        self.shader_idx = 0
        self._load_shader(0)
        self.frame_interval  = 1.0 / VIDEO_FPS
        self.last_frame_time = 0.0
        self._fps_frames     = 0
        self._fps_accum      = 0.0
        self._audio_timer    = 0.0
        threading.Thread(target=decode_loop, args=(VIDEO_PATH,), daemon=True).start()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='float32',
            blocksize=BLOCK_SIZE, device=AUDIO_DEVICE, callback=audio_callback,
        )
        self._stream.start()

    def _load_shader(self, idx: int):
        path = SHADERS[idx]
        with open(path) as f:
            frag = f.read()
        if hasattr(self, 'prog'):
            self.prog.release()
        self.prog = self.ctx.program(vertex_shader=VERT, fragment_shader=frag)
        self.vao = self.ctx.vertex_array(self.prog, [(self._vbo, '2f', 'in_position')])
        set_uniform(self.prog, 'video', 0)
        self.texture.use(location=0)
        self.shader_idx = idx
        defaults = SHADER_DEFAULTS[idx]
        for k, v in defaults.items():
            set_uniform(self.prog, k, v)
        print(f"shader: {path}")

    def on_render(self, time, frametime):
        self._fps_frames += 1
        self._fps_accum  += frametime
        self._audio_timer += frametime

        if self._fps_accum >= 5.0:
            print(f"render: {self._fps_frames / self._fps_accum:.1f} fps")
            self._fps_frames = 0
            self._fps_accum  = 0.0

        if self._audio_timer >= 1.0:
            with _lock:
                b, m, t, bt = _bands['bass'], _bands['mid'], _bands['treble'], _bands['beat']
            print(f"bass={b:.3f}  mid={m:.3f}  treble={t:.3f}  beat={bt:.3f}")
            self._audio_timer = 0.0

        with _lock:
            bass, mid, treble, beat = (
                float(_bands['bass']), float(_bands['mid']),
                float(_bands['treble']), float(_bands['beat']),
            )

        set_uniform(self.prog, 'resolution', self.wnd.size)
        set_uniform(self.prog, 'time',       time)
        set_uniform(self.prog, 'bass',       bass)
        set_uniform(self.prog, 'mid',        mid)
        set_uniform(self.prog, 'treble',     treble)
        set_uniform(self.prog, 'beat',       beat)

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
        if action != self.wnd.keys.ACTION_PRESS:
            return
        if key == self.wnd.keys.Q:
            self.wnd.close()
        elif key == ord('1'):
            self._load_shader(0)
        elif key == ord('2'):
            self._load_shader(1)
        elif key == ord('3'):
            self._load_shader(2)


if __name__ == '__main__':
    mglw.run_window_config(VGLRApp)
