"""Slot save/load and SEND ALL burst detection.

Run from the repo root:
    python3 tests/test_slot_settings.py
"""
import json
import os
import sys
import tempfile
import types
import unittest

# vglr imports GL/audio stacks at module level. Stub them so the persistence
# logic can be tested without a display or sound device.
for _name in ("moderngl", "moderngl_window", "av", "sounddevice"):
    _mod = types.ModuleType(_name)
    sys.modules.setdefault(_name, _mod)
sys.modules["moderngl_window"].WindowConfig = type("WindowConfig", (), {})

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vglr


class _Msg:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _cc(control, value):
    vglr._handle_midi(_Msg(type="control_change", control=control, value=value))


def _note(note, pressed, velocity=127):
    vglr._handle_midi(_Msg(
        type="note_on" if pressed else "note_off",
        note=note,
        velocity=velocity if pressed else 0,
    ))


class SlotSettingsTests(unittest.TestCase):
    def setUp(self):
        self._old = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        vglr._effect_page = 0
        vglr._current_bank = 1
        vglr._current_slot = 1
        vglr._active_effects = [0]
        vglr._slot_beat_thresh = 1.8
        vglr._cc_seen_at.clear()
        vglr._m_master = 1.0
        vglr._reset_held.clear()
        vglr._reset_combo_active = False
        vglr._reset_solo_note = None
        for params in vglr._effect_params.values():
            params.update(vglr._DEFAULT_EFFECT)

    def tearDown(self):
        os.chdir(self._old)
        self._tmp.cleanup()

    def _settings(self, bank=1, slot=1):
        path = os.path.join(self._tmp.name, "videos", f"bank{bank}", f"video{slot}", "settings.json")
        with open(path) as f:
            return json.load(f)

    def test_send_all_set_has_every_factory_control(self):
        self.assertEqual(len(vglr._SEND_ALL_CCS), 33)
        self.assertEqual(len(vglr.KNOB_CC) * 3 + len(vglr.FADER_CC) + 1, 33)

    def test_send_all_persists_the_cc_that_completes_the_burst(self):
        # Strip 8 fader is delivered last — the old counter saved on message 32,
        # before this value was applied, so a recalled slot jumped back.
        vglr._active_effects = [7]
        vglr._effect_params[7]["intensity"] = 0.0
        last = vglr.FADER_CC[7]
        for cc in sorted(vglr._SEND_ALL_CCS - {last}):
            _cc(cc, 1)
        path = os.path.join(self._tmp.name, "videos", "bank1", "video1", "settings.json")
        self.assertFalse(os.path.exists(path))

        _cc(last, 127)
        cfg = self._settings()
        self.assertEqual(cfg["effects"][0]["shader"], "melt")
        self.assertEqual(cfg["effects"][0]["intensity"], 1.0)
        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_send_all_right_after_another_cc_still_saves(self):
        # A knob touch or pot jitter just before SEND ALL used to open a fixed
        # window that expired mid-burst, so the save was silently skipped.
        clock = [100.0]
        real = vglr.time.monotonic
        vglr.time.monotonic = lambda: clock[0]
        try:
            _cc(vglr.FADER_CC[0], 5)
            clock[0] += 0.14
            for cc in sorted(vglr._SEND_ALL_CCS):
                _cc(cc, 64)
                clock[0] += 0.001
        finally:
            vglr.time.monotonic = real
        self.assertEqual(self._settings()["effects"][0]["shader"], "vhs")

    def test_fader_stream_does_not_save(self):
        vglr._active_effects = [0]
        for value in range(64):
            _cc(vglr.FADER_CC[0], value)
        path = os.path.join(self._tmp.name, "videos", "bank1", "video1", "settings.json")
        self.assertFalse(os.path.exists(path))
        self.assertAlmostEqual(vglr._effect_params[0]["intensity"], 63 / 127.0)

    def test_empty_effect_list_roundtrips(self):
        vglr._active_effects = []
        vglr._save_settings(1, 1)
        vglr._active_effects = [0]
        vglr._apply_settings(vglr._load_settings(1, 1))
        self.assertEqual(vglr._active_effects, [])

    def test_two_effects_roundtrip(self):
        vglr._active_effects = [0, 4]
        vglr._effect_params[0].update(
            {"intensity": 0.2, "param_a": 0.3, "param_b": 0.4, "param_c": 0.5}
        )
        vglr._effect_params[4].update(
            {"intensity": 0.6, "param_a": 0.7, "param_b": 0.8, "param_c": 0.9}
        )
        vglr._save_settings(1, 2)
        vglr._active_effects = [1]
        vglr._apply_settings(vglr._load_settings(1, 2))
        self.assertEqual(vglr._active_effects, [0, 4])
        self.assertEqual(vglr._effect_params[0]["intensity"], 0.2)
        self.assertEqual(vglr._effect_params[4]["param_c"], 0.9)

    def test_probe_video_reads_geometry(self):
        class _Stream:
            width = 1280
            height = 720
            average_rate = 24
            guessed_rate = None

        class _Container:
            def __init__(self):
                self.streams = types.SimpleNamespace(video=[_Stream()])

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        vglr.av.open = lambda path: _Container()
        self.assertEqual(vglr._probe_video("clip.mp4"), (1280, 720, 24.0))

    def test_probe_video_rejects_unreadable_file(self):
        def _open(path):
            raise OSError("truncated")

        vglr.av.open = _open
        with self.assertRaises(OSError):
            vglr._probe_video("clip.mp4")

    def test_legacy_settings_without_effects_key(self):
        slot = os.path.join(self._tmp.name, "videos", "bank1", "video3")
        os.makedirs(slot)
        with open(os.path.join(slot, "settings.json"), "w") as f:
            json.dump({
                "shader": "melt",
                "intensity": 0.25,
                "param_a": 0.1,
                "param_b": 0.2,
                "param_c": 0.3,
            }, f)
        vglr._apply_settings(vglr._load_settings(1, 3))
        self.assertEqual(vglr._active_effects, [7])
        self.assertEqual(vglr._effect_params[7]["intensity"], 0.25)
        self.assertEqual(vglr._effect_params[7]["param_a"], 0.1)


class ResetComboTests(unittest.TestCase):
    def setUp(self):
        self._old_clock = vglr._monotonic
        vglr._current_bank = 3
        vglr._current_slot = 2
        vglr._effect_page = 0
        vglr._active_effects = [1, 4]
        vglr._reset_held.clear()
        vglr._reset_combo_active = False
        vglr._reset_solo_note = None

    def tearDown(self):
        vglr._monotonic = self._old_clock

    def test_solo_bank_and_mute_still_work_on_release(self):
        _note(vglr.BANK_R, True)
        self.assertEqual(vglr._current_bank, 3)
        _note(vglr.BANK_R, False)
        self.assertEqual(vglr._current_bank, 4)

        vglr._active_effects = []
        _note(vglr.MUTE[1], True)
        self.assertEqual(vglr._active_effects, [1])
        _note(vglr.MUTE[0], True)
        self.assertEqual(vglr._active_effects, [1])
        _note(vglr.MUTE[0], False)
        self.assertEqual(vglr._active_effects, [0, 1])

    def test_combo_does_not_change_bank_or_effects(self):
        # Holding the restart chord used to switch banks and toggle MUTE-1
        # immediately, so an aborted restart left the projector on the wrong clip.
        for note in (vglr.MUTE[0], vglr.BANK_L, vglr.BANK_R):
            _note(note, True)
            self.assertEqual(vglr._current_bank, 3)
            self.assertEqual(vglr._active_effects, [1, 4])
        for note in (vglr.BANK_R, vglr.BANK_L, vglr.MUTE[0]):
            _note(note, False)
        self.assertEqual(vglr._current_bank, 3)
        self.assertEqual(vglr._current_slot, 2)
        self.assertEqual(vglr._active_effects, [1, 4])
        self.assertFalse(vglr._reset_combo_active)
        self.assertIsNone(vglr._reset_solo_note)
        self.assertEqual(vglr._reset_held, {})

    def test_long_solo_bank_press_still_changes_bank(self):
        # The 10s stale-hold eviction forgets a stuck note so it cannot arm the
        # chord. A finger that is actually still down must bank on release.
        vglr._monotonic = lambda: 0.0
        _note(vglr.BANK_R, True)
        vglr._monotonic = lambda: 11.0
        self.assertFalse(vglr._poll_reset_combo())
        self.assertNotIn(vglr.BANK_R, vglr._reset_held)
        self.assertEqual(vglr._current_bank, 3)
        _note(vglr.BANK_R, False)
        self.assertEqual(vglr._current_bank, 4)

    def test_bank1_chord_does_not_advance_to_bank2(self):
        vglr._current_bank = 1
        _note(vglr.BANK_L, True)
        _note(vglr.BANK_R, True)
        _note(vglr.MUTE[0], True)
        _note(vglr.MUTE[0], False)
        _note(vglr.BANK_R, False)
        _note(vglr.BANK_L, False)
        self.assertEqual(vglr._current_bank, 1)

    def test_poll_fires_only_after_full_hold(self):
        start = 5000.0
        vglr._reset_held = {note: start for note in vglr._RESET_NOTES}
        vglr._monotonic = lambda: start + 1.9
        self.assertFalse(vglr._poll_reset_combo())
        vglr._monotonic = lambda: start + 2.0
        self.assertTrue(vglr._poll_reset_combo())

    def test_note_off_during_poll_is_not_written_back(self):
        # Snapshot-then-monotonic-then-update restored released notes, because
        # monotonic() drops the GIL and the MIDI thread can pop them in between.
        start = 8000.0
        vglr._reset_held = {note: start for note in vglr._RESET_NOTES}

        def release_during_clock():
            vglr._reset_held.clear()
            return start + 1.5

        vglr._monotonic = release_during_clock
        self.assertFalse(vglr._poll_reset_combo())
        self.assertEqual(vglr._reset_held, {})

        vglr._monotonic = lambda: start + 3.0
        self.assertFalse(vglr._poll_reset_combo())
        self.assertEqual(vglr._reset_held, {})

    def test_stale_press_is_forgotten(self):
        vglr._reset_held[vglr.BANK_L] = 0.0
        vglr._reset_held[vglr.BANK_R] = 10.5
        vglr._monotonic = lambda: 11.0
        self.assertFalse(vglr._poll_reset_combo())
        self.assertNotIn(vglr.BANK_L, vglr._reset_held)
        self.assertIn(vglr.BANK_R, vglr._reset_held)


if __name__ == "__main__":
    unittest.main()
