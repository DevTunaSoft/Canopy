"""Hostile-but-plausible Shell Pack display-text fields (nonvisual contract).

The v1 checker rejects C0 controls in display names, but a display name is
also consumed by host UI/settings surfaces where non-printable Unicode
control and format characters (C1 controls, bidi overrides, zero-width
characters, lone surrogates) can spoof a trusted identity or hide content.
The metadata contract requires a clean string, so those fields must fail
closed with PackValidationError rather than returning a false VALID verdict.
"""

import json
from pathlib import Path
import tempfile
import unittest

from tools.check_shell_pack import PackValidationError, validate_pack

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "examples" / "shell-pack-starter"


class HostileShellPackTextFieldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "pack"
        (self.root / "ui").mkdir(parents=True)
        (self.root / "ui" / "Main.qml").write_text(
            "import QtQuick\nItem {}\n", encoding="utf-8"
        )
        self.manifest = json.loads(
            (STARTER / "manifest.json").read_text(encoding="utf-8")
        )

    def validate_with(self, field, value):
        self.manifest[field] = value
        (self.root / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        return validate_pack(self.root)

    def assert_clean_string_rejected(self, field, value):
        with self.assertRaisesRegex(PackValidationError, "clean string"):
            self.validate_with(field, value)

    def test_c1_control_in_name_rejected(self):
        self.assert_clean_string_rejected("name", "Official\x85Shell")

    def test_bidi_override_in_name_rejected(self):
        self.assert_clean_string_rejected("name", "Official\u202eShell")

    def test_zero_width_space_in_name_rejected(self):
        self.assert_clean_string_rejected("name", "Official\u200bShell")

    def test_soft_hyphen_in_description_rejected(self):
        self.assert_clean_string_rejected("description", "A\u00adB")

    def test_nonbreaking_space_in_name_rejected(self):
        self.assert_clean_string_rejected("name", "Official\u00a0Shell")

    def test_lone_surrogate_in_name_rejected(self):
        self.assert_clean_string_rejected("name", "Official\ud800Shell")

    def test_printable_unicode_name_still_accepted(self):
        name = "Café \u2014 Présentation"
        self.assertEqual(self.validate_with("name", name)["name"], name)


if __name__ == "__main__":
    unittest.main()
