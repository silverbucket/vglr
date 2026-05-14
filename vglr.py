#!/usr/bin/env python3
"""vglr — multi-shader audio-reactive video player with MIDI Mix control."""
import queue
import threading
import numpy as np
import moderngl
import moderngl_window as mglw
import av
import sounddevice as sd

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False
    print("mido not installed — running without MIDI (pip install mido python-rtmidi)")

# ── video / audio config ─────────────────────────────────────────────────────
VIDEO_PATH   = 'videos/fb_rev_wet_mop_reimagined.mp4'
AUDIO_DEVICE = 1      # Zoom F1 (hw:2,0) — change if device order shifts
SAMPLE_RATE  = 44100
BLOCK_SIZE   = 1024
GAIN         = 50.0   # FFT → 0-1 scale; tuned by fader 1-3 at runtime
SMOOTH       = 0.3
BEAT_DECAY   = 0.85

# ── shaders ──────────────────────────────────────────────────────────────────
SHADERS = [
    ('VHS',         'shaders/vhs.glsl',         {'param_a': 0.5, 'param_b': 0.4, 'param_c': 0.4}),
    ('BlockGlitch', 'shaders/block_glitch.glsl', {'param_a': 0.4, 'param_b': 0.5, 'param_c': 0.4}),
    ('Clean',       'shaders/passthrough.glsl',  {}),
]

# ── AKAI MIDI Mix factory mapping ─────────────────────────────────────────────
# Rec ARM notes (strips 1-8) — used for shader selection
RECARM = [3, 6, 9, 12, 15, 18, 21, 24]
# Mute notes (strips 1-8) — used for band on/off
MUTE   = [1, 4, 7, 10, 13, 16, 19, 22]
SOLO   = 27    # "clean hold" toggle
BANK_L = 25
BANK_R = 26

# Channel fader CC numbers (strips 1-8) + master
FADER_CC  = [19, 23, 27, 31, 49, 53, 57, 61]
MASTER_CC = 62

# ── MIDI control state ────────────────────────────────────────────────────────
# Simple floats/bools — CPython GIL makes writes atomic enough for these params
_m_bass_gain   = 1.0   # fader 1  (0-2.0, centre=1.0)
_m_mid_gain    = 1.0   # fader 2
_m_treble_gain = 1.0   # fader 3
_m_beat_thresh = 1.8   # fader 4  (1.0-4.5, higher = less sensitive)
_m_master      = 1.0   # master fader (0-1.0)
_m_effects_on  = True  # solo toggle — False suppresses all effects
_m_bass_on     = True  # mute 1
_m_mid_on      = True  # mute 2
_m_treble_on   = True  # mute 3
_m_shader_req  = None  # set by MIDI thread, consumed by render thread
_midi_out       = None  # mido output port (set once MIDI connects)


def _set_led(note: int, on: bool) -> None:
    if _midi_out:
        _midi_out.send(mido.Message('note_on', channel=0, note=note,
                                     velocity=127 if on else 0))


def _shader_leds(active_idx: int) -> None:
    for i, note in enumerate(RECARM[:len(SHADERS)]):
        _set_led(note, i == active_idx)


def _handle_midi(msg) -> None:
    global _m_bass_gain, _m_mid_gain, _m_treble_gain, _m_beat_thresh
    global _m_master, _m_effects_on, _m_bass_on, _m_mid_on, _m_treble_on
    global _m_shader_req

    if msg.type in ('note_on', 'note_off'):
        if msg.type == 'note_off' or msg.velocity == 0:
            return
        note = msg.note
        # Rec ARM 1-N → select shader
        for i, n in enumerate(RECARM[:len(SHADERS)]):
            if note == n:
                _m_shader_req = i
                _shader_leds(i)
                return
        # Mute 1-3 → toggle band reactivity
        if note == MUTE[0]:
            _m_bass_on = not _m_bass_on
            _set_led(MUTE[0], _m_bass_on)
        elif note == MUTE[1]:
            _m_mid_on = not _m_mid_on
            _set_led(MUTE[1], _m_mid_on)
        elif note == MUTE[2]:
            _m_treble_on = not _m_treble_on
            _set_led(MUTE[2], _m_treble_on)
        # Solo → suppress all effects while toggled on
        elif note == SOLO:
            _m_effects_on = not _m_effects_on
            _set_led(SOLO, not _m_effects_on)   # LED on = effects suppressed

    elif msg.type == 'control_change':
        cc, v = msg.control, msg.value
        if   cc == FADER_CC[0]: _m_bass_gain   = v / 64.0            # 0→2.0
        elif cc == FADER_CC[1]: _m_mid_gain    = v / 64.0
        elif cc == FADER_CC[2]: _m_treble_gain = v / 64.0
        elif cc == FADER_CC[3]: _m_beat_thresh = 1.0 + v / 127.0 * 3.5  # 1.0→4.5
        elif cc == MASTER_CC:   _m_master      = v / 127.0


def _midi_loop() -> None:
    global _midi_out
    if not MIDO_AVAILABLE:
        return
    try:
        in_name  = next((n for n in mido.get_input_names()  if 'MIDI Mix' in n), None)
        out_name = next((n for n in mido.get_output_names() if 'MIDI Mix' in n), None)
        if not in_name:
            print("MIDI Mix not found — running without MIDI")
            return
        print(f"MIDI: in={in_name}  out={out_name}")
        with mido.open_output(out_name) as outport:
            _midi_out = outport
            _shader_leds(0)
            for note in [MUTE[0], MUTE[1], MUTE[2]]:
                _set_led(note, True)
            _set_led(SOLO, False)
            with mido.open_input(in_name) as inport:
                for msg in inport:
                    _handle_midi(msg)
    except Exception as exc:
        print(f"MIDI error: {exc}")


# ── video decode ─────────────────────────────────────────────────────────────
with av.open(VIDEO_PATH) as _c:
    _s = _c.streams.video[0]
    VIDEO_W, VIDEO_H = _s.width, _s.height
    VIDEO_FPS = float(_s.average_rate or _s.guessed_rate or 30)

print(f"video: {VIDEO_W}x{VIDEO_H} @ {VIDEO_FPS:.3f} fps")

frame_queue: queue.Queue = queue.Queue(maxsize=4)


def _decode_loop(path: str) -> None:
    while True:
        with av.open(path) as container:
            for frame in container.decode(video=0):
                frame_queue.put(frame.to_ndarray(format='rgb24'), block=True)


# ── audio capture ─────────────────────────────────────────────────────────────
_FREQS       = np.fft.rfftfreq(BLOCK_SIZE, d=1.0 / SAMPLE_RATE)
_BASS_MASK   = (_FREQS >= 20)  & (_FREQS < 250)
_MID_MASK    = (_FREQS >= 250) & (_FREQS < 4000)
_TREBLE_MASK = _FREQS >= 4000

_lock          = threading.Lock()
_bands         = {'bass': 0.0, 'mid': 0.0, 'treble': 0.0, 'beat': 0.0}
_energy_smooth = 0.0


def _audio_callback(indata, frames, time_info, status):
    global _energy_smooth
    mono   = indata[:, 0]
    fft    = np.abs(np.fft.rfft(mono, n=BLOCK_SIZE)) / BLOCK_SIZE
    bass   = min(float(np.mean(fft[_BASS_MASK]))   * GAIN, 1.0)
    mid    = min(float(np.mean(fft[_MID_MASK]))    * GAIN, 1.0)
    treble = min(float(np.mean(fft[_TREBLE_MASK])) * GAIN, 1.0)
    energy = float(np.sum(fft ** 2))
    beat   = 1.0 if (_energy_smooth > 0 and energy > _energy_smooth * _m_beat_thresh) else 0.0
    _energy_smooth = _energy_smooth * 0.9 + energy * 0.1
    with _lock:
        _bands['bass']   += SMOOTH * (bass   - _bands['bass'])
        _bands['mid']    += SMOOTH * (mid    - _bands['mid'])
        _bands['treble'] += SMOOTH * (treble - _bands['treble'])
        _bands['beat']    = max(_bands['beat'] * BEAT_DECAY, beat)


# ── GL helpers ────────────────────────────────────────────────────────────────
VERT = """
#version 140
in vec2 in_position;
out vec2 uv;
void main() {
    uv = vec2(in_position.x * 0.5 + 0.5, 1.0 - (in_position.y * 0.5 + 0.5));
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

QUAD = np.array([-1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0], dtype='f4')


def _set_uniform(prog, name, value):
    try:
        prog[name] = value
    except KeyError:
        pass


# ── app ───────────────────────────────────────────────────────────────────────
class VGLRApp(mglw.WindowConfig):
    title = "vglr"
    gl_version = (3, 1)
    window_size = (1280, 720)
    resizable = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._vbo      = self.ctx.buffer(QUAD)
        self.texture   = self.ctx.texture((VIDEO_W, VIDEO_H), 3)
        self.shader_idx = -1
        self.prog       = None
        self._load_shader(0)

        self.frame_interval  = 1.0 / VIDEO_FPS
        self.last_frame_time = 0.0
        self._fps_frames     = 0
        self._fps_accum      = 0.0
        self._audio_timer    = 0.0

        threading.Thread(target=_decode_loop, args=(VIDEO_PATH,), daemon=True).start()
        threading.Thread(target=_midi_loop, daemon=True).start()

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='float32',
            blocksize=BLOCK_SIZE, device=AUDIO_DEVICE, callback=_audio_callback,
        )
        self._stream.start()

    def _load_shader(self, idx: int) -> None:
        name, path, defaults = SHADERS[idx]
        with open(path) as f:
            frag = f.read()
        if self.prog:
            self.prog.release()
        self.prog = self.ctx.program(vertex_shader=VERT, fragment_shader=frag)
        self.vao  = self.ctx.vertex_array(self.prog, [(self._vbo, '2f', 'in_position')])
        _set_uniform(self.prog, 'video', 0)
        self.texture.use(location=0)
        for k, v in defaults.items():
            _set_uniform(self.prog, k, v)
        self.shader_idx = idx
        print(f"shader: {name} ({path})")

    def on_render(self, time, frametime):
        global _m_shader_req

        # ── shader switch requested by MIDI ──
        if _m_shader_req is not None:
            self._load_shader(_m_shader_req)
            _m_shader_req = None

        # ── fps logging ──
        self._fps_frames += 1
        self._fps_accum  += frametime
        self._audio_timer += frametime
        if self._fps_accum >= 5.0:
            print(f"render: {self._fps_frames / self._fps_accum:.1f} fps  "
                  f"shader: {SHADERS[self.shader_idx][0]}")
            self._fps_frames = 0
            self._fps_accum  = 0.0

        # ── audio values with MIDI gain applied ──
        with _lock:
            br, mr, tr, bt = (_bands['bass'], _bands['mid'],
                               _bands['treble'], _bands['beat'])

        if _m_effects_on:
            bass   = br * (_m_bass_gain   * _m_master) if _m_bass_on   else 0.0
            mid    = mr * (_m_mid_gain    * _m_master) if _m_mid_on    else 0.0
            treble = tr * (_m_treble_gain * _m_master) if _m_treble_on else 0.0
            beat   = bt * _m_master
        else:
            bass = mid = treble = beat = 0.0

        if self._audio_timer >= 1.0:
            print(f"bass={bass:.3f}  mid={mid:.3f}  treble={treble:.3f}  beat={beat:.3f}")
            self._audio_timer = 0.0

        # ── set uniforms ──
        _set_uniform(self.prog, 'resolution', self.wnd.size)
        _set_uniform(self.prog, 'time',       time)
        _set_uniform(self.prog, 'bass',       float(bass))
        _set_uniform(self.prog, 'mid',        float(mid))
        _set_uniform(self.prog, 'treble',     float(treble))
        _set_uniform(self.prog, 'beat',       float(beat))

        # ── video frame ──
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


if __name__ == '__main__':
    mglw.run_window_config(VGLRApp)
