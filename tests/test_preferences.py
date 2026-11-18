import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from canopy.preferences import Preferences, Profile, Layout, Override, load, save, effective_features, update_classic_pins, user_settings_path

class PreferencesTests(unittest.TestCase):
    def test_defaults(self):
        p = Preferences()
        self.assertEqual(p.layout, Layout.CLASSIC)
        self.assertEqual(p.profile, Profile.BALANCED)
        self.assertTrue(effective_features(p)["animations"])

    def test_profiles(self):
        for profile, count in zip(Profile, [0, 0, 1, 2, 3]):
            with self.subTest(profile=profile):
                self.assertEqual(sum(effective_features(Preferences(profile=profile, auto_mode=False)).values()), count)

    def test_user_override(self):
        p = Preferences(profile=Profile.ULTRA_LITE)
        p.overrides["transparency"] = Override.ON
        self.assertTrue(effective_features(p, memory_pressure=True)["transparency"])
        p.overrides["transparency"] = Override.OFF
        self.assertFalse(effective_features(p)["transparency"])

    def test_accessibility_wins(self):
        p = Preferences()
        p.overrides["animations"] = Override.ON
        p.overrides["dock_magnification"] = Override.ON
        self.assertFalse(effective_features(p, reduced_motion=True)["animations"])
        self.assertFalse(effective_features(p, reduced_motion=True)["dock_magnification"])

    def test_auto_resource_pressure(self):
        p = Preferences(profile=Profile.ULTIMATE)
        self.assertEqual(sum(effective_features(p, memory_pressure=True).values()), 0)
        self.assertEqual(sum(effective_features(p, battery_saver=True).values()), 0)
        p.auto_mode = False
        self.assertEqual(sum(effective_features(p, memory_pressure=True).values()), 3)

    def test_roundtrip_and_modern(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(load(path).layout, Layout.CLASSIC)
            p = Preferences(layout=Layout.MODERN, profile=Profile.EFFICIENT)
            save(path, p)
            self.assertEqual(load(path).to_dict(), p.to_dict())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_version_one_loads_with_default_pins_and_saves_as_two(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text(json.dumps({'version': 1, 'profile': 'efficient'}))
            preferences = load(path)
            self.assertEqual(preferences.profile, Profile.EFFICIENT)
            self.assertIsNone(preferences.classic_pins)
            save(path, preferences)
            self.assertEqual(json.loads(path.read_text())['version'], 2)
            self.assertIsNone(load(path).classic_pins)

    def test_classic_pins_roundtrip_and_validation(self):
        preferences = Preferences(classic_pins=['nemo.desktop', 'firefox.desktop'])
        self.assertEqual(Preferences.from_dict(preferences.to_dict()), preferences)
        self.assertEqual(Preferences.from_dict({'version': 2, 'classic_pins': []}).classic_pins, [])
        for pins in (['same.desktop', 'same.desktop'], [''], ['unknown'], [4],
                     'nemo.desktop', ['a.desktop'] * 65, ['\x00.desktop'], ['\x7f.desktop']):
            with self.subTest(pins=pins), self.assertRaises(ValueError):
                Preferences.from_dict({'version': 2, 'classic_pins': pins})

    def test_pin_update_keeps_other_changes_and_rejects_stale_editor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            save(path, Preferences(profile=Profile.ENHANCED))
            updated = update_classic_pins(path, None, ['nemo.desktop'])
            self.assertEqual(updated.profile, Profile.ENHANCED)
            self.assertEqual(load(path).classic_pins, ['nemo.desktop'])

            with self.assertRaisesRegex(ValueError, 'changed elsewhere'):
                update_classic_pins(path, None, ['firefox.desktop'])
            self.assertEqual(load(path).classic_pins, ['nemo.desktop'])

    def test_pin_update_preserves_corrupt_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_bytes(b'{broken')
            with self.assertRaises(json.JSONDecodeError):
                update_classic_pins(path, None, ['nemo.desktop'])
            self.assertEqual(path.read_bytes(), b'{broken')

    def test_invalid_save_does_not_create_settings_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'canopy/settings.json'
            with self.assertRaises(ValueError):
                save(path, Preferences(classic_pins=['invalid']))
            self.assertFalse(path.parent.exists())

    def test_save_syncs_file_and_containing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'canopy/settings.json'
            synced_modes = []
            original_fsync = os.fsync

            def record_fsync(descriptor):
                synced_modes.append(os.fstat(descriptor).st_mode)
                original_fsync(descriptor)

            with patch('canopy.preferences.os.fsync', side_effect=record_fsync):
                save(path, Preferences())

            self.assertEqual(len(synced_modes), 2)
            self.assertTrue(stat.S_ISREG(synced_modes[0]))
            self.assertTrue(stat.S_ISDIR(synced_modes[1]))

    def test_reject_unknown_or_invalid(self):
        for data in ({"version": 3}, {"version": True}, {"version": 1.0}, {"auto_mode": "false"},
                     {"overrides": {"networking": "off"}},
                     {"overrides": {"animations": "maybe"}},
                     {"layout": "unknown"}, {"unexpected": True},
                     {"version": 1, "classic_pins": []}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Preferences.from_dict(data)

    def test_xdg_config_home_must_be_absolute(self):
        fallback = Path.home() / ".config/canopy/settings.json"
        for value in ("", "relative"):
            with self.subTest(value=value), patch.dict("os.environ", {"XDG_CONFIG_HOME": value}):
                self.assertEqual(user_settings_path(), fallback)
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": "/example/config"}):
            self.assertEqual(user_settings_path(), Path("/example/config/canopy/settings.json"))

    def test_corrupt_file_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load(path)
            self.assertEqual(path.read_text(), "{broken")

if __name__ == "__main__":
    unittest.main()
