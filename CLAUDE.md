# vglr — Project Context

## Goal

Build an **audio-reactive video glitch player** for live shows / projections.

- Play a video clip as a base layer.
- Apply GLSL shader effects (VHS, glitch, etc.) on top.
- Modulate shader parameters in real time from live audio input (USB sound card).
- Runs on **Raspberry Pi 5, 4GB RAM**, fullscreen output via DRM (no desktop), over HDMI to a projector.
- Target: 1080p, fall back to 720p if perf demands.

## Hardware / OS

- Raspberry Pi 5, 4GB RAM
- Running headless, accessed over SSH
- Output: HDMI to projector, fullscreen via DRM (no X/Wayland)
- USB sound card for low-latency audio input (model TBD)
- User is on Arch-derivative Linux on desktop; Pi runs Raspberry Pi OS (Debian-based)

## Current repo state

```
vglr/
├── shaders/
│   ├── vhs.glsl           # WORKS with mpv (uses //!HOOK MAIN directives)
│   └── vhs-glitch.glsl    # Godot format (shader_type canvas_item) — NOT mpv-compatible, ignore for now
├── videos/
│   └── fb_rev_wet_mop_reimagined.mp4   # 1080p H.264 test clip
├── playlist.json
└── vglr.py                # existing Python entry point — needs to be read & evaluated
```

## What we've learned so far (mpv exploration phase)

We initially tried using mpv as the shader runtime. Findings:

- `mpv --vo=gpu` **silently fails to load user shaders** on Pi (GLES profile too limited; libplacebo's `frame` uniform not provided in old VO).
- `mpv --vo=gpu-next` **works** — uses libplacebo, compiles `//!HOOK`-style shaders correctly.
- Working command:
  ```
  mpv --fullscreen --vo=gpu-next --gpu-context=drm \
      --hwdec=v4l2m2m-copy \
      --glsl-shaders=shaders/vhs.glsl --no-audio \
      videos/fb_rev_wet_mop_reimagined.mp4
  ```
- **The blocker:** mpv user shaders **cannot receive live audio uniforms.** No hook for FFT/RMS/beat data into a running shader. You can only swap shaders or change parameters via IPC, which gives stepped/triggered reactivity, not continuous modulation.
- Therefore, **mpv is being abandoned as the shader runtime** in favor of a custom Python pipeline.

## Chosen architecture

**Python + moderngl + PyAV + sounddevice + numpy**

```
┌─────────────────┐         ┌──────────────────┐
│ Audio thread    │         │ Render thread    │
│ (sounddevice)   │         │ (moderngl-window)│
│                 │         │                  │
│ mic → buffer →  │         │ loop:            │
│ FFT → bands →   │ ──────► │  pyav.next_frame │
│ shared state    │  audio  │  upload texture  │
│                 │  values │  read audio vals │
└─────────────────┘         │  set uniforms    │
                            │  draw shader     │
                            │  swap buffers    │
                            └──────────────────┘
```

### Components

- **PyAV** (`av`) — decode video frames from disk. Use `h264_v4l2m2m` codec for Pi hardware decode.
- **moderngl** — OpenGL wrapper. Upload each frame as a texture, run fragment shader with live uniforms, render to screen.
- **moderngl-window** — handles window/fullscreen/main loop boilerplate. Use the EGL backend or DRM/KMS for fullscreen-without-desktop on the Pi.
- **sounddevice** — captures from USB sound card via PortAudio. Non-blocking callback API, runs in its own thread.
- **numpy** — FFT for frequency bands (bass/mid/treble); simple onset detection for beat triggers.
- **aubio** (optional, later) — more robust beat/onset detection if numpy-based detection isn't tight enough.

### Shader format

Port existing `vhs.glsl` from mpv hook format to standard GLSL 330 fragment shader with these uniforms:

```glsl
uniform sampler2D video;
uniform vec2 resolution;
uniform float time;
uniform float bass;    // 0.0 - 1.0, smoothed
uniform float mid;
uniform float treble;
uniform float beat;    // spikes to 1.0 on onset, decays exponentially
```

Existing `vhs.glsl` uses `HOOKED_raw`, `HOOKED_pos`, `HOOKED_size`, `hook()` entry point — these need replacement with standard sampler/uv/main equivalents. Once ported, modulate existing parameters like `wiggle` and `smear` by audio bands (e.g. `wiggle *= (1.0 + bass * 3.0)`).

### Perf budget on Pi 5

- 1080p H.264 decode via v4l2m2m: ~5% CPU, hardware-accelerated.
- Single fragment shader pass at 1080p60: VideoCore VII handles `vhs.glsl`-complexity fine.
- Audio FFT (1024 samples @ 48kHz): ~0.1ms in numpy.
- Memory: ~300-500MB total. Comfortable on 4GB.
- If perf becomes tight: drop to 720p, reduce shader complexity, or single-pass only.

## Open questions / TODO for first session

1. **Read `vglr.py`** — what does it currently do? Does it use mpv (now obsolete), or has it already started on a moderngl pipeline?
2. **Decide: extend `vglr.py` or start fresh?** Depends on #1.
3. **Identify the USB sound card** — `arecord -l` on the Pi.
4. **Set up Python env** — venv with `moderngl moderngl-window av sounddevice numpy`. Pi OS may need `--break-system-packages` or `python3-venv`.
5. **Build pipeline incrementally:**
   - a. moderngl-window opens fullscreen, displays a static test pattern via shader.
   - b. PyAV decodes video, feeds frames as textures into the moderngl loop.
   - c. sounddevice captures audio, computes FFT bands, exposes shared state.
   - d. Port `vhs.glsl` to standalone GLSL, wire audio uniforms in.
6. **Fullscreen output on Pi without desktop** — moderngl-window's DRM/KMS or EGL backend. May need experimentation; SDL2 backend over DRM is a fallback.

## User preferences

- Linux power user (Arch background)
- Comfortable with SSH-only workflow
- Wants direct file editing, not copy-paste from chat
- Will test on actual hardware
