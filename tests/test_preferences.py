import json
from pathlib import Path
import tempfile
import unittest
from canopy.preferences import Preferences, Profile, Layout, Override, load, save, effective_features

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

    def test_reject_unknown_or_invalid(self):
        for data in ({"version": 2}, {"auto_mode": "false"},
                     {"overrides": {"networking": "off"}},
                     {"overrides": {"animations": "maybe"}},
                     {"layout": "unknown"}, {"unexpected": True}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Preferences.from_dict(data)

    def test_corrupt_file_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load(path)
            self.assertEqual(path.read_text(), "{broken")

if __name__ == "__main__":
    unittest.main()
