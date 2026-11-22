"""Offline tests for opt-in-only, duplicate-safe autostart registration."""
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer import autostart_consent as ac


class AutostartConsentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Path with spaces exercises the Windows-host case; no real home write.
        self.root = Path(self.temp.name) / "xdg config with spaces"
        self.entry = ac.AutostartEntry(
            "org.canopy.Classic", "/opt/canopy/canopy-classic --preview")

    def test_denied_and_unset_consent_write_nothing(self):
        for consent in (ac.DENIED, ac.UNSET):
            with self.subTest(consent=consent):
                self.assertEqual(ac.decide(consent, self.entry),
                                 ac.SKIP_NO_CONSENT)
                self.assertEqual(ac.register(self.root, self.entry, consent),
                                 ac.SKIP_NO_CONSENT)
        self.assertEqual(ac.status(self.root, self.entry.app_id),
                         ac.NOT_REGISTERED)
        self.assertFalse((self.root / "autostart").exists())

    def test_denied_consent_cannot_hide_existing_duplicates(self):
        folder = self.root / "autostart"
        folder.mkdir(parents=True)
        self._write_desktop(folder, "a.desktop", self.entry.app_id,
                            self.entry.command)
        self._write_desktop(folder, "b.desktop", self.entry.app_id,
                            self.entry.command)
        self.assertEqual(ac.register(self.root, self.entry, ac.DENIED),
                         ac.SKIP_NO_CONSENT)
        self.assertEqual(ac.status(self.root, self.entry.app_id), ac.DUPLICATE)

    def test_granted_consent_creates_freedesktop_entry(self):
        self.assertEqual(ac.register(self.root, self.entry, ac.GRANTED),
                         ac.WRITE)
        f = self.root / "autostart" / (self.entry.app_id + ".desktop")
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("[Desktop Entry]", text)
        self.assertIn("Exec=" + self.entry.command, text)
        self.assertIn("Hidden=false", text)
        self.assertIn("X-GNOME-Autostart-enabled=true", text)
        self.assertIn("X-Canopy-App-Id=" + self.entry.app_id, text)
        self.assertEqual(ac.status(self.root, self.entry.app_id),
                         ac.REGISTERED)

    def test_granted_twice_is_noop_not_duplicate(self):
        ac.register(self.root, self.entry, ac.GRANTED)
        self.assertEqual(ac.register(self.root, self.entry, ac.GRANTED),
                         ac.NOOP)
        files = list((self.root / "autostart").glob("*.desktop"))
        self.assertEqual(len(files), 1)
        self.assertEqual(ac.status(self.root, self.entry.app_id),
                         ac.REGISTERED)

    def test_duplicate_entries_rejected_by_decide_status_and_register(self):
        folder = self.root / "autostart"
        folder.mkdir(parents=True)
        self._write_desktop(folder, "one.desktop", self.entry.app_id,
                            self.entry.command)
        self._write_desktop(folder, "two.desktop", self.entry.app_id,
                            self.entry.command)
        existing = [ac.AutostartEntry(self.entry.app_id, self.entry.command)] * 2
        with self.assertRaises(ac.DuplicateEntryError):
            ac.decide(ac.GRANTED, self.entry, existing)
        self.assertEqual(ac.status(self.root, self.entry.app_id), ac.DUPLICATE)
        with self.assertRaises(ac.DuplicateEntryError):
            ac.register(self.root, self.entry, ac.GRANTED)
        self.assertEqual(len(list(folder.glob("*.desktop"))), 2)

    def test_conflicting_command_duplicate_rejected(self):
        other = ac.AutostartEntry(self.entry.app_id, "/other/binary")
        with self.assertRaises(ac.DuplicateEntryError):
            ac.decide(ac.GRANTED, self.entry, [other])

    def test_foreign_entry_same_command_is_duplicate(self):
        foreign = ac.AutostartEntry("com.other.App", self.entry.command)
        with self.assertRaises(ac.DuplicateEntryError):
            ac.decide(ac.GRANTED, self.entry, [foreign])

    def test_unregister_is_reversible_and_removes_only_owned_file(self):
        ac.register(self.root, self.entry, ac.GRANTED)
        self.assertEqual(ac.unregister(self.root, self.entry.app_id),
                         ac.UNREGISTERED)
        self.assertEqual(ac.status(self.root, self.entry.app_id),
                         ac.NOT_REGISTERED)
        self.assertFalse(
            (self.root / "autostart" / (self.entry.app_id + ".desktop")).exists())
        with self.assertRaises(ac.ConsentError):
            ac.unregister(self.root, self.entry.app_id)

    def test_modified_entry_prevents_unregister(self):
        ac.register(self.root, self.entry, ac.GRANTED)
        f = self.root / "autostart" / (self.entry.app_id + ".desktop")
        f.write_text(f.read_text(encoding="utf-8") + "# user edit\n",
                     encoding="utf-8")
        self.assertEqual(ac.status(self.root, self.entry.app_id),
                         ac.MODIFIED_OR_UNOWNED)
        with self.assertRaisesRegex(ac.ConsentError, "removed nothing"):
            ac.unregister(self.root, self.entry.app_id)
        self.assertTrue(f.is_file())

    def test_duplicate_prevents_unregister(self):
        folder = self.root / "autostart"
        folder.mkdir(parents=True)
        self._write_desktop(folder, "one.desktop", self.entry.app_id,
                            self.entry.command)
        self._write_desktop(folder, "two.desktop", self.entry.app_id,
                            self.entry.command)
        with self.assertRaises(ac.DuplicateEntryError):
            ac.unregister(self.root, self.entry.app_id)

    def test_symlinked_autostart_directory_is_unsafe(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.root.mkdir(parents=True)
        (self.root / "autostart").symlink_to(outside, target_is_directory=True)
        self.assertEqual(ac.status(self.root, self.entry.app_id), ac.UNSAFE)
        with self.assertRaises(ac.ConsentError):
            ac.register(self.root, self.entry, ac.GRANTED)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unknown_consent_and_bad_input_rejected(self):
        with self.assertRaises(ac.ConsentError):
            ac.decide("implicit", self.entry)
        with self.assertRaises(ac.ConsentError):
            ac.AutostartEntry("../escape", "cmd")
        with self.assertRaises(ac.ConsentError):
            ac.AutostartEntry("org.canopy.Classic", "cmd\nHidden=true")

    def test_model_never_writes_outside_supplied_root(self):
        sentinel = Path(self.temp.name) / "should-not-exist"
        ac.register(self.root, self.entry, ac.GRANTED)
        ac.register(self.root, self.entry, ac.DENIED)
        self.assertFalse(sentinel.exists())
        self.assertTrue(
            (self.root / "autostart" / (self.entry.app_id + ".desktop")).is_file())

    @staticmethod
    def _write_desktop(folder, name, app_id, command):
        (folder / name).write_text(
            "[Desktop Entry]\nExec=" + command + "\nHidden=false\n"
            "X-Canopy-App-Id=" + app_id + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
