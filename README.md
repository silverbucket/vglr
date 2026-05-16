# vglr

Audio-reactive video glitch player for live shows and projections.

Plays video clips through GLSL shader effects whose parameters are modulated in real time from live audio input. Designed to run headless on a Raspberry Pi 5 over HDMI to a projector, controlled via an AKAI MIDI Mix.

---

## Hardware

| Component | Details |
|-----------|---------|
| Raspberry Pi 5 | 4 GB RAM, headless (SSH only) |
| Display | HDMI to projector, fullscreen via KMS/DRM (no desktop) |
| Audio input | Zoom F1 (or H6) as USB sound card |
| MIDI controller | AKAI MIDI Mix |

---

## Quick start

```bash
# on the Pi
git pull
SDL_VIDEODRIVER=kmsdrm venv/bin/python vglr.py --window sdl2 --fullscreen
```

Press `Q` to quit.

For automatic start on boot, see [Pi Setup](docs/raspi-setup.md).

---

## Video library layout

Videos are organised into banks and slots. Each slot holds one video clip and a `settings.json` that stores the last-saved effect and knob positions.

```
videos/
  bank1/
    video1/
      clip.mp4
      settings.json    ← created when you press SEND ALL
    video2/
      another.mp4
    ...
  bank2/
    video1/
      ...
  ...
```

Any `.mp4`, `.mkv`, or `.mov` file in a slot directory is used. If a slot has no video, the previously-playing clip continues. If no slot has a video at all, `videos/fb_rev_wet_mop_reimagined.mp4` is used as a fallback.

---

## MIDI Mix controls

```
┌──────────────────────────────────────────────────┐  ┌──────────┐
│  [MUTE 1] [MUTE 2] [MUTE 3] [MUTE 4]            │  │ SEND ALL │ → save settings
│  [MUTE 5] [MUTE 6] [MUTE 7] [MUTE 8]            │  └──────────┘
│                                                  │
│  [REC 1]  [REC 2]  [REC 3]  [REC 4]             │
│  [REC 5]  [REC 6]  [REC 7]  [REC 8]             │
│                                                  │
│  [BANK◄]  [BANK►]                  [SOLO]        │
│                                                  │
│  [FDR 1]  [FDR 2]  ...  [FDR 8]   [MASTER]      │
│  [KNB 1A] [KNB 2A] ...  [KNB 8A]                │
│  [KNB 1B] [KNB 2B] ...  [KNB 8B]                │
│  [KNB 1C] [KNB 2C] ...  [KNB 8C]                │
└──────────────────────────────────────────────────┘
```

| Control | Function |
|---------|----------|
| **MUTE 1–8** | Toggle effect on/off (from the current effect page). Up to 2 effects can be active simultaneously. Lit LED = active. Press a lit button to deactivate; pressing a 3rd while 2 are active does nothing. |
| **REC ARM 1–8** | Select video slot within the current bank. Lit LED = active slot. |
| **BANK ◄ / ►** | Navigate video banks. Brief colour flash confirms the new bank. |
| **SOLO** | Cycle through effect pages (page 1 = effects 1–8, page 2 = 9–16, …). Purple flash on change. |
| **SEND ALL** | Save current slot settings to `settings.json` (all active effects, their intensities and knob values). |
| **Fader N** | Ceiling intensity for effect N. Always controls effect N on the current page, whether or not it is active. |
| **Knob N row 1** | `param_a` for effect N — always live, even when effect N is not active. |
| **Knob N row 2** | `param_b` for effect N. |
| **Knob N row 3** | `param_c` for effect N. |
| **Master fader** | Signal normalizer (0–3× range). Raise for acoustic/quiet shows to amplify subtle audio; lower for loud/dense shows to preserve variation. Set at soundcheck. |
| **MUTE 1 + BANK ◄ + BANK ► (hold 2 s)** | Emergency restart — hold all three simultaneously for 2 seconds. All LEDs go dark and the service restarts (~3 s). Use if video navigation stops responding. |

The fader and knobs on strip N always control whichever effect is currently selected via MUTE N. Switching video slots (REC ARM) loads that slot's saved settings but does not change which strip is in control.

---

## Effects

Press **SOLO** to toggle between effect pages. Purple OSD flash confirms page change.

### Page 1 (default)

| MUTE | Name | Description | param_a | param_b | param_c |
|------|------|-------------|---------|---------|---------|
| 1 | vhs | VHS scan jitter, colour smear, Y/C noise | wiggle amount | smear strength | noise density |
| 2 | block_glitch | Rectangular block displacement | block size | shift amount | colour split |
| 3 | kaleidoscope | Radial mirror tiles that sway with bass | segment count | sway amount | zoom |
| 4 | vortex | Twist warp that surges on bass/beat | twist strength | falloff sharpness | sway speed |
| 5 | rgb_orbit | RGB channels orbit separately, driven by frequency bands | orbit radius | oscillation speed | channel spread |
| 6 | pixel_sort | Column pixel sorting | sort threshold | sort length | colour mode |
| 7 | contour | Edge/contour detection overlay | edge threshold | line weight | colour blend |
| 8 | melt | Vertical melt/drip | drip speed | drip width | colour shift |

### Page 2 (press SOLO once)

| MUTE | Name | Description | param_a | param_b | param_c |
|------|------|-------------|---------|---------|---------|
| 1 | thermal | Heat-vision palette map; fire or ice mode | palette (fire↔ice) | bloom spread | heat threshold |
| 2 | neon_glow | Neon edge glow on dark background; hue cycles with bass | edge threshold | glow spread | video bleed |
| 3 | lens_warp | Barrel distortion + chromatic aberration; stereo width drives asymmetric pull | distortion strength | aberration split | vignette |
| 4 | slit_scan | Scanline time-delay smear with rainbow colour separation | scan frequency | scan depth | colour spread |
| 5 | posterize | Colour quantization + hue rotation; beat snaps to 2-level pop-art | colour levels | hue rotation speed | saturation boost |
| 6 | tunnel_neon | Neon-lit spoke tunnel rushing toward viewer; beat strobes | spoke count | tunnel speed | video bleed |
| 7 | film_burn | Cinematic halation, light leaks on beat, orange-teal grade, grain | halation strength | grade warmth | grain intensity |
| 8 | mirror_tile | Tiled mirror from a Lissajous-roaming crop window; per-tile colour tint | crop window size | tile count | tint intensity |

To add a page 3, append 8 more entries to the `SHADERS` list in `vglr.py`.

### Shader uniforms

All shaders receive the same uniforms:

```glsl
uniform sampler2D video;      // current video frame
uniform vec2  resolution;
uniform float time;
uniform float bass;           // 0.0–1.0, smoothed 20–250 Hz
uniform float mid;            // 250–4000 Hz
uniform float treble;         // 4000+ Hz
uniform float beat;           // spikes to 1.0 on onset, decays
uniform float intensity;      // fader base + audio drive
uniform float param_a;
uniform float param_b;
uniform float param_c;
uniform float stereo_width;   // abs(L−R), peaks on transient stereo events
```

Use `#version 140` — the Pi 5 Mesa driver caps at OpenGL 3.1 Core.

---

## Configuration

Key constants at the top of `vglr.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `AUDIO_DEVICE` | `1` | sounddevice index for the Zoom F1. Run `venv/bin/python -c "import sounddevice; print(sounddevice.query_devices())"` to list devices. |
| `GAIN` | `200.0` | Overall audio sensitivity. Increase if effects are weak at your venue volume. |
| `BEAT_THRESH` | `1.8` | Energy ratio for beat detection. Lower = more sensitive to transients. |
| `SMOOTH` | `0.3` | Band smoothing (0 = instant, 1 = no movement). |

---

## Pi setup

See [docs/raspi-setup.md](docs/raspi-setup.md) for full installation, service setup, and maintenance instructions.
