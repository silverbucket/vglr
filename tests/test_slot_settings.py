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
        vglr._cc_burst_seen.clear()
        vglr._cc_burst_time = 0.0
        vglr._m_master = 1.0
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


if __name__ == "__main__":
    unittest.main()
