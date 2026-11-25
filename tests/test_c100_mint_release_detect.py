"""Offline unit tests for read-only Linux Mint release detection."""
import json
import tempfile
import unittest
from pathlib import Path

from canopy_features.mint.release_detect import (
    DEFAULT_RELEASE_PATH,
    clean_version,
    detect,
)

VALID_MINT = 'ID=linuxmint\nVERSION_ID="22.3"\nPRETTY_NAME="Linux Mint 22.3"\n'


class ReleaseDetectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="canopy-release-detect-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_default_path_is_system_os_release(self):
        self.assertEqual(DEFAULT_RELEASE_PATH, "/etc/os-release")

    def test_default_path_probe_is_safe_on_any_host(self):
        # On this Windows host /etc/os-release is absent; no path may raise.
        report = detect()
        self.assertTrue(report["probe_only"])
        self.assertEqual(report["release_acceptance"], "NOT_RUN")
        self.assertIn(report["compatibility"],
                      ("unknown", "not_mint", "supported", "unsupported"))

    def test_real_mint_release_matches_supported_major(self):
        path = self.write("os-release", VALID_MINT)
        report = detect(path, supported=("22",))
        self.assertEqual(report["read_status"], "ok")
        self.assertTrue(report["mint_identified"])
        self.assertEqual(report["version_id"], "22.3")
        self.assertEqual(report["compatibility"], "supported")
        self.assertTrue(report["probe_only"])
        self.assertEqual(report["release_acceptance"], "NOT_RUN")

    def test_exact_version_and_unsupported_release(self):
        path = self.write("os-release", VALID_MINT)
        self.assertEqual(detect(path, supported=("22.3",))["compatibility"],
                         "supported")
        report = detect(path, supported=("20", "21"))
        self.assertEqual(report["compatibility"], "unsupported")
        self.assertTrue(report["mint_identified"])

    def test_empty_support_matrix_never_claims_acceptance(self):
        path = self.write("os-release", VALID_MINT)
        report = detect(path)
        self.assertEqual(report["compatibility"], "unsupported")
        self.assertEqual(report["release_acceptance"], "NOT_RUN")

    def test_missing_release_file(self):
        report = detect(self.dir / "absent", supported=("22",))
        self.assertEqual(report["read_status"], "missing-or-unreadable")
        self.assertFalse(report["mint_identified"])
        self.assertEqual(report["version_id"], "")
        self.assertEqual(report["compatibility"], "unknown")

    def test_empty_release_file(self):
        path = self.write("os-release", "")
        report = detect(path)
        self.assertEqual(report["read_status"], "empty")
        self.assertEqual(report["compatibility"], "unknown")

    def test_non_mint_distro_not_passed_as_mint(self):
        path = self.write("os-release", 'ID=ubuntu\nVERSION_ID="24.04"\n')
        report = detect(path, supported=("22",))
        self.assertFalse(report["mint_identified"])
        self.assertEqual(report["version_id"], "")
        self.assertEqual(report["compatibility"], "not_mint")

    def test_forged_version_is_rejected_not_matched(self):
        path = self.write(
            "os-release",
            'ID=linuxmint\nVERSION_ID="22.3; rm -rf /"\nTOKEN=forged\n',
        )
        report = detect(path, supported=("22.3",))
        self.assertTrue(report["mint_identified"])
        self.assertEqual(report["version_id"], "")
        self.assertEqual(report["compatibility"], "unknown")

    def test_forged_extra_fields_are_ignored(self):
        path = self.write(
            "os-release",
            'ID=linuxmint\nVERSION_ID=22.3\nHOME=/root\nCANOPY_SECRET=leak\n',
        )
        report = detect(path, supported=("22",))
        serialized = json.dumps(report)
        self.assertNotIn("CANOPY_SECRET", serialized)
        self.assertNotIn("/root", serialized)
        self.assertNotIn("leak", serialized)

    def test_malformed_identity_not_treated_as_mint(self):
        # Unterminated quote makes parse_release drop the ID line.
        path = self.write("os-release", 'ID="linuxmint\nVERSION_ID=22.3\n')
        report = detect(path, supported=("22",))
        self.assertFalse(report["mint_identified"])
        self.assertEqual(report["compatibility"], "not_mint")

    def test_control_character_version_is_ignored(self):
        path = self.write("os-release", "ID=linuxmint\nVERSION_ID=22." + chr(0) + "3\n")
        report = detect(path, supported=("22",))
        self.assertTrue(report["mint_identified"])
        self.assertEqual(report["version_id"], "")
        self.assertEqual(report["compatibility"], "unknown")

    def test_oversized_release_file_is_bounded(self):
        path = self.write(
            "os-release",
            'ID=linuxmint\nVERSION_ID=22.3\n#' + "x" * 10000,
        )
        report = detect(path, supported=("22",))
        self.assertEqual(report["read_status"], "oversized")
        self.assertEqual(report["compatibility"], "unknown")

    def test_clean_version_accepts_dotted_numeric(self):
        for good in ("22", "22.3", "21.3.1"):
            with self.subTest(version=good):
                self.assertEqual(clean_version(good), good)

    def test_clean_version_rejects_forged_values(self):
        for bad in ("", "abc", "22.x", "22.3.4.5", "-1",
                    "9" * 20, 22, None):
            with self.subTest(version=bad):
                self.assertEqual(clean_version(bad), "")


if __name__ == "__main__":
    unittest.main()
