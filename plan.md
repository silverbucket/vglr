# vglr build plan

`vglr.py` was mpv-based — fully replaced. Architecture: Python + moderngl + PyAV + sounddevice + numpy.

## Step 5: incremental pipeline

### 5a — moderngl-window + static shader  [CURRENT]
- Open window (1920×1080), draw animated UV gradient via GLSL 330 fragment shader.
- Prove moderngl-window works before Pi-specific backends.
- Test locally; Q to quit.

### 5b — PyAV video decode → texture
- Decode video in a thread with PyAV (use `h264_v4l2m2m` on Pi, software fallback on desktop).
- Upload each frame as a `moderngl` Texture, display through shader.
- No audio yet; shader just passes video through.

### 5c — sounddevice audio → shared FFT state
- Add non-blocking `sounddevice` InputStream callback.
- numpy FFT → smoothed `bass`/`mid`/`treble` floats + `beat` onset spike.
- Shared state via lock-protected floats; printout confirms live update.
- Testable on desktop with built-in mic.

### 5d — port vhs.glsl + wire audio uniforms
- Convert `shaders/vhs.glsl` from mpv `//!HOOK` format to GLSL 330 with uniforms:
  `video`, `resolution`, `time`, `bass`, `mid`, `treble`, `beat`
- Modulate `wiggle`/`smear` by audio bands.
- Full pipeline: glitchy VHS video reacting to mic.
- Pi required here: DRM backend, USB sound card.

## Notes
- 5a–5c: develop and test on desktop.
- 5d: needs Pi for DRM/EGL fullscreen and USB audio device.
- moderngl-window backend order to try on Pi: EGL → SDL2 over DRM.
- Hardware decode on Pi: `av.CodecContext.create('h264_v4l2m2m')`.
- If perf tight: drop to 720p or simplify shader.
