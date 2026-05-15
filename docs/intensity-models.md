# Intensity Models

Two named models for how the track fader and master fader interact with
the audio signal to drive effect intensity. The active model lives in
`vglr.py` → `on_render()`.

To switch back to a model, restore `vglr.py` from the relevant commit:

```bash
git checkout <commit> -- vglr.py
```

---

## Model A — "floor-sensitivity"  *(last commit: c847b5c)*

### Behaviour

| Control | Role |
|---------|------|
| Track fader | **Floor** — minimum effect level always visible even at silence |
| Master fader | **Sensitivity** — how much loud audio adds on top of the floor (0–1×) |

```
intensity = fader + smooth_energy × (1 − fader) × master
```

All band uniforms (`bass`, `mid`, `treble`, `beat`) passed to shaders raw
(scaled by `GAIN` only, not by master).

### Characteristics

- Fader at 0, loud audio, master = 1.0 → intensity = 1.0 (effect fully
  on even with fader down — the floor is only "off" at silence)
- Fader at 1 → always fully on regardless of audio
- Master does not affect internal shader band effects — a low master makes
  the blend more subtle but warp/distortion/cell animation inside shaders
  still track the raw audio energy

### Suited for

Situations where you want a constant baseline aesthetic: the effect is
always present at some level and audio pushes it further. Master is a
sensitivity fine-tune, not a venue calibration.

---

## Model B — "ceiling-normalizer"  *(introduced: d05cb0e)*

### Behaviour

| Control | Role |
|---------|------|
| Track fader | **Ceiling** — maximum effect level; 0 = always off, 1 = can reach full saturation |
| Master fader | **Signal normalizer** — scales all audio 0–3× before hitting the effect |

```
master_scale  = master × 3.0
energy_scaled = clamp(smooth_energy × master_scale, 0, 1)
intensity     = fader × energy_scaled

bass   = clamp(raw_bass   × master_scale, 0, 1)   # also passed to shaders scaled
mid    = clamp(raw_mid    × master_scale, 0, 1)
treble = clamp(raw_treble × master_scale, 0, 1)
beat   = clamp(raw_beat   × master_scale, 0, 1)
```

### Characteristics

- Fader at 0 → always off regardless of master or audio level ✓
- Fader at 1 → effect can reach full saturation when audio × master_scale ≥ 1
- At silence → intensity = 0 regardless of fader position (no floor)
- Master scales EVERYTHING uniformly: both the blend and all internal
  shader band effects move together

### Master calibration guide

| Show type | Master setting | Effect |
|-----------|---------------|--------|
| Loud / dense (post-punk, techno) | Low (MIDI ~20–50) | Compresses loud signals; preserves variation among loud parts |
| Medium / mixed | Mid (MIDI ~55–80) | Roughly equivalent to old model at sensitivity = 1 |
| Quiet / acoustic | High (MIDI ~90–127) | Amplifies quiet signals; effects fire on subtle sounds |

MIDI 127 → 3× amplification. At mid position (~MIDI 42) master_scale ≈ 1.0,
which reproduces the old Model A sensitivity=1 behaviour for the energy
envelope (bands are still affected, unlike Model A).

### Suited for

Per-gig venue calibration at soundcheck. Set master once to normalise the
room's dynamic range into the 0–1 band space. Track faders then give a
clean min–max range that behaves identically regardless of how loud the
show is.

---

## Switching

```bash
# Restore Model A (floor-sensitivity)
git checkout c847b5c -- vglr.py

# Restore Model B (ceiling-normalizer)
git checkout d05cb0e -- vglr.py
```

After switching, restart vglr.
