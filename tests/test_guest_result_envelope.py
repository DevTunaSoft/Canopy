import json
from pathlib import Path
import tempfile
import unittest

from scripts.guest_result_envelope import wrap


SHA = "ab" * 20
RUN = "cd" * 16
BOOT = "11111111-2222-3333-4444-555555555555"


class GuestEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report = Path(self.tmp.name) / "report.json"
        self.report.write_text(json.dumps({"schema_version": 1, "status": "PASS"}))

    def test_marks_guest_data_untrusted(self):
        data = wrap(commit=SHA, run_id=RUN, boot_id=BOOT, report=self.report)
        self.assertFalse(data["host_verified"])
        self.assertEqual(data["kind"], "UNTRUSTED_GUEST_EVIDENCE")
        self.assertEqual(len(data["report_sha256"]), 64)

    def test_stale_or_mutated_identity_is_rejected(self):
        for key, replacement in (("commit", "main"), ("run_id", "old"), ("boot_id", "x")):
            kwargs = dict(commit=SHA, run_id=RUN, boot_id=BOOT, report=self.report)
            kwargs[key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                wrap(**kwargs)

    def test_claimed_status_mismatch_fails(self):
        with self.assertRaises(ValueError):
            wrap(commit=SHA, run_id=RUN, boot_id=BOOT, report=self.report, status="FAIL")

    def test_invalid_schema_rejected(self):
        self.report.write_text(json.dumps({"schema_version": True, "status": "PASS"}))
        with self.assertRaises(ValueError):
            wrap(commit=SHA, run_id=RUN, boot_id=BOOT, report=self.report)

    def test_symlink_is_rejected(self):
        link = Path(self.tmp.name) / "link.json"
        try:
            link.symlink_to(self.report)
        except (NotImplementedError, OSError):
            self.skipTest("Symlink unavailable")
        with self.assertRaises(ValueError):
            wrap(commit=SHA, run_id=RUN, boot_id=BOOT, report=link)


if __name__ == "__main__":
    unittest.main()
