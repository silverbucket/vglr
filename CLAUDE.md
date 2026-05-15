# vglr — Project Context

## Goal

Build an **audio-reactive video glitch player** for live shows / projections.

- Play a video clip as a base layer.
- Apply GLSL shader effects (VHS, glitch, etc.) on top.
- Modulate shader parameters in real time from live audio input (USB sound card).
- Runs on **Raspberry Pi 5, 4GB RAM**, fullscreen output via DRM (no desktop), over HDMI to a projector.

## Hardware / OS

- Raspberry Pi 5, 4GB RAM — headless, accessed over SSH
- Output: HDMI to projector, fullscreen via DRM (no X/Wayland)
- Audio input: **Zoom F1** field recorder as USB sound card (`AUDIO_DEVICE = 1`, hw:2,0)
- MIDI controller: **AKAI MIDI Mix** (8-channel mixer form factor, USB)
- User is on Arch-derivative Linux on desktop; Pi runs Raspberry Pi OS (Debian-based)

## Current state — pipeline is fully working

Run command on the Pi:
```
SDL_VIDEODRIVER=kmsdrm python vglr.py --window sdl2 --fullscreen
```

Stack: **Python + moderngl + PyAV + sounddevice + numpy + mido**

- `vglr.py` — single-file entry point, all logic here
- `shaders/` — GLSL 140 fragment shaders (8 currently loaded)
- `videos/bank{N}/video{M}/` — video clip filesystem; slot settings stored as `settings.json` in same dir

## AKAI MIDI Mix mapping

```
MUTE buttons (1–8)   → select active shader/effect (from current effect page)
REC ARM buttons (1–8)→ select video slot (1–8) within current bank
BANK L / BANK R      → navigate video banks (bank1..bankN); OSD flash confirms
SOLO                 → cycle effect page (page 1 = effects 1–8, page 2 = 9–16, …)
                       purple OSD flash on page change; all Mute LEDs off if active
                       effect is on a different page
SEND ALL (top right) → save current slot settings to settings.json
                       detected via CC burst (fires all 33 CCs simultaneously);
                       CCs also re-sync hardware state as a side effect
Fader (strip N)      → ceiling intensity for effect N (0=always off, 1=can fully saturate)
Knob row 1 (strip N) → param_a  (shader-specific, e.g. speed)
Knob row 2 (strip N) → param_b  (shader-specific, e.g. scale)
Knob row 3 (strip N) → param_c  (shader-specific, e.g. colour shift)
Master fader         → signal normalizer: 0=silent, 127=3× amplification
                       raise for acoustic/quiet shows, lower for loud/dense shows
```

LEDs: active slot lit on REC ARM row; active effect lit on MUTE row (only when on matching page).

## Shader uniforms (standard across all shaders)

```glsl
uniform sampler2D video;      // current video frame
uniform vec2  resolution;
uniform float time;
uniform float bass;           // 0.0–1.0, smoothed FFT energy 20–250 Hz
uniform float mid;            // 250–4000 Hz
uniform float treble;         // 4000+ Hz
uniform float beat;           // spikes to 1.0 on onset, decays (BEAT_DECAY = 0.85)
uniform float intensity;      // derived: fader × clamp(smooth_energy × master_scale, 0, 1)
uniform float param_a;        // MIDI knob row 1
uniform float param_b;        // MIDI knob row 2
uniform float param_c;        // MIDI knob row 3
uniform float stereo_width;   // L–R channel difference, 0–1 (peaks on transient stereo events)
```

All shaders use `#version 140` (Pi 5 Mesa V3D caps at OpenGL 3.1 Core — not 3.3).

## Current shaders (slot order = MUTE button order)

1. `vhs.glsl`         — VHS scan jitter, colour smear, Y/C noise
2. `block_glitch.glsl`— rectangular block displacement
3. `kaleidoscope.glsl`— radial mirror/tile
4. `vortex.glsl`      — swirl/warp
5. `rgb_orbit.glsl`   — RGB channel orbit/separation
6. `pixel_sort.glsl`  — pixel sorting columns
7. `contour.glsl`     — edge/contour detection overlay
8. `melt.glsl`        — vertical melt/drip

Also present but not in active rotation: `vhs-glitch.glsl` (Godot format, ignore), `vhs-tape-shader.glsl`, `morpholog.glsl`, `passthrough.glsl`.

## Bank / slot filesystem

```
videos/
  bank1/
    video1/
      clip.mp4
      settings.json   ← shader name, intensity, param_a/b/c, beat_thresh
    video2/
      ...
  bank2/
    ...
```

If no video exists for a slot, the previous clip keeps playing. Settings are per-slot and saved on SOLO press.

## Performance (measured on Pi 5)

- **720p output, 7-sample blur** → ~15 fps (current working config)
- 1080p untested with complex shaders; likely ~10 fps
- Audio FFT at 1024 samples/44.1kHz: ~0.1ms
- `GAIN = 200.0` currently; tune per venue

## Audio → visual coupling

Active model: **ceiling-normalizer** — see `docs/intensity-models.md` for full history and rollback instructions.

- `master_scale` = `master_fader × 3.0`  (MIDI 0–127 → 0–3× amplification)
- `energy_scaled` = `clamp(smooth_energy × master_scale, 0, 1)`
- `intensity` = `fader × energy_scaled`
  - `fader` = ceiling (0 = always off; 1 = can reach full saturation with sufficient audio)
  - `master_fader` = signal normalizer: raise for acoustic shows, lower for loud shows
- `bass`, `mid`, `treble`, `beat` uniforms are all scaled by `master_scale` before shaders receive them
- Beat detection: energy ratio threshold (`BEAT_THRESH = 1.8`)
- Snappy attack (rate 0.4), slow release (rate 0.08) for smooth intensity envelope
- Audio is stereo (2 channels from Zoom F1); mono = L+R average; `stereo_width` = abs(L−R)
- `stereo_width` peaks on transient stereo events (cymbals, room reverb, panned hits)

## Architecture

```
┌─────────────────┐         ┌──────────────────┐    ┌──────────────┐
│ Audio thread    │         │ Render thread    │    │ MIDI thread  │
│ (sounddevice)   │         │ (moderngl-window)│    │ (mido)       │
│                 │         │                  │    │              │
│ mic → FFT →     │──────►  │ pyav frame →     │◄── │ knobs/faders │
│ bass/mid/treble │ bands   │ texture upload   │    │ → uniforms   │
│ beat detection  │         │ uniforms → shader│    │ buttons →    │
└─────────────────┘         │ render quad      │    │ slot/bank    │
                            └──────────────────┘    └──────────────┘
```

## Known constraints & decisions

- **No mpv** — abandoned because mpv user shaders can't receive live audio uniforms.
- **OpenGL 3.1 only** — Pi 5 Mesa V3D 7.1.10.2 hard cap. Use `gl_version = (3, 1)` and `#version 140` everywhere.
- **SDL2/KMS backend** — `SDL_VIDEODRIVER=kmsdrm` required for fullscreen without desktop.
- **GIL as lock** — audio/MIDI threads write simple floats; Python GIL provides sufficient atomicity for these reads.

## User preferences

- Linux power user (Arch background), comfortable with SSH-only workflow
- Wants direct file editing, not copy-paste from chat
- Tests on actual Pi hardware
