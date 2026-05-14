#!/usr/bin/env python3
"""vglr — step 5d: VHS shader with audio-reactive uniforms."""
import queue
import threading
import numpy as np
import moderngl
import moderngl_window as mglw
import av
import sounddevice as sd

VIDEO_PATH  = 'videos/fb_rev_wet_mop_reimagined.mp4'
SHADER_PATH = 'shaders/vhs.glsl'
AUDIO_DEVICE = 1  # Zoom F1: USB Audio (hw:2,0)
SAMPLE_RATE  = 44100
BLOCK_SIZE   = 1024
GAIN         = 50.0   # scale FFT into 0-1; tune to mic level
SMOOTH       = 0.3    # exponential smoothing (higher = faster response)
BEAT_THRESH  = 1.8    # energy ratio above smoothed average to trigger beat
BEAT_DECAY   = 0.85   # beat value decay per audio callback (~23ms)

# Read video metadata before GL init
with av.open(VIDEO_PATH) as _c:
    _s = _c.streams.video[0]
    VIDEO_W, VIDEO_H = _s.width, _s.height
    VIDEO_FPS = float(_s.average_rate or _s.guessed_rate or 30)

print(f"video: {VIDEO_W}x{VIDEO_H} @ {VIDEO_FPS:.3f} fps")

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
    window_size = (1920, 1080)
    resizable = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with open(SHADER_PATH) as f:
            frag = f.read()
        self.prog = self.ctx.program(vertex_shader=VERT, fragment_shader=frag)
        vbo = self.ctx.buffer(QUAD)
        self.vao = self.ctx.vertex_array(self.prog, [(vbo, '2f', 'in_position')])
        self.texture = self.ctx.texture((VIDEO_W, VIDEO_H), 3)
        self.prog['video'] = 0
        self.texture.use(location=0)
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

        self.prog['resolution'] = self.wnd.size
        self.prog['time']       = time
        self.prog['bass']       = bass
        self.prog['mid']        = mid
        self.prog['treble']     = treble
        self.prog['beat']       = beat

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
