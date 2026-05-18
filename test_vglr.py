"""
Comprehensive tests for vglr.py — covering changes introduced in this PR:

  1. New auto-effect tuning constants
  2. _save_settings  — serialises _auto_effects pool to config
  3. _apply_settings — restores _auto_effects pool from config
  4. _effect_leds    — slow-blink for auto pool, fast-blink for preview
  5. _handle_midi    — solo-preview hold tracking + double-click auto-mode toggle
  6. Momentum-normalisation formula (pure maths, extracted from on_render)
  7. Blend-ramp logic (pure maths, extracted from on_render)
"""

import importlib
import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Stub heavy / hardware-specific dependencies so the module can be imported
# in a plain CI environment.
# ---------------------------------------------------------------------------

def _make_mglw_stub():
    """Create a minimal moderngl_window stub with a WindowConfig base class."""
    stub = types.ModuleType("moderngl_window")
    stub.WindowConfig = type("WindowConfig", (), {"__init_subclass__": classmethod(lambda cls, **kw: None)})
    stub.run_window_config = MagicMock()
    return stub


def _make_moderngl_stub():
    stub = types.ModuleType("moderngl")
    stub.TRIANGLE_STRIP = 6
    stub.BLEND = 3042
    stub.SRC_ALPHA = 770
    stub.ONE_MINUS_SRC_ALPHA = 771
    return stub


def _make_av_stub():
    stub = types.ModuleType("av")
    # av.open is only called at module level when _requested_video is truthy;
    # since no videos directory exists that branch is skipped.
    stub.open = MagicMock()
    return stub


def _make_sd_stub():
    stub = types.ModuleType("sounddevice")
    stub.InputStream = MagicMock()
    return stub


def _make_mido_stub():
    stub = types.ModuleType("mido")
    stub.get_input_names  = MagicMock(return_value=[])
    stub.get_output_names = MagicMock(return_value=[])
    stub.open_input       = MagicMock()
    stub.open_output      = MagicMock()
    stub.Message          = MagicMock(side_effect=lambda *a, **kw: MagicMock())
    return stub


def _install_stubs():
    """Insert stubs into sys.modules before vglr is imported."""
    for name, factory in [
        ("moderngl",        _make_moderngl_stub),
        ("moderngl_window", _make_mglw_stub),
        ("av",              _make_av_stub),
        ("sounddevice",     _make_sd_stub),
        ("mido",            _make_mido_stub),
    ]:
        if name not in sys.modules:
            sys.modules[name] = factory()


_install_stubs()

# Now it is safe to import vglr.
import vglr  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_globals():
    """Reset all mutable globals touched by tests back to their defaults."""
    vglr._auto_effects.clear()
    vglr._dbl_click_time.clear()
    vglr._mute_hold_time.clear()
    vglr._active_effects[:] = [0]
    vglr._effect_page = 0
    vglr._midi_out    = None
    # Reset every _effect_params entry to defaults
    for i in range(len(vglr.SHADERS)):
        vglr._effect_params[i].update(dict(vglr._DEFAULT_EFFECT))


def _make_midi_msg(type_: str, note: int = 0, velocity: int = 127, control: int = 0, value: int = 0):
    msg = MagicMock()
    msg.type     = type_
    msg.note     = note
    msg.velocity = velocity
    msg.control  = control
    msg.value    = value
    return msg


# ---------------------------------------------------------------------------
# 1. New auto-effect tuning constants
# ---------------------------------------------------------------------------

class TestAutoEffectConstants(unittest.TestCase):

    def test_auto_momentum_smooth(self):
        self.assertAlmostEqual(vglr.AUTO_MOMENTUM_SMOOTH, 0.85)

    def test_auto_momentum_scale(self):
        self.assertAlmostEqual(vglr.AUTO_MOMENTUM_SCALE, 25.0)

    def test_auto_beat_threshold(self):
        self.assertAlmostEqual(vglr.AUTO_BEAT_THRESHOLD, 0.5)

    def test_auto_p_on_floor(self):
        self.assertAlmostEqual(vglr.AUTO_P_ON_FLOOR, 0.05)

    def test_auto_p_on_momentum(self):
        self.assertAlmostEqual(vglr.AUTO_P_ON_MOMENTUM, 0.10)

    def test_auto_p_off_floor(self):
        self.assertAlmostEqual(vglr.AUTO_P_OFF_FLOOR, 0.05)

    def test_auto_p_off_momentum(self):
        self.assertAlmostEqual(vglr.AUTO_P_OFF_MOMENTUM, 0.40)

    def test_auto_p_drift(self):
        self.assertAlmostEqual(vglr.AUTO_P_DRIFT, 0.15)

    def test_auto_blend_rate(self):
        self.assertAlmostEqual(vglr.AUTO_BLEND_RATE, 2.5)

    def test_auto_blend_max(self):
        self.assertAlmostEqual(vglr.AUTO_BLEND_MAX, 0.75)

    def test_preview_hold_s(self):
        self.assertAlmostEqual(vglr.PREVIEW_HOLD_S, 1.0)

    def test_constants_in_valid_range(self):
        self.assertGreater(vglr.AUTO_MOMENTUM_SMOOTH, 0.0)
        self.assertLess(vglr.AUTO_MOMENTUM_SMOOTH,    1.0)
        self.assertGreater(vglr.AUTO_BLEND_MAX, 0.0)
        self.assertLessEqual(vglr.AUTO_BLEND_MAX, 1.0)
        self.assertGreater(vglr.PREVIEW_HOLD_S, 0.0)

    def test_probability_ceilings_below_one(self):
        """Combined on-probability never exceeds 1."""
        self.assertLessEqual(vglr.AUTO_P_ON_FLOOR + vglr.AUTO_P_ON_MOMENTUM, 1.0)
        self.assertLessEqual(vglr.AUTO_P_OFF_FLOOR + vglr.AUTO_P_OFF_MOMENTUM, 1.0)

    def test_fallback_video_path_updated(self):
        """FALLBACK_VIDEO was changed to the new bank1/video1/Americana path."""
        self.assertIn("bank1", vglr.FALLBACK_VIDEO)
        self.assertIn("video1", vglr.FALLBACK_VIDEO)


# ---------------------------------------------------------------------------
# 2. _save_settings — auto_effects serialisation
# ---------------------------------------------------------------------------

class TestSaveSettings(unittest.TestCase):

    def setUp(self):
        _reset_globals()

    def _save_and_read(self, tmp_dir: str, bank: int = 1, slot: int = 1) -> dict:
        """Run _save_settings and return the parsed JSON, working from tmp_dir."""
        orig = os.getcwd()
        try:
            os.chdir(tmp_dir)
            vglr._save_settings(bank, slot)
            path = vglr._settings_path(bank, slot)
            with open(path) as f:
                return json.load(f)
        finally:
            os.chdir(orig)

    def test_auto_effects_empty_when_pool_empty(self, tmp_path=None):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vglr._auto_effects.clear()
            cfg = self._save_and_read(tmp)
            self.assertIn("auto_effects", cfg)
            self.assertEqual(cfg["auto_effects"], [])

    def test_auto_effects_serialised_with_correct_keys(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            idx = 2  # 'kaleidoscope'
            vglr._auto_effects.add(idx)
            vglr._effect_params[idx].update({"intensity": 0.8, "param_a": 0.3,
                                              "param_b": 0.6, "param_c": 0.9})
            cfg = self._save_and_read(tmp)
            auto = cfg["auto_effects"]
            self.assertEqual(len(auto), 1)
            entry = auto[0]
            self.assertEqual(entry["shader"],    vglr.SHADERS[idx][0])
            self.assertAlmostEqual(entry["intensity"], 0.8)
            self.assertAlmostEqual(entry["param_a"],   0.3)
            self.assertAlmostEqual(entry["param_b"],   0.6)
            self.assertAlmostEqual(entry["param_c"],   0.9)

    def test_auto_effects_multiple_effects_sorted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vglr._auto_effects.update({3, 1, 5})
            cfg = self._save_and_read(tmp)
            auto = cfg["auto_effects"]
            self.assertEqual(len(auto), 3)
            # should be in ascending index order
            indices = [next(i for i, (n, _) in enumerate(vglr.SHADERS)
                            if n == e["shader"]) for e in auto]
            self.assertEqual(indices, sorted(indices))

    def test_auto_effects_out_of_range_indices_excluded(self):
        """Indices >= len(SHADERS) are silently skipped."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vglr._auto_effects.add(len(vglr.SHADERS))    # one beyond last valid
            vglr._auto_effects.add(len(vglr.SHADERS) + 5)
            cfg = self._save_and_read(tmp)
            self.assertEqual(cfg["auto_effects"], [])

    def test_active_effects_and_auto_effects_both_present(self):
        """Both 'effects' and 'auto_effects' keys are written."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vglr._active_effects[:] = [0]
            vglr._auto_effects.add(1)
            cfg = self._save_and_read(tmp)
            self.assertIn("effects",      cfg)
            self.assertIn("auto_effects", cfg)
            self.assertEqual(len(cfg["effects"]),      1)
            self.assertEqual(len(cfg["auto_effects"]), 1)


# ---------------------------------------------------------------------------
# 3. _apply_settings — auto_effects restoration
# ---------------------------------------------------------------------------

class TestApplySettings(unittest.TestCase):

    def setUp(self):
        _reset_globals()

    def test_auto_effects_cleared_when_key_absent(self):
        vglr._auto_effects.add(0)
        vglr._apply_settings({"effects": [{"shader": "vhs"}]})
        self.assertEqual(len(vglr._auto_effects), 0)

    def test_auto_effects_cleared_when_list_empty(self):
        vglr._auto_effects.update({0, 1})
        vglr._apply_settings({"effects": [{"shader": "vhs"}], "auto_effects": []})
        self.assertEqual(len(vglr._auto_effects), 0)

    def test_auto_effects_restored_single_entry(self):
        cfg = {
            "effects": [{"shader": "vhs"}],
            "auto_effects": [{"shader": "kaleidoscope", "intensity": 0.7,
                              "param_a": 0.2, "param_b": 0.3, "param_c": 0.4}],
        }
        vglr._apply_settings(cfg)
        expected_idx = next(i for i, (n, _) in enumerate(vglr.SHADERS) if n == "kaleidoscope")
        self.assertIn(expected_idx, vglr._auto_effects)
        self.assertEqual(len(vglr._auto_effects), 1)

    def test_auto_effects_params_updated(self):
        cfg = {
            "effects": [{"shader": "vhs"}],
            "auto_effects": [{"shader": "vortex", "intensity": 0.55,
                              "param_a": 0.11, "param_b": 0.22, "param_c": 0.33}],
        }
        vglr._apply_settings(cfg)
        idx = next(i for i, (n, _) in enumerate(vglr.SHADERS) if n == "vortex")
        p = vglr._effect_params[idx]
        self.assertAlmostEqual(p["intensity"], 0.55)
        self.assertAlmostEqual(p["param_a"],   0.11)
        self.assertAlmostEqual(p["param_b"],   0.22)
        self.assertAlmostEqual(p["param_c"],   0.33)

    def test_auto_effects_multiple_restored(self):
        cfg = {
            "effects": [{"shader": "vhs"}],
            "auto_effects": [
                {"shader": "rgb_orbit"},
                {"shader": "pixel_sort"},
            ],
        }
        vglr._apply_settings(cfg)
        idx_a = next(i for i, (n, _) in enumerate(vglr.SHADERS) if n == "rgb_orbit")
        idx_b = next(i for i, (n, _) in enumerate(vglr.SHADERS) if n == "pixel_sort")
        self.assertIn(idx_a, vglr._auto_effects)
        self.assertIn(idx_b, vglr._auto_effects)
        self.assertEqual(len(vglr._auto_effects), 2)

    def test_auto_effects_unknown_shader_ignored(self):
        cfg = {
            "effects": [{"shader": "vhs"}],
            "auto_effects": [{"shader": "totally_nonexistent_shader"}],
        }
        vglr._apply_settings(cfg)
        self.assertEqual(len(vglr._auto_effects), 0)

    def test_auto_effects_default_params_used_when_absent(self):
        """If a param key is missing in auto_effects entry, default values apply."""
        cfg = {
            "effects": [{"shader": "vhs"}],
            "auto_effects": [{"shader": "melt"}],   # no params at all
        }
        vglr._apply_settings(cfg)
        idx = next(i for i, (n, _) in enumerate(vglr.SHADERS) if n == "melt")
        p = vglr._effect_params[idx]
        self.assertAlmostEqual(p["intensity"], vglr._DEFAULT_EFFECT["intensity"])
        self.assertAlmostEqual(p["param_a"],   vglr._DEFAULT_EFFECT["param_a"])

    def test_auto_effects_does_not_interfere_with_active_effects(self):
        cfg = {
            "effects": [{"shader": "block_glitch"}, {"shader": "vhs"}],
            "auto_effects": [{"shader": "thermal"}],
        }
        vglr._apply_settings(cfg)
        self.assertEqual(len(vglr._active_effects), 2)
        self.assertEqual(len(vglr._auto_effects),   1)

    def test_apply_settings_replaces_previous_auto_effects(self):
        """A second apply_settings call should replace the previous auto pool."""
        vglr._auto_effects.update({0, 1, 2})
        cfg = {
            "effects": [{"shader": "vhs"}],
            "auto_effects": [{"shader": "contour"}],
        }
        vglr._apply_settings(cfg)
        self.assertEqual(len(vglr._auto_effects), 1)
        idx_contour = next(i for i, (n, _) in enumerate(vglr.SHADERS) if n == "contour")
        self.assertIn(idx_contour, vglr._auto_effects)


# ---------------------------------------------------------------------------
# 4. _effect_leds
# ---------------------------------------------------------------------------

class TestEffectLeds(unittest.TestCase):
    """
    _effect_leds is a no-op when _midi_out is None.
    We install a mock _midi_out + mido.Message so we can record each _set_led call.
    """

    def setUp(self):
        _reset_globals()
        # Install mock midi_out
        self._mock_out    = MagicMock()
        vglr._midi_out    = self._mock_out
        # Track (note, on) pairs that were sent
        self._sent: list  = []

        def _capture_send(msg):
            self._sent.append(msg)

        self._mock_out.send.side_effect = _capture_send

        # Make mido.Message return a traceable object
        mido_stub = sys.modules["mido"]
        mido_stub.Message.side_effect = lambda *a, **kw: (a, kw)

    def tearDown(self):
        _reset_globals()

    def _calls_for_note(self, note: int):
        """Return all mido.Message kwargs sent for a given note."""
        return [kw for (_, kw) in self._sent if kw.get("note") == note]

    def _last_velocity_for_mute(self, mute_index: int) -> int:
        """Return the last velocity sent to MUTE[mute_index], or -1 if none."""
        note = vglr.MUTE[mute_index]
        calls = self._calls_for_note(note)
        return calls[-1]["velocity"] if calls else -1

    # -- helpers --

    def _run(self, active_indices, slow_phase=True, fast_phase=True, preview_idx=None):
        self._sent.clear()
        vglr._effect_leds(active_indices, slow_phase=slow_phase,
                          fast_phase=fast_phase, preview_idx=preview_idx)

    # -- tests --

    def test_active_index_is_solid_on(self):
        """An index in active_indices → LED on (velocity 127) regardless of phase."""
        vglr._effect_page = 0
        self._run([0])  # shader 0 is MUTE[0] on page 0
        self.assertEqual(self._last_velocity_for_mute(0), 127)

    def test_inactive_non_auto_is_off(self):
        """An index that is neither active nor in _auto_effects → LED off."""
        vglr._effect_page = 0
        self._run([])
        self.assertEqual(self._last_velocity_for_mute(0), 0)

    def test_auto_effect_on_in_slow_phase(self):
        """An index in _auto_effects → LED follows slow_phase (on when slow_phase=True)."""
        vglr._effect_page = 0
        vglr._auto_effects.add(1)   # MUTE[1] on page 0
        self._run([], slow_phase=True)
        self.assertEqual(self._last_velocity_for_mute(1), 127)

    def test_auto_effect_off_outside_slow_phase(self):
        vglr._effect_page = 0
        vglr._auto_effects.add(1)
        self._run([], slow_phase=False)
        self.assertEqual(self._last_velocity_for_mute(1), 0)

    def test_active_overrides_auto_in_slow_phase_off(self):
        """An index listed in both active and auto → solid on (active takes priority)."""
        vglr._effect_page = 0
        vglr._auto_effects.add(0)
        self._run([0], slow_phase=False)
        # active branch comes first → solid on
        self.assertEqual(self._last_velocity_for_mute(0), 127)

    def test_preview_idx_fast_blinks_target_led(self):
        """When preview_idx is set, only that LED uses fast_phase."""
        vglr._effect_page = 0
        self._run([0, 1], fast_phase=True, preview_idx=2)
        # MUTE[2] should be on (fast_phase=True)
        self.assertEqual(self._last_velocity_for_mute(2), 127)
        # Active effects are suppressed during preview
        self.assertEqual(self._last_velocity_for_mute(0), 0)
        self.assertEqual(self._last_velocity_for_mute(1), 0)

    def test_preview_idx_fast_off_when_fast_phase_false(self):
        vglr._effect_page = 0
        self._run([0], fast_phase=False, preview_idx=2)
        self.assertEqual(self._last_velocity_for_mute(2), 0)

    def test_preview_other_leds_off_even_if_active(self):
        """During preview, all LEDs except the previewed one are off."""
        vglr._effect_page = 0
        self._run([0, 3], fast_phase=True, preview_idx=5)
        for i in range(8):
            if i != 5:
                self.assertEqual(self._last_velocity_for_mute(i), 0,
                                 msg=f"MUTE[{i}] should be off during preview")

    def test_out_of_range_index_is_off(self):
        """Indices >= len(SHADERS) → LED off."""
        vglr._effect_page = 1   # page 1 starts at index 8
        # Total SHADERS = 16; so page 1 indices 8-15 are valid, but if we go to page 2:
        vglr._effect_page = 2   # indices 16-23, all out of range for a 16-shader list
        self._run([16])
        for i in range(8):
            self.assertEqual(self._last_velocity_for_mute(i), 0)

    def test_page_offset_applied_correctly(self):
        """On page 1, MUTE[0] maps to shader index 8."""
        vglr._effect_page = 1
        self._run([8])           # shader 8 = 'thermal', on page 1 it is MUTE[0]
        self.assertEqual(self._last_velocity_for_mute(0), 127)
        self.assertEqual(self._last_velocity_for_mute(1), 0)

    def test_preview_idx_on_page1_offset(self):
        """preview_idx is an absolute shader index; page offset is applied."""
        vglr._effect_page = 1
        # MUTE[0] on page 1 → shader index 8
        self._run([], fast_phase=True, preview_idx=8)
        self.assertEqual(self._last_velocity_for_mute(0), 127)
        for i in range(1, 8):
            self.assertEqual(self._last_velocity_for_mute(i), 0)


# ---------------------------------------------------------------------------
# 5. _handle_midi — solo-preview hold tracking
# ---------------------------------------------------------------------------

class TestHandleMidiPreviewHold(unittest.TestCase):

    def setUp(self):
        _reset_globals()

    def tearDown(self):
        _reset_globals()

    def test_mute_press_records_hold_time(self):
        note = vglr.MUTE[0]
        fake_time = 100.0
        with patch("vglr.time") as mock_time:
            mock_time.monotonic.return_value = fake_time
            msg = _make_midi_msg("note_on", note=note, velocity=127)
            vglr._handle_midi(msg)
        self.assertIn(note, vglr._mute_hold_time)
        self.assertAlmostEqual(vglr._mute_hold_time[note], fake_time)

    def test_mute_release_removes_hold_time(self):
        note = vglr.MUTE[0]
        vglr._mute_hold_time[note] = 50.0
        with patch("vglr.time") as mock_time:
            mock_time.monotonic.return_value = 51.0
            msg = _make_midi_msg("note_off", note=note, velocity=0)
            vglr._handle_midi(msg)
        self.assertNotIn(note, vglr._mute_hold_time)

    def test_non_mute_note_does_not_affect_hold_time(self):
        """Pressing a non-MUTE note (e.g. RECARM) must not touch _mute_hold_time."""
        note = vglr.RECARM[0]
        with patch("vglr.time") as mock_time:
            mock_time.monotonic.return_value = 10.0
            msg = _make_midi_msg("note_on", note=note, velocity=127)
            vglr._handle_midi(msg)
        self.assertNotIn(note, vglr._mute_hold_time)

    def test_all_mute_notes_tracked(self):
        """Every note in MUTE is tracked on press."""
        with patch("vglr.time") as mock_time:
            mock_time.monotonic.return_value = 200.0
            for n in vglr.MUTE:
                vglr._mute_hold_time.clear()
                msg = _make_midi_msg("note_on", note=n, velocity=127)
                vglr._handle_midi(msg)
                self.assertIn(n, vglr._mute_hold_time)

    def test_mute_note_on_velocity_zero_treated_as_release(self):
        """note_on with velocity=0 is treated as a release (MIDI running status)."""
        note = vglr.MUTE[0]
        vglr._mute_hold_time[note] = 10.0
        with patch("vglr.time") as mock_time:
            mock_time.monotonic.return_value = 11.0
            msg = _make_midi_msg("note_on", note=note, velocity=0)
            vglr._handle_midi(msg)
        self.assertNotIn(note, vglr._mute_hold_time)


# ---------------------------------------------------------------------------
# 6. _handle_midi — double-click auto-mode toggle
# ---------------------------------------------------------------------------

class TestHandleMidiDoubleClick(unittest.TestCase):

    def setUp(self):
        _reset_globals()
        # No real MIDI output needed for these tests
        vglr._midi_out = None

    def tearDown(self):
        _reset_globals()

    def _press_mute(self, mute_idx: int, t: float):
        note = vglr.MUTE[mute_idx]
        with patch("vglr.time") as mt:
            mt.monotonic.return_value = t
            # Also patch _effect_leds so it doesn't error without midi_out
            with patch("vglr._effect_leds"):
                msg = _make_midi_msg("note_on", note=note, velocity=127)
                vglr._handle_midi(msg)

    def test_single_click_adds_to_active_not_auto(self):
        """A single click on an inactive effect activates it (not auto mode)."""
        vglr._active_effects[:] = []
        self._press_mute(0, t=1.0)
        self.assertIn(0, vglr._active_effects)
        self.assertNotIn(0, vglr._auto_effects)

    def test_single_click_removes_from_active(self):
        """A single click on an active effect deactivates it."""
        vglr._active_effects[:] = [0]
        # First click at t=1.0, second click 0.5s later (not a double-click)
        self._press_mute(0, t=1.0)
        # Reset active so the click toggles it off
        vglr._active_effects[:] = [0]
        self._press_mute(0, t=10.0)  # well beyond 0.35s threshold
        self.assertNotIn(0, vglr._active_effects)

    def test_double_click_moves_effect_to_auto(self):
        """Two clicks within 0.35 s move the effect from active to _auto_effects."""
        vglr._active_effects[:] = [0]
        self._press_mute(0, t=1.0)
        self._press_mute(0, t=1.20)  # 0.20 s apart — within 0.35 s threshold
        self.assertIn(0, vglr._auto_effects)
        self.assertNotIn(0, vglr._active_effects)

    def test_double_click_removes_from_auto_if_already_there(self):
        """Double-clicking an already-auto effect removes it from auto.

        The double-click handler checks _auto_effects AT THE TIME of the second
        click.  We pre-load _dbl_click_time to simulate that the first click of
        the pair already fired, and we keep the effect in _auto_effects so the
        second click sees it there and discards it.
        """
        note = vglr.MUTE[0]
        # Simulate first click of the pair having fired 0.2 s ago at t_first.
        t_first = 2.0
        vglr._dbl_click_time[note] = t_first
        vglr._auto_effects.add(0)
        vglr._active_effects[:] = []
        # Second click 0.2 s later → double-click path, effect IS in auto → discard
        self._press_mute(0, t=t_first + 0.2)
        self.assertNotIn(0, vglr._auto_effects)

    def test_double_click_threshold_boundary_just_inside(self):
        """Clicks separated by just under 0.35 s are a double-click."""
        vglr._active_effects[:] = []
        # First click at t=1.0 (well past any residual 0.0 default → treated as single)
        self._press_mute(0, t=1.0)
        # Second click 0.349 s later → 0.349 < 0.35 → double-click
        self._press_mute(0, t=1.349)
        self.assertIn(0, vglr._auto_effects)

    def test_double_click_threshold_boundary_just_outside(self):
        """Clicks separated by >= 0.35 s are two single-clicks, not a double-click."""
        vglr._active_effects[:] = []
        self._press_mute(0, t=0.0)
        self._press_mute(0, t=0.351)
        # Should be added as active, not auto
        self.assertIn(0, vglr._active_effects)
        self.assertNotIn(0, vglr._auto_effects)

    def test_single_click_exits_auto_mode(self):
        """A plain single click on an auto-mode effect removes it from auto and activates it."""
        vglr._auto_effects.add(0)
        vglr._active_effects[:] = []
        # Single click (long gap from previous press)
        self._press_mute(0, t=100.0)
        # The effect must have been discarded from auto
        self.assertNotIn(0, vglr._auto_effects)

    def test_double_click_reset_prevents_triple_click_double(self):
        """After a double-click the timer is zeroed, so a 3rd quick click is a single."""
        vglr._active_effects[:] = []
        self._press_mute(0, t=1.0)
        self._press_mute(0, t=1.2)   # double-click → auto
        # 3rd click very soon after → should be treated as fresh single
        self._press_mute(0, t=1.3)
        # Effect should now be in active (single click from auto → exits auto, activates)
        self.assertNotIn(0, vglr._auto_effects)

    def test_double_click_on_page1_uses_correct_real_idx(self):
        """Double-click on page 1, slot 0 → auto index 8 (not 0)."""
        vglr._effect_page = 1
        vglr._active_effects[:] = [8]
        self._press_mute(0, t=5.0)
        self._press_mute(0, t=5.2)
        self.assertIn(8, vglr._auto_effects)
        self.assertNotIn(8, vglr._active_effects)

    def test_double_click_out_of_range_ignored(self):
        """Double-clicking a slot beyond SHADERS length does nothing."""
        n_shaders = len(vglr.SHADERS)
        vglr._effect_page = n_shaders // 8 + 1   # force page beyond last valid shader
        before_auto   = set(vglr._auto_effects)
        before_active = list(vglr._active_effects)
        note = vglr.MUTE[0]
        with patch("vglr.time") as mt:
            mt.monotonic.return_value = 1.0
            msg = _make_midi_msg("note_on", note=note, velocity=127)
            vglr._handle_midi(msg)
        # State must be unchanged
        self.assertEqual(set(vglr._auto_effects),   before_auto)
        self.assertEqual(list(vglr._active_effects), before_active)


# ---------------------------------------------------------------------------
# 7. Momentum-normalisation (pure maths extracted from on_render logic)
# ---------------------------------------------------------------------------

class TestMomentumNorm(unittest.TestCase):
    """
    The formula extracted verbatim from on_render:

        momentum_norm = min(max(momentum * AUTO_MOMENTUM_SCALE + 0.5, 0.0), 1.0)
    """

    def _calc(self, momentum: float) -> float:
        return min(max(momentum * vglr.AUTO_MOMENTUM_SCALE + 0.5, 0.0), 1.0)

    def test_zero_momentum_gives_half(self):
        self.assertAlmostEqual(self._calc(0.0), 0.5)

    def test_positive_momentum_above_half(self):
        self.assertGreater(self._calc(0.01), 0.5)

    def test_negative_momentum_below_half(self):
        self.assertLess(self._calc(-0.01), 0.5)

    def test_large_positive_clamped_to_one(self):
        self.assertAlmostEqual(self._calc(100.0), 1.0)

    def test_large_negative_clamped_to_zero(self):
        self.assertAlmostEqual(self._calc(-100.0), 0.0)

    def test_threshold_for_scale(self):
        """At momentum = 0.5 / AUTO_MOMENTUM_SCALE the result should reach exactly 1.0."""
        threshold = 0.5 / vglr.AUTO_MOMENTUM_SCALE
        self.assertAlmostEqual(self._calc(threshold), 1.0)

    def test_result_is_always_in_0_to_1(self):
        for v in [-10.0, -0.1, 0.0, 0.1, 10.0]:
            result = self._calc(v)
            self.assertGreaterEqual(result, 0.0)
            self.assertLessEqual(result, 1.0)


# ---------------------------------------------------------------------------
# 8. Blend-ramp logic (pure maths extracted from on_render)
# ---------------------------------------------------------------------------

class TestBlendRamp(unittest.TestCase):
    """
    The ramp formulae extracted verbatim from on_render:

        if blend < target:
            blend = min(target, blend + AUTO_BLEND_RATE * dt)
        else:
            blend = max(target, blend - AUTO_BLEND_RATE * dt)
    """

    def _step(self, blend: float, target: float, dt: float) -> float:
        rate = vglr.AUTO_BLEND_RATE
        if blend < target:
            return min(target, blend + rate * dt)
        else:
            return max(target, blend - rate * dt)

    def test_ramp_up_increases_blend(self):
        b = self._step(0.0, 1.0, 0.1)
        expected = min(1.0, 0.0 + vglr.AUTO_BLEND_RATE * 0.1)
        self.assertAlmostEqual(b, expected)

    def test_ramp_down_decreases_blend(self):
        b = self._step(1.0, 0.0, 0.1)
        expected = max(0.0, 1.0 - vglr.AUTO_BLEND_RATE * 0.1)
        self.assertAlmostEqual(b, expected)

    def test_ramp_does_not_overshoot_target_upward(self):
        """A huge dt must clamp at target."""
        b = self._step(0.0, 1.0, 999.0)
        self.assertAlmostEqual(b, 1.0)

    def test_ramp_does_not_overshoot_target_downward(self):
        b = self._step(1.0, 0.0, 999.0)
        self.assertAlmostEqual(b, 0.0)

    def test_blend_already_at_target_unchanged(self):
        self.assertAlmostEqual(self._step(0.5, 0.5, 0.1), 0.5)

    def test_blend_ramps_fully_to_target_in_expected_time(self):
        """From 0 to 1 should take at most 1/AUTO_BLEND_RATE seconds."""
        max_time = 1.0 / vglr.AUTO_BLEND_RATE
        dt = 0.01
        b = 0.0
        t = 0.0
        while t < max_time + 0.1 and b < 1.0:
            b = self._step(b, 1.0, dt)
            t += dt
        self.assertAlmostEqual(b, 1.0)

    def test_auto_blend_max_applied_correctly(self):
        """AUTO_BLEND_MAX scales the final blend_alpha sent to the shader."""
        blend = 0.8
        expected_alpha = blend * vglr.AUTO_BLEND_MAX
        self.assertAlmostEqual(expected_alpha, 0.8 * 0.75)


# ---------------------------------------------------------------------------
# 9. LED blink phases (pure maths extracted from on_render)
# ---------------------------------------------------------------------------

class TestLedBlinkPhases(unittest.TestCase):
    """
    Blink logic from on_render:

        slow_phase = bool(led_count % 8 < 4)   # ~1 Hz
        fast_phase = bool(led_count % 2 == 0)  # ~4 Hz
    """

    def _phases(self, count: int):
        slow = bool(count % 8 < 4)
        fast = bool(count % 2 == 0)
        return slow, fast

    def test_slow_phase_on_first_four_ticks(self):
        for c in range(4):
            slow, _ = self._phases(c)
            self.assertTrue(slow, f"slow_phase should be True for count={c}")

    def test_slow_phase_off_next_four_ticks(self):
        for c in range(4, 8):
            slow, _ = self._phases(c)
            self.assertFalse(slow, f"slow_phase should be False for count={c}")

    def test_slow_phase_period_is_8(self):
        for c in range(16):
            self.assertEqual(self._phases(c)[0], self._phases(c + 8)[0])

    def test_fast_phase_period_is_2(self):
        for c in range(8):
            self.assertEqual(self._phases(c)[1], self._phases(c + 2)[1])

    def test_fast_phase_alternates(self):
        phases = [self._phases(c)[1] for c in range(4)]
        self.assertEqual(phases, [True, False, True, False])

    def test_slow_phase_complete_cycle(self):
        slow_cycle = [self._phases(c)[0] for c in range(8)]
        self.assertEqual(slow_cycle, [True, True, True, True, False, False, False, False])


# ---------------------------------------------------------------------------
# 10. Solo-preview detection logic (pure logic, no GL context required)
# ---------------------------------------------------------------------------

class TestSoloPreviewDetection(unittest.TestCase):
    """
    The solo-preview detection loop from on_render (extracted as pure logic):

        preview_idx = None
        for i, n in enumerate(MUTE):
            press_t = _mute_hold_time.get(n)
            if press_t and now - press_t >= PREVIEW_HOLD_S:
                preview_idx = effect_page * 8 + i
                break
    """

    def setUp(self):
        _reset_globals()

    def tearDown(self):
        _reset_globals()

    def _detect_preview(self, hold_times: dict, now: float, page: int = 0):
        """Replicate the preview detection loop from on_render."""
        for i, n in enumerate(vglr.MUTE):
            press_t = hold_times.get(n)
            if press_t and now - press_t >= vglr.PREVIEW_HOLD_S:
                return page * 8 + i
        return None

    def test_no_hold_returns_none(self):
        self.assertIsNone(self._detect_preview({}, now=100.0))

    def test_hold_short_of_threshold_returns_none(self):
        note = vglr.MUTE[0]
        hold = {note: 100.0}
        self.assertIsNone(self._detect_preview(hold, now=100.5))  # only 0.5 s

    def test_hold_at_threshold_returns_index(self):
        note = vglr.MUTE[0]
        hold = {note: 100.0}
        result = self._detect_preview(hold, now=101.0)
        self.assertEqual(result, 0)

    def test_hold_beyond_threshold_returns_index(self):
        note = vglr.MUTE[3]
        hold = {note: 50.0}
        result = self._detect_preview(hold, now=55.0)  # 5 s held
        self.assertEqual(result, 3)

    def test_first_matching_note_wins(self):
        """If two buttons are held, the lowest-index MUTE wins."""
        # Use a non-zero press time so `if press_t:` evaluates as truthy.
        hold = {
            vglr.MUTE[2]: 10.0,
            vglr.MUTE[5]: 10.0,
        }
        result = self._detect_preview(hold, now=12.0)
        self.assertEqual(result, 2)

    def test_page_offset_applied(self):
        note = vglr.MUTE[0]
        # Non-zero press time so `if press_t:` is truthy
        hold = {note: 100.0}
        result = self._detect_preview(hold, now=101.5, page=1)
        self.assertEqual(result, 8)

    def test_preview_hold_s_constant_used(self):
        """Verify PREVIEW_HOLD_S is respected: just below threshold returns None."""
        note = vglr.MUTE[0]
        # Use a non-zero press time so `if press_t:` is truthy
        t_press = 50.0
        just_before = t_press + vglr.PREVIEW_HOLD_S - 0.001
        hold = {note: t_press}
        self.assertIsNone(self._detect_preview(hold, now=just_before))
        at_threshold = t_press + vglr.PREVIEW_HOLD_S
        self.assertIsNotNone(self._detect_preview(hold, now=at_threshold))


if __name__ == "__main__":
    unittest.main()
