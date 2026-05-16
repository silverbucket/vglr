#!/usr/bin/env python3
"""vglr — audio-reactive video glitch player with MIDI Mix control."""
import json
import os
import queue
import random
import sys
import time
from time import monotonic as _monotonic
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

# ── audio config ──────────────────────────────────────────────────────────────
AUDIO_DEVICE = 1      # Zoom F1 (hw:2,0)
SAMPLE_RATE  = 44100
BLOCK_SIZE   = 1024
GAIN         = 200.0  # higher = more sensitive; tune per venue
SMOOTH       = 0.3
BEAT_DECAY   = 0.85

FALLBACK_VIDEO = 'videos/bank1/video1/Americana.mp4'

# ── auto-effect tuning ────────────────────────────────────────────────────────
# How quickly the momentum tracker responds to energy changes.
# Higher = smoother/slower; lower = snappier but jittery. Range 0–1.
AUTO_MOMENTUM_SMOOTH   = 0.85

# Scales how much energy swing is needed to shift momentum from 0 to 1.
# Lower = small swings move the needle; higher = only big drops/builds matter.
AUTO_MOMENTUM_SCALE    = 25.0

# Beat amplitude threshold (pre-master) that triggers auto probability rolls.
# 0.5 = medium beats; lower = reacts to quieter beats too.
AUTO_BEAT_THRESHOLD    = 0.5

# Minimum activate probability per beat (even at silence / flat energy).
AUTO_P_ON_FLOOR        = 0.05
# How much building momentum adds to activate probability. Total max = FLOOR + this.
AUTO_P_ON_MOMENTUM     = 0.10

# Minimum deactivate probability per beat (even while energy is building).
AUTO_P_OFF_FLOOR       = 0.05
# How much falling momentum adds to deactivate probability. Total max = FLOOR + this.
AUTO_P_OFF_MOMENTUM    = 0.40

# Probability per beat of drifting to a different effect within the auto pool.
# Only applies when the pool has more than one effect.
AUTO_P_DRIFT           = 0.15

# Blend transition speed: higher = snappier fade in/out (2.5 ≈ 0.4s to full).
AUTO_BLEND_RATE        = 2.5

# Maximum opacity of the accent layer (0.0–1.0).
# At 1.0 the auto effect fully covers the A/B output at peak blend.
AUTO_BLEND_MAX         = 0.75

# How long (seconds) to hold a MUTE button before solo-preview activates.
PREVIEW_HOLD_S         = 1.0

# ── shaders (name, path) — 8 slots map to 8 Mute buttons ─────────────────────
SHADERS = [
    # ── page 1 (SOLO × 0) ─────────────────────────────────────────────────────
    ('vhs',            'shaders/vhs.glsl'),
    ('block_glitch',   'shaders/block_glitch.glsl'),
    ('kaleidoscope',   'shaders/kaleidoscope.glsl'),
    ('vortex',         'shaders/vortex.glsl'),
    ('rgb_orbit',      'shaders/rgb_orbit.glsl'),
    ('pixel_sort',     'shaders/pixel_sort.glsl'),
    ('contour',        'shaders/contour.glsl'),
    ('melt',           'shaders/melt.glsl'),
    # ── page 2 (SOLO × 1) ─────────────────────────────────────────────────────
    ('thermal',        'shaders/thermal.glsl'),
    ('neon_glow',      'shaders/neon_glow.glsl'),
    ('lens_warp',      'shaders/lens_warp.glsl'),
    ('slit_scan',      'shaders/slit_scan.glsl'),
    ('posterize',      'shaders/posterize.glsl'),
    ('tunnel_neon',    'shaders/tunnel_neon.glsl'),
    ('film_burn',      'shaders/film_burn.glsl'),
    ('mirror_tile',    'shaders/mirror_tile.glsl'),
]

# ── AKAI MIDI Mix factory mapping ─────────────────────────────────────────────
RECARM    = [3,  6,  9,  12, 15, 18, 21, 24]   # Rec ARM notes, strips 1-8
MUTE      = [1,  4,  7,  10, 13, 16, 19, 22]   # Mute notes, strips 1-8
SOLO      = 27
BANK_L    = 25
BANK_R    = 26
SEND_ALL_BURST  = 32    # SEND ALL fires all 33 CCs; save after 32
SEND_ALL_WINDOW = 0.15  # seconds; CC burst window
FADER_CC  = [19, 23, 27, 31, 49, 53, 57, 61]
KNOB_CC   = [
    [16, 17, 18], [20, 21, 22], [24, 25, 26], [28, 29, 30],
    [46, 47, 48], [50, 51, 52], [54, 55, 56], [58, 59, 60],
]
MASTER_CC = 62

# ── per-bank OSD colours (shown as brief flash on bank change) ────────────────
BANK_COLORS = [
    (1.0, 0.25, 0.25),  # bank1  red
    (0.25, 0.45, 1.0),  # bank2  blue
    (0.25, 1.0,  0.35), # bank3  green
    (1.0, 1.0,  0.20),  # bank4  yellow
    (1.0, 0.25, 1.0),   # bank5  magenta
    (0.20, 1.0,  1.0),  # bank6  cyan
    (1.0, 0.55, 0.10),  # bank7  orange
    (0.90, 0.90, 0.90), # bank8  white
]
OSD_DURATION = 1.5

# ── defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_SETTINGS = {
    'shader':      'vhs',
    'intensity':   1.0,
    'param_a':     0.5,
    'param_b':     0.4,
    'param_c':     0.4,
    'beat_thresh': 1.8,
}
_DEFAULT_EFFECT = {'intensity': 1.0, 'param_a': 0.5, 'param_b': 0.4, 'param_c': 0.4}

# ── live state (MIDI thread writes, render thread reads; GIL as lock) ─────────
_current_bank     = 1
_current_slot     = 1
# Up to 2 active shader indices, sorted ascending.
# MIDI thread mutates in place (append/remove/sort); render thread snapshots with list().
_active_effects   = [0]
# Per-shader params for every shader; always present so any strip can be tweaked
# even before its effect is activated.
_effect_params    = {i: dict(_DEFAULT_EFFECT) for i in range(len(SHADERS))}
_slot_beat_thresh = 1.8
_m_master         = 1.0
_midi_out         = None

# ── video / OSD state ─────────────────────────────────────────────────────────
_requested_video = None
_new_fps         = None
_osd_trigger     = None
_effect_page     = 0

# ── SEND ALL burst detection (MIDI thread only) ───────────────────────────────
_cc_burst_count = 0
_cc_burst_time  = 0.0

# ── MIDI reset combo: hold MUTE-1 + BANK_L + BANK_R for 2 s ──────────────────
_RESET_NOTES  = frozenset({MUTE[0], BANK_L, BANK_R})
_RESET_HOLD_S = 2.0
_reset_held: dict = {}   # note → press_time (MIDI thread only)

# ── auto-effect probabilistic accent layer ────────────────────────────────────
_auto_effects:   set  = set()   # effect indices in probabilistic mode
_dbl_click_time: dict = {}      # MUTE note → last press time (double-click detection)
_mute_hold_time: dict = {}      # MUTE note → press time (solo-preview hold detection)

frame_queue: queue.Queue = queue.Queue(maxsize=4)


# ── slot filesystem ───────────────────────────────────────────────────────────
def _slot_dir(bank: int, slot: int) -> str:
    return os.path.join('videos', f'bank{bank}', f'video{slot}')


def _find_video(bank: int, slot: int) -> str | None:
    d = _slot_dir(bank, slot)
    if not os.path.isdir(d):
        return None
    for f in sorted(os.listdir(d)):
        if not f.startswith('.') and f.lower().endswith(('.mp4', '.mkv', '.mov')):
            return os.path.join(d, f)
    return None


def _settings_path(bank: int, slot: int) -> str:
    return os.path.join(_slot_dir(bank, slot), 'settings.json')


def _load_settings(bank: int, slot: int) -> dict:
    try:
        with open(_settings_path(bank, slot)) as f:
            return {**_DEFAULT_SETTINGS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return _DEFAULT_SETTINGS.copy()


def _save_settings(bank: int, slot: int) -> None:
    effects = [
        {
            'shader':    SHADERS[idx][0],
            'intensity': _effect_params[idx]['intensity'],
            'param_a':   _effect_params[idx]['param_a'],
            'param_b':   _effect_params[idx]['param_b'],
            'param_c':   _effect_params[idx]['param_c'],
        }
        for idx in sorted(_active_effects)
    ]
    first = effects[0] if effects else {}
    auto = [
        {
            'shader':    SHADERS[idx][0],
            'intensity': _effect_params[idx]['intensity'],
            'param_a':   _effect_params[idx]['param_a'],
            'param_b':   _effect_params[idx]['param_b'],
            'param_c':   _effect_params[idx]['param_c'],
        }
        for idx in sorted(_auto_effects)
        if idx < len(SHADERS)
    ]
    cfg = {
        'effects':      effects,
        'auto_effects': auto,
        # Legacy top-level keys for forward/backward compat with old format
        'shader':      first.get('shader', 'vhs'),
        'intensity':   first.get('intensity', 1.0),
        'param_a':     first.get('param_a', 0.5),
        'param_b':     first.get('param_b', 0.4),
        'param_c':     first.get('param_c', 0.4),
        'beat_thresh': _slot_beat_thresh,
    }
    os.makedirs(_slot_dir(bank, slot), exist_ok=True)
    with open(_settings_path(bank, slot), 'w') as f:
        json.dump(cfg, f, indent=2)
    names = '+'.join(e['shader'] for e in effects)
    print(f"saved: {_settings_path(bank, slot)}  ({names})")


def _apply_settings(cfg: dict) -> None:
    global _active_effects, _slot_beat_thresh, _auto_effects
    _slot_beat_thresh = cfg.get('beat_thresh', _DEFAULT_SETTINGS['beat_thresh'])

    raw_effects = cfg.get('effects')
    if raw_effects:
        # New multi-effect format
        new_active = []
        for e in raw_effects[:2]:
            idx = next((i for i, (n, _) in enumerate(SHADERS) if n == e.get('shader')), 0)
            _effect_params[idx].update({
                'intensity': e.get('intensity', _DEFAULT_EFFECT['intensity']),
                'param_a':   e.get('param_a',   _DEFAULT_EFFECT['param_a']),
                'param_b':   e.get('param_b',   _DEFAULT_EFFECT['param_b']),
                'param_c':   e.get('param_c',   _DEFAULT_EFFECT['param_c']),
            })
            new_active.append(idx)
        _active_effects = sorted(new_active)
    else:
        # Legacy single-effect format
        idx = next((i for i, (n, _) in enumerate(SHADERS) if n == cfg.get('shader', 'vhs')), 0)
        _effect_params[idx].update({
            'intensity': cfg.get('intensity', _DEFAULT_EFFECT['intensity']),
            'param_a':   cfg.get('param_a',   _DEFAULT_EFFECT['param_a']),
            'param_b':   cfg.get('param_b',   _DEFAULT_EFFECT['param_b']),
            'param_c':   cfg.get('param_c',   _DEFAULT_EFFECT['param_c']),
        })
        _active_effects = [idx]

    # Restore auto-effect pool
    _auto_effects.clear()
    for e in cfg.get('auto_effects', []):
        idx = next((i for i, (n, _) in enumerate(SHADERS) if n == e.get('shader')), None)
        if idx is not None:
            _effect_params[idx].update({
                'intensity': e.get('intensity', _DEFAULT_EFFECT['intensity']),
                'param_a':   e.get('param_a',   _DEFAULT_EFFECT['param_a']),
                'param_b':   e.get('param_b',   _DEFAULT_EFFECT['param_b']),
                'param_c':   e.get('param_c',   _DEFAULT_EFFECT['param_c']),
            })
            _auto_effects.add(idx)


def _select_slot(bank: int, slot: int, flash_osd: bool = False) -> None:
    global _current_bank, _current_slot, _requested_video, _osd_trigger
    _current_bank = bank
    _current_slot = slot
    _apply_settings(_load_settings(bank, slot))
    video = _find_video(bank, slot)
    if video:
        _requested_video = video
        print(f"slot: bank{bank}/video{slot}  {os.path.basename(video)}")
    else:
        print(f"slot: bank{bank}/video{slot}  (no video)")
    names = '+'.join(SHADERS[i][0] for i in _active_effects)
    print(f"  effects={names}")
    if flash_osd:
        _osd_trigger = BANK_COLORS[(bank - 1) % len(BANK_COLORS)]
    if _midi_out:
        _slot_leds(slot)
        _effect_leds(_active_effects)


# ── LED helpers ───────────────────────────────────────────────────────────────
def _set_led(note: int, on: bool) -> None:
    if _midi_out:
        _midi_out.send(mido.Message('note_on', channel=0, note=note,
                                    velocity=127 if on else 0))


def _slot_leds(active: int) -> None:
    for i, note in enumerate(RECARM):
        _set_led(note, (i + 1) == active)


def _effect_leds(active_indices, slow_phase: bool = True, fast_phase: bool = True,
                 preview_idx: int | None = None) -> None:
    page_start = _effect_page * 8
    for i in range(8):
        idx = page_start + i
        if idx >= len(SHADERS):
            _set_led(MUTE[i], False)
        elif preview_idx is not None:
            # Preview active: only the previewed LED fast-flashes; everything else off
            _set_led(MUTE[i], fast_phase if idx == preview_idx else False)
        elif idx in active_indices:
            _set_led(MUTE[i], True)              # stable active: solid
        elif idx in _auto_effects:
            _set_led(MUTE[i], slow_phase)        # auto/trigger pool: slow blink
        else:
            _set_led(MUTE[i], False)


def _toggle_effect_page() -> None:
    global _effect_page, _osd_trigger
    pages = max(1, (len(SHADERS) + 7) // 8)
    _effect_page = (_effect_page + 1) % pages
    print(f"effect page: {_effect_page + 1}/{pages}")
    _osd_trigger = (0.55, 0.2, 0.9)
    if _midi_out:
        _effect_leds(_active_effects)


# ── MIDI ──────────────────────────────────────────────────────────────────────
def _handle_midi(msg) -> None:
    global _m_master, _cc_burst_count, _cc_burst_time, _reset_held, _active_effects

    if msg.type in ('note_on', 'note_off'):
        pressed = msg.type == 'note_on' and msg.velocity > 0
        note    = msg.note

        # ── reset combo hold tracking (trigger polled in render loop) ───────────
        if note in _RESET_NOTES:
            if pressed:
                _reset_held[note] = time.monotonic()
            else:
                _reset_held.pop(note, None)
        # ── end reset combo ───────────────────────────────────────────────────

        # ── solo-preview hold tracking ────────────────────────────────────────
        if note in MUTE:
            if pressed:
                _mute_hold_time[note] = time.monotonic()
            else:
                _mute_hold_time.pop(note, None)
        # ─────────────────────────────────────────────────────────────────────

        if not pressed:
            return
        note = msg.note

        for i, n in enumerate(RECARM):
            if note == n:
                _select_slot(_current_bank, i + 1)
                return

        for i, n in enumerate(MUTE):
            if note == n:
                real_idx = _effect_page * 8 + i
                if real_idx >= len(SHADERS):
                    return
                now_t = time.monotonic()
                last_t = _dbl_click_time.get(n, 0.0)
                _dbl_click_time[n] = now_t

                if now_t - last_t < 0.35:
                    # Double-click: toggle auto mode
                    _dbl_click_time[n] = 0.0   # reset so triple-click is a fresh single
                    if real_idx in _auto_effects:
                        _auto_effects.discard(real_idx)
                    else:
                        _active_effects = [e for e in _active_effects if e != real_idx]
                        _auto_effects.add(real_idx)
                    _effect_leds(_active_effects)
                    return

                # Single click: stable toggle (also exits auto mode if already there)
                _auto_effects.discard(real_idx)
                if real_idx in _active_effects:
                    _active_effects.remove(real_idx)
                elif len(_active_effects) < 2:
                    _active_effects.append(real_idx)
                    _active_effects.sort()
                # else: already at 2 active — ignore press
                _effect_leds(_active_effects)
                return

        if note == BANK_L:
            _select_slot(max(1, _current_bank - 1), _current_slot, flash_osd=True)
        elif note == BANK_R:
            _select_slot(_current_bank + 1, _current_slot, flash_osd=True)
        elif note == SOLO:
            _toggle_effect_page()

    elif msg.type == 'control_change':
        cc, v = msg.control, msg.value

        # Detect SEND ALL: 33 CCs arrive in < 150ms
        now = time.monotonic()
        if now - _cc_burst_time > SEND_ALL_WINDOW:
            _cc_burst_count = 0
            _cc_burst_time  = now
        _cc_burst_count += 1
        if _cc_burst_count == SEND_ALL_BURST:
            _save_settings(_current_bank, _current_slot)

        # Each strip independently controls its own effect on the current page.
        # This works whether or not that effect is currently active.
        for si in range(8):
            effect_idx = _effect_page * 8 + si
            if effect_idx >= len(SHADERS):
                continue
            if cc == FADER_CC[si]:
                _effect_params[effect_idx]['intensity'] = v / 127.0
                return
            for k, key in enumerate(('param_a', 'param_b', 'param_c')):
                if cc == KNOB_CC[si][k]:
                    _effect_params[effect_idx][key] = v / 127.0
                    return

        if cc == MASTER_CC:
            _m_master = v / 127.0


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
            _slot_leds(_current_slot)
            _effect_leds(_active_effects)
            with mido.open_input(in_name) as inport:
                for msg in inport:
                    _handle_midi(msg)
    except Exception as exc:
        print(f"MIDI error: {exc}")


# ── video decode ──────────────────────────────────────────────────────────────
def _decode_loop() -> None:
    global _new_fps
    current = None
    while True:
        try:
            target = _requested_video
            if not target:
                time.sleep(0.05)
                continue
            if target != current:
                while not frame_queue.empty():
                    try:
                        frame_queue.get_nowait()
                    except queue.Empty:
                        break
                current = target
            with av.open(current) as container:
                s = container.streams.video[0]
                _new_fps = float(s.average_rate or s.guessed_rate or 30)
                for frame in container.decode(video=0):
                    if _requested_video != current:
                        break
                    if frame.width != _init_w or frame.height != _init_h:
                        frame = frame.reformat(width=_init_w, height=_init_h)
                    try:
                        frame_queue.put(frame.to_ndarray(format='rgb24'),
                                        block=True, timeout=0.5)
                    except queue.Full:
                        pass
        except Exception as exc:
            print(f"decode error ({current}): {exc}", flush=True)
            current = None
            time.sleep(0.5)


# ── audio ─────────────────────────────────────────────────────────────────────
_FREQS       = np.fft.rfftfreq(BLOCK_SIZE, d=1.0 / SAMPLE_RATE)
_BASS_MASK   = (_FREQS >= 20)  & (_FREQS < 250)
_MID_MASK    = (_FREQS >= 250) & (_FREQS < 4000)
_TREBLE_MASK = _FREQS >= 4000

_lock          = threading.Lock()
_bands         = {'bass': 0.0, 'mid': 0.0, 'treble': 0.0, 'beat': 0.0, 'stereo_width': 0.0}
_energy_smooth = 0.0


def _audio_callback(indata, frames, time_info, status):
    global _energy_smooth
    mono  = indata.mean(axis=1)
    width = min(float(np.mean(np.abs(indata[:, 0] - indata[:, 1]))) * GAIN, 1.0)
    fft    = np.abs(np.fft.rfft(mono, n=BLOCK_SIZE)) / BLOCK_SIZE
    bass   = min(float(np.mean(fft[_BASS_MASK]))   * GAIN, 1.0)
    mid    = min(float(np.mean(fft[_MID_MASK]))    * GAIN, 1.0)
    treble = min(float(np.mean(fft[_TREBLE_MASK])) * GAIN, 1.0)
    energy = float(np.sum(fft ** 2))
    beat   = 1.0 if (_energy_smooth > 0 and energy > _energy_smooth * _slot_beat_thresh) else 0.0
    _energy_smooth = _energy_smooth * 0.9 + energy * 0.1
    with _lock:
        _bands['bass']         += SMOOTH * (bass   - _bands['bass'])
        _bands['mid']          += SMOOTH * (mid    - _bands['mid'])
        _bands['treble']       += SMOOTH * (treble - _bands['treble'])
        _bands['beat']          = max(_bands['beat'] * BEAT_DECAY, beat)
        _bands['stereo_width'] += SMOOTH * (width  - _bands['stereo_width'])


# ── GL ────────────────────────────────────────────────────────────────────────
VERT = """
#version 140
in vec2 in_position;
out vec2 uv;
void main() {
    uv = vec2(in_position.x * 0.5 + 0.5, 1.0 - (in_position.y * 0.5 + 0.5));
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

# Same UV as VERT but gl_Position.y is negated.
# Two uses:
#   1. Pass 1 of dual-effect chain: stores the FBO content with the same y=0-at-top
#      orientation as the video texture, so Pass 2 can sample it with the normal UV.
#   2. Beat-triggered screen flip: outputs the final image upside-down.
VERT_FLIP = """
#version 140
in vec2 in_position;
out vec2 uv;
void main() {
    uv = vec2(in_position.x * 0.5 + 0.5, 1.0 - (in_position.y * 0.5 + 0.5));
    gl_Position = vec4(in_position.x, -in_position.y, 0.0, 1.0);
}
"""

_OSD_FRAG = """
#version 140
uniform vec4 osd_color;
in vec2 uv;
out vec4 fragColor;
void main() {
    // Distance from nearest edge (0 at border, 0.5 at centre)
    float edge = min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y));
    // Glow that's full-strength at the border and fades inward over ~20% of the screen
    float vignette = 1.0 - smoothstep(0.0, 0.20, edge);
    vignette = pow(vignette, 0.7);
    fragColor = vec4(osd_color.rgb, osd_color.a * vignette);
}
"""

_AUTO_BLEND_FRAG = """
#version 140
uniform sampler2D overlay;
uniform float blend_alpha;
in vec2 uv;
out vec4 fragColor;
void main() {
    fragColor = vec4(texture(overlay, uv).rgb, blend_alpha);
}
"""

_PASSTHROUGH_FRAG = """
#version 140
uniform sampler2D video;
in vec2 uv;
out vec4 fragColor;
void main() { fragColor = texture(video, uv); }
"""

QUAD = np.array([-1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0], dtype='f4')


def _set_uniform(prog, name, value):
    try:
        prog[name] = value
    except KeyError:
        pass


class VGLRApp(mglw.WindowConfig):
    title = "vglr"
    gl_version = (3, 1)
    window_size = (1280, 720)
    resizable = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._vbo = self.ctx.buffer(QUAD)

        # Main video texture
        self.texture = self.ctx.texture((_init_w, _init_h), 3)
        self.texture.use(location=0)

        # Pre-compile all effect shaders at startup — no latency when toggling.
        # Each shader is compiled twice: once with VERT (normal screen output)
        # and once with VERT_FLIP (position-flipped, for FBO writes and beat flip).
        self._progs      = {}   # shader_idx -> (prog, vao)  — normal output
        self._progs_flip = {}   # shader_idx -> (prog, vao)  — position-flipped output
        for i, (name, path) in enumerate(SHADERS):
            try:
                with open(path) as f:
                    frag = f.read()
                prog = self.ctx.program(vertex_shader=VERT, fragment_shader=frag)
                vao  = self.ctx.vertex_array(prog, [(self._vbo, '2f', 'in_position')])
                _set_uniform(prog, 'video', 0)
                self._progs[i] = (prog, vao)

                prog_f = self.ctx.program(vertex_shader=VERT_FLIP, fragment_shader=frag)
                vao_f  = self.ctx.vertex_array(prog_f, [(self._vbo, '2f', 'in_position')])
                _set_uniform(prog_f, 'video', 0)
                self._progs_flip[i] = (prog_f, vao_f)
                print(f"compiled: {name}")
            except Exception as exc:
                print(f"shader error ({name}): {exc}")

        # Passthrough — used when no effect is active
        _pt_prog = self.ctx.program(vertex_shader=VERT, fragment_shader=_PASSTHROUGH_FRAG)
        _pt_vao  = self.ctx.vertex_array(_pt_prog, [(self._vbo, '2f', 'in_position')])
        _set_uniform(_pt_prog, 'video', 0)
        self._passthrough_vao = _pt_vao

        # OSD overlay
        self._osd_prog = self.ctx.program(vertex_shader=VERT, fragment_shader=_OSD_FRAG)
        self._osd_vao  = self.ctx.vertex_array(self._osd_prog,
                                               [(self._vbo, '2f', 'in_position')])
        self._osd_timer = 0.0
        self._osd_color = (1.0, 1.0, 1.0)

        # FBO for two-effect chain: effect A renders here, effect B reads it as "video"
        self._fbo_tex = self.ctx.texture(self.wnd.size, 4)
        self._fbo     = self.ctx.framebuffer(color_attachments=[self._fbo_tex])

        # FBO2 for auto-effect accent layer: rendered on original video, blended over screen
        self._fbo2_tex = self.ctx.texture(self.wnd.size, 4)
        self._fbo2     = self.ctx.framebuffer(color_attachments=[self._fbo2_tex])
        self._auto_blend_prog = self.ctx.program(
            vertex_shader=VERT, fragment_shader=_AUTO_BLEND_FRAG)
        self._auto_blend_vao  = self.ctx.vertex_array(
            self._auto_blend_prog, [(self._vbo, '2f', 'in_position')])
        self._auto_blend_prog['overlay'] = 1   # texture unit 1

        global _new_fps
        _new_fps = None

        self.frame_interval  = 1.0 / _init_fps
        self.last_frame_time = 0.0
        self._fps_frames     = 0
        self._fps_accum      = 0.0
        self._audio_timer    = 0.0
        self._smooth_energy   = 0.0
        self._flip_active     = False  # True while beat-triggered flip is on
        self._flip_timer      = 0.0   # counts down; flip holds until this hits 0
        self._prev_beat_high  = False  # rising-edge detection for beat onset

        # Auto-effect accent layer state
        self._auto_current      = None   # effect index currently in accent slot (or None)
        self._auto_blend        = 0.0    # current mix factor (smoothly ramped)
        self._auto_blend_target = 0.0    # 1.0 when accent active, 0.0 when not
        self._auto_beat_prev    = False  # beat edge detection
        self._prev_se           = 0.0    # previous smooth_energy for momentum
        self._momentum          = 0.0    # smoothed dE/dt

        # LED blink state (driven from render loop so auto/preview LEDs can flash)
        # Tick at 8 Hz; slow_phase toggles at 1 Hz, fast_phase at 4 Hz.
        self._led_tick  = 0.0
        self._led_count = 0

        # Solo-preview state
        self._preview_idx     = None   # effect currently being previewed (or None)
        self._preview_entered = False  # True on the first frame of preview (triggers OSD)

        threading.Thread(target=_decode_loop, daemon=True).start()
        threading.Thread(target=_midi_loop, daemon=True).start()

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=2, dtype='float32',
            blocksize=BLOCK_SIZE, device=AUDIO_DEVICE, callback=_audio_callback,
        )
        self._stream.start()

    def _set_effect_uniforms(self, prog, t, intensity, params, bass, mid, treble, beat, sw):
        _set_uniform(prog, 'resolution',   self.wnd.size)
        _set_uniform(prog, 'time',         t)
        _set_uniform(prog, 'bass',         float(bass))
        _set_uniform(prog, 'mid',          float(mid))
        _set_uniform(prog, 'treble',       float(treble))
        _set_uniform(prog, 'beat',         float(beat))
        _set_uniform(prog, 'intensity',    float(intensity))
        _set_uniform(prog, 'param_a',      float(params['param_a']))
        _set_uniform(prog, 'param_b',      float(params['param_b']))
        _set_uniform(prog, 'param_c',      float(params['param_c']))
        _set_uniform(prog, 'stereo_width', float(sw))

    def on_render(self, time, frametime):
        global _new_fps, _osd_trigger

        # ── MIDI reset combo poll ─────────────────────────────────────────────
        held = dict(_reset_held)
        now  = _monotonic()
        # Evict stale entries (pressed > 10 s ago without completing the combo)
        _reset_held.update({k: v for k, v in held.items() if now - v <= 10.0})
        for k in [k for k, v in held.items() if now - v > 10.0]:
            _reset_held.pop(k, None)
        if (len(held) == 3 and
                all(k in held for k in _RESET_NOTES) and
                now - max(held.values()) >= _RESET_HOLD_S):
            print("reset combo held — restarting", flush=True)
            for n in MUTE + RECARM:
                _set_led(n, False)
            os._exit(1)
        # ─────────────────────────────────────────────────────────────────────

        if _new_fps is not None:
            self.frame_interval = 1.0 / _new_fps
            _new_fps = None

        if _osd_trigger is not None:
            self._osd_color = _osd_trigger
            self._osd_timer = OSD_DURATION
            _osd_trigger = None

        self._fps_frames += 1
        self._fps_accum  += frametime
        self._audio_timer += frametime
        if self._fps_accum >= 5.0:
            effects = list(_active_effects)
            names   = '+'.join(SHADERS[i][0] for i in effects) if effects else 'none'
            print(f"render: {self._fps_frames / self._fps_accum:.1f} fps  fx: {names}")
            self._fps_frames = 0
            self._fps_accum  = 0.0

        with _lock:
            br, mr, tr, bt, sw = (_bands['bass'], _bands['mid'],
                                   _bands['treble'], _bands['beat'],
                                   _bands['stereo_width'])

        # Model B — ceiling-normalizer (see docs/intensity-models.md)
        master_scale = _m_master * 3.0
        raw_energy   = min(br * 2.5 + mr * 0.8 + tr * 0.4, 1.0)
        rate = 0.4 if raw_energy > self._smooth_energy else 0.08
        self._smooth_energy += rate * (raw_energy - self._smooth_energy)
        energy_scaled = min(self._smooth_energy * master_scale, 1.0)

        ms     = master_scale
        bass   = min(float(br) * ms, 1.0)
        mid    = min(float(mr) * ms, 1.0)
        treble = min(float(tr) * ms, 1.0)
        beat   = min(float(bt) * ms, 1.0)

        if self._audio_timer >= 1.0:
            print(f"bass={bass:.3f}  mid={mid:.3f}  treble={treble:.3f}  "
                  f"beat={beat:.3f}  lvl={self._smooth_energy:.2f}")
            self._audio_timer = 0.0

        # Upload next video frame if due
        if time - self.last_frame_time >= self.frame_interval:
            try:
                frame = frame_queue.get_nowait()
                self.texture.write(frame.tobytes())
                self.last_frame_time = time
            except queue.Empty:
                pass

        # Beat-triggered screen flip: ~5% chance per beat onset, holds 0.4s.
        # Uses raw pre-master bt for detection so master level doesn't suppress it.
        beat_high = float(bt) > 0.8
        if beat_high and not self._prev_beat_high and random.random() < 0.05:
            self._flip_timer = 0.4
        self._prev_beat_high = beat_high
        self._flip_timer  = max(0.0, self._flip_timer - frametime)
        self._flip_active = self._flip_timer > 0.0

        # ── auto-effect probability logic ─────────────────────────────────────
        # Momentum: smoothed derivative of smooth_energy (positive = building)
        delta = self._smooth_energy - self._prev_se
        self._momentum = self._momentum * AUTO_MOMENTUM_SMOOTH + delta * (1.0 - AUTO_MOMENTUM_SMOOTH)
        self._prev_se  = self._smooth_energy
        # Normalise momentum to 0..1: 0 = falling, 0.5 = flat, 1 = building fast
        momentum_norm = min(max(self._momentum * AUTO_MOMENTUM_SCALE + 0.5, 0.0), 1.0)

        auto_beat = float(bt) > AUTO_BEAT_THRESHOLD
        if auto_beat and not self._auto_beat_prev and _auto_effects:
            if self._auto_current is None:
                # Chance to activate scales with momentum (building energy → more likely)
                p_on = AUTO_P_ON_FLOOR + momentum_norm * AUTO_P_ON_MOMENTUM
                if random.random() < p_on:
                    self._auto_current      = random.choice(list(_auto_effects))
                    self._auto_blend_target = 1.0
            else:
                # Chance to deactivate scales with falling energy
                p_off = AUTO_P_OFF_FLOOR + (1.0 - momentum_norm) * AUTO_P_OFF_MOMENTUM
                if random.random() < p_off:
                    self._auto_current      = None
                    self._auto_blend_target = 0.0
                elif len(_auto_effects) > 1 and random.random() < AUTO_P_DRIFT:
                    # Occasionally drift to a different effect in the pool
                    candidates = [e for e in _auto_effects if e != self._auto_current]
                    self._auto_current = random.choice(candidates)
        self._auto_beat_prev = auto_beat

        # If pool was cleared externally (slot change), retire active auto effect
        if self._auto_current is not None and self._auto_current not in _auto_effects:
            self._auto_current      = None
            self._auto_blend_target = 0.0

        # Smooth blend ramp
        if self._auto_blend < self._auto_blend_target:
            self._auto_blend = min(self._auto_blend_target,
                                   self._auto_blend + AUTO_BLEND_RATE * frametime)
        else:
            self._auto_blend = max(self._auto_blend_target,
                                   self._auto_blend - AUTO_BLEND_RATE * frametime)
        # ─────────────────────────────────────────────────────────────────────

        # ── solo-preview detection ────────────────────────────────────────────
        prev_preview = self._preview_idx
        self._preview_idx = None
        now_p = _monotonic()
        for i, n in enumerate(MUTE):
            press_t = _mute_hold_time.get(n)
            if press_t and now_p - press_t >= PREVIEW_HOLD_S:
                self._preview_idx = _effect_page * 8 + i
                break
        if self._preview_idx is not None and prev_preview is None:
            self._preview_entered = True   # first frame: trigger OSD flash
        # ─────────────────────────────────────────────────────────────────────

        # ── LED blink tick (8 Hz; slow=1 Hz, fast=4 Hz) ──────────────────────
        self._led_tick += frametime
        if self._led_tick >= 0.125:   # 8 Hz
            self._led_tick  -= 0.125
            self._led_count += 1
            slow_phase = bool(self._led_count % 8 < 4)   # on 4 ticks, off 4 → 1 Hz
            fast_phase = bool(self._led_count % 2 == 0)  # on 1 tick,  off 1 → 4 Hz
            if (_auto_effects or self._preview_idx is not None) and _midi_out:
                _effect_leds(_active_effects, slow_phase=slow_phase,
                             fast_phase=fast_phase, preview_idx=self._preview_idx)
        # ─────────────────────────────────────────────────────────────────────

        # For single-effect or final-screen render: choose normal or flip progs.
        screen_progs = self._progs_flip if self._flip_active else self._progs

        effects = list(_active_effects)   # stable snapshot for this frame

        # ── solo-preview render override ──────────────────────────────────────
        if self._preview_idx is not None and self._preview_idx in self._progs:
            if self._preview_entered:
                _osd_trigger = (1.0, 0.55, 0.0)   # orange flash on entry
                self._preview_entered = False
            prog, vao = self._progs[self._preview_idx]
            params = _effect_params[self._preview_idx]
            self.ctx.screen.use()
            self.ctx.clear()
            self.texture.use(location=0)
            self._set_effect_uniforms(prog, time, params['intensity'] * energy_scaled,
                                      params, bass, mid, treble, beat, sw)
            vao.render(moderngl.TRIANGLE_STRIP)
            # Skip normal render + auto accent; jump straight to OSD
        elif not effects:
            # No effects active: show raw video
            self.ctx.screen.use()
            self.ctx.clear()
            self.texture.use(location=0)
            self._passthrough_vao.render(moderngl.TRIANGLE_STRIP)

        elif len(effects) == 1:
            idx = effects[0]
            if idx in screen_progs:
                prog, vao = screen_progs[idx]
                params = _effect_params[idx]
                self._set_effect_uniforms(
                    prog, time, params['intensity'] * energy_scaled,
                    params, bass, mid, treble, beat, sw)
                self.ctx.screen.use()
                self.ctx.clear()
                self.texture.use(location=0)
                vao.render(moderngl.TRIANGLE_STRIP)

        else:
            # Two effects: A → FBO, then B reads FBO as its "video" input.
            # Pass 1 always uses _progs_flip so the FBO stores content with the same
            # y=0-at-top orientation as the video texture (double-flip cancels in Pass 2).
            idx_a, idx_b = effects[0], effects[1]
            if idx_a in self._progs_flip and idx_b in screen_progs:
                prog_a, vao_a = self._progs_flip[idx_a]
                prog_b, vao_b = screen_progs[idx_b]
                params_a = _effect_params[idx_a]
                params_b = _effect_params[idx_b]

                # Pass 1: render effect A into FBO (position-flipped to fix orientation)
                self._fbo.use()
                self._fbo.clear()
                self._set_effect_uniforms(
                    prog_a, time, params_a['intensity'] * energy_scaled,
                    params_a, bass, mid, treble, beat, sw)
                self.texture.use(location=0)
                vao_a.render(moderngl.TRIANGLE_STRIP)

                # Pass 2: render effect B to screen, feeding A's output as "video"
                self.ctx.screen.use()
                self.ctx.clear()
                self._set_effect_uniforms(
                    prog_b, time, params_b['intensity'] * energy_scaled,
                    params_b, bass, mid, treble, beat, sw)
                self._fbo_tex.use(location=0)
                vao_b.render(moderngl.TRIANGLE_STRIP)

                # Restore video texture binding for next frame upload
                self.texture.use(location=0)

        # ── auto-effect accent blend (skipped during solo preview) ───────────
        # Render auto effect on original video into FBO2, then blend over screen.
        # Uses _progs_flip for correct orientation (same double-flip logic as pass 1).
        if self._preview_idx is None and self._auto_blend > 0.001 and self._auto_current in self._progs_flip:
            prog_auto, vao_auto = self._progs_flip[self._auto_current]
            params_auto = _effect_params[self._auto_current]
            self._fbo2.use()
            self._fbo2.clear()
            self._set_effect_uniforms(
                prog_auto, time, params_auto['intensity'] * energy_scaled,
                params_auto, bass, mid, treble, beat, sw)
            self.texture.use(location=0)   # original video
            vao_auto.render(moderngl.TRIANGLE_STRIP)

            self.ctx.screen.use()
            self._fbo2_tex.use(location=1)
            self._auto_blend_prog['blend_alpha'].value = self._auto_blend * AUTO_BLEND_MAX
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self._auto_blend_vao.render(moderngl.TRIANGLE_STRIP)
            self.ctx.disable(moderngl.BLEND)
            self.texture.use(location=0)   # restore
        # ─────────────────────────────────────────────────────────────────────

        # OSD bank/page flash
        if self._osd_timer > 0:
            self._osd_timer -= frametime
            alpha = max(0.0, self._osd_timer / OSD_DURATION) * 0.90
            self._osd_prog['osd_color'] = (*self._osd_color, alpha)
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self._osd_vao.render(moderngl.TRIANGLE_STRIP)
            self.ctx.disable(moderngl.BLEND)

    def key_event(self, key, action, modifiers):
        if action != self.wnd.keys.ACTION_PRESS:
            return
        if key == self.wnd.keys.Q:
            self.wnd.close()


# ── startup ───────────────────────────────────────────────────────────────────
_select_slot(1, 1)
if _requested_video is None and os.path.exists(FALLBACK_VIDEO):
    _requested_video = FALLBACK_VIDEO
    print(f"fallback: {FALLBACK_VIDEO}")

if _requested_video:
    with av.open(_requested_video) as _c:
        _s = _c.streams.video[0]
        _init_w   = _s.width
        _init_h   = _s.height
        _init_fps = float(_s.average_rate or _s.guessed_rate or 30)
    print(f"video: {_init_w}x{_init_h} @ {_init_fps:.3f} fps")
else:
    _init_w, _init_h, _init_fps = 1920, 1080, 30.0
    print("WARNING: no video found — add videos/bank1/video1/*.mp4")

if __name__ == '__main__':
    mglw.run_window_config(VGLRApp)
