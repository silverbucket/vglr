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

## All 5 steps DONE. Pipeline working. Next:

### FPS / performance
- Currently ~15 fps at 720p with 7-sample blur (was 7.5fps at 1080p/15-sample).
- Try 5-sample blur: should push to ~18–20 fps.
- Try 1080p with 5-sample: probably ~10 fps, likely not worth it.
- Investigate whether v4l2m2m hardware decode of video frames reduces CPU pressure enough to help.
- Consider: accept 15fps as the aesthetic; glitch art doesn't need to be smooth.

### Tuning / calibration
- GAIN (currently 50.0) should be adjustable per-gig depending on how loud the band is.
- Effect coefficients (bass*0.12, beat*0.2, etc.) need real-world tuning at volume.
- Consider adding a "dry/wet" blend so the effect can fade in/out (mix raw video with shader output).

### Playlist / video switching
- Current: single video, loops. Need multi-video support from playlist.json.
- decode_loop should support switching video mid-playback on signal.
- playlist.json already exists — parse it, preload next video metadata.

### Additional shaders
- vhs-glitch.glsl exists in Godot format — port it similarly (needs same GLSL 1.40 treatment).
- Shader hot-swap: load new .glsl file at runtime without restart.
- Consider a "passthrough" shader (no effect) as slot 0 for clean moments.

### MIDI Mix controller  [IN PROGRESS — see below]
- Akai MIDI Mix plugged in, kernel sees it (idVendor=09e8, idProduct=0031).
- Use for: video slot selection, per-band gain, effect toggles, LED feedback.

### Beat detection improvement
- Current: simple energy ratio (BEAT_THRESH). Works but fires on any transient.
- aubio library: proper onset/beat detection. Add if beat triggering is too noisy.
- Consider low-pass filtering energy_smooth to ignore rapid transients.
