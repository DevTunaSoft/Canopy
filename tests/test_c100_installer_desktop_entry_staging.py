"""Offline unit tests for escaped desktop-entry staging with ownership.

These are pure Python tests using a temporary staging directory. They run on
the Windows host and do not touch XDG paths or a real desktop session. They
are not tests of Linux Mint, the compiled Qt application or a real install.
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canopy_features.installer import desktop_entry_staging as staging

SOURCE = ROOT / "canopy_features" / "installer" / "desktop_entry_staging.py"


class BuildEntryTests(unittest.TestCase):
    def test_escapes_spaces_and_quotes_every_argument(self):
        payload = staging.build_entry(
            "Canopy Classic",
            ["/opt/with spaces/canopy-classic", "--flag", "value with spaces"],
        )
        text = payload.decode("utf-8")
        self.assertIn(
            'Exec="/opt/with spaces/canopy-classic" "--flag" "value with spaces"',
            text,
        )
        self.assertNotIn("sh -c", text)
        self.assertTrue(text.startswith("[Desktop Entry]\n"))
        self.assertIn("Type=Application", text)
        self.assertIn("Name=Canopy Classic", text)
        self.assertIn("Terminal=false", text)

    def test_malformed_exec_fields_rejected(self):
        # Includes the Desktop Entry field code %f and Windows-style backslashes.
        bad = ('a"b', "a\\b", "a$b", "a`b", "a%f", "a\nb", "a\rb", "a\x00b")
        for value in bad:
            with self.subTest(value=repr(value)):
                with self.assertRaises(staging.StagingError):
                    staging.build_entry("X", ["/app", value])

    def test_empty_and_nonstring_exec_args_rejected(self):
        for args in ([], [""], [None], [123], ["/app", None]):
            with self.subTest(args=args):
                with self.assertRaises(staging.StagingError):
                    staging.build_entry("X", args)

    def test_invalid_name_and_metadata_rejected(self):
        for name in ("", "bad\nname", "bad=name"):
            with self.subTest(name=name):
                with self.assertRaises(staging.StagingError):
                    staging.build_entry(name, ["/app"])
        with self.assertRaises(staging.StagingError):
            staging.build_entry("X", ["/app"], comment="line\nbreak")
        with self.assertRaises(staging.StagingError):
            staging.build_entry("X", ["/app"], icon="a=b")

    def test_quote_argument_reuses_existing_quoter(self):
        self.assertEqual(staging.quote_argument("/a b"), '"/a b"')
        with self.assertRaises(staging.StagingError):
            staging.quote_argument("/a%b")


class StageVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.stage_dir = self.base / "xdg data with spaces" / "staging"
        self.payload = staging.build_entry(
            "Canopy Classic", ["/opt/canopy-classic", "--flag"]
        )

    def test_verify_not_staged_initially(self):
        self.assertEqual(staging.verify(self.stage_dir), "NOT_STAGED")

    def test_stage_round_trip_ownership(self):
        entry = staging.stage(self.stage_dir, self.payload)
        self.assertTrue(entry.is_file())
        self.assertEqual(entry.read_bytes(), self.payload)
        self.assertEqual(staging.verify(self.stage_dir), "OWNED")
        record = json.loads(
            (self.stage_dir / staging.RECORD_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(record["schema"], staging.SCHEMA)
        self.assertEqual(record["entry"], staging.DEFAULT_ENTRY)
        self.assertEqual(
            record["sha256"], hashlib.sha256(self.payload).hexdigest()
        )

    def test_existing_user_entry_refused(self):
        self.stage_dir.mkdir(parents=True)
        existing = self.stage_dir / staging.DEFAULT_ENTRY
        existing.write_bytes(b"user's own desktop entry")
        with self.assertRaisesRegex(staging.StagingError, "existing user entry"):
            staging.stage(self.stage_dir, self.payload)
        self.assertEqual(existing.read_bytes(), b"user's own desktop entry")
        self.assertFalse((self.stage_dir / staging.RECORD_NAME).exists())

    def test_existing_ownership_record_refused(self):
        self.stage_dir.mkdir(parents=True)
        record = self.stage_dir / staging.RECORD_NAME
        record.write_bytes(b"user record")
        with self.assertRaisesRegex(staging.StagingError, "existing ownership"):
            staging.stage(self.stage_dir, self.payload)
        self.assertEqual(record.read_bytes(), b"user record")
        self.assertFalse((self.stage_dir / staging.DEFAULT_ENTRY).exists())

    def test_modified_entry_detected(self):
        staging.stage(self.stage_dir, self.payload)
        entry = self.stage_dir / staging.DEFAULT_ENTRY
        entry.write_bytes(self.payload + b"\n# injected\n")
        self.assertEqual(staging.verify(self.stage_dir), "MODIFIED_OR_UNMANAGED")

    def test_modified_record_detected(self):
        staging.stage(self.stage_dir, self.payload)
        (self.stage_dir / staging.RECORD_NAME).write_text(
            '{"schema":1,"sha256":"bad"}', encoding="utf-8"
        )
        self.assertEqual(staging.verify(self.stage_dir), "MODIFIED_OR_UNMANAGED")

    def test_stage_twice_refused_without_overwrite(self):
        entry = staging.stage(self.stage_dir, self.payload)
        before = entry.read_bytes()
        with self.assertRaises(staging.StagingError):
            staging.stage(self.stage_dir, self.payload)
        self.assertEqual(entry.read_bytes(), before)
        self.assertEqual(staging.verify(self.stage_dir), "OWNED")

    def test_partial_failure_rolls_back(self):
        original = Path.open

        def fail_on_record(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "")
            if path.name == staging.RECORD_NAME and "x" in str(mode):
                raise OSError("simulated full disk")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", autospec=True, side_effect=fail_on_record):
            with self.assertRaises(OSError):
                staging.stage(self.stage_dir, self.payload)
        self.assertFalse((self.stage_dir / staging.DEFAULT_ENTRY).exists())
        self.assertFalse((self.stage_dir / staging.RECORD_NAME).exists())

    def test_symlinked_entry_target_refused(self):
        outside = self.base / "outside.desktop"
        outside.write_bytes(b"private")
        self.stage_dir.mkdir(parents=True)
        (self.stage_dir / staging.DEFAULT_ENTRY).symlink_to(outside)
        with self.assertRaises(staging.StagingError):
            staging.stage(self.stage_dir, self.payload)
        self.assertEqual(outside.read_bytes(), b"private")

    def test_verify_symlink_is_unsafe(self):
        outside = self.base / "outside.desktop"
        outside.write_bytes(self.payload)
        self.stage_dir.mkdir(parents=True)
        (self.stage_dir / staging.DEFAULT_ENTRY).symlink_to(outside)
        self.assertEqual(staging.verify(self.stage_dir), "UNSAFE")

    def test_invalid_filename_and_payload_rejected(self):
        for name in ("bad.txt", "../bad.desktop", "a/b.desktop", "x\ny.desktop"):
            with self.subTest(name=name):
                with self.assertRaises(staging.StagingError):
                    staging.stage(self.stage_dir, self.payload, filename=name)
        for payload in (b"", "not bytes"):
            with self.subTest(payload=payload):
                with self.assertRaises(staging.StagingError):
                    staging.stage(self.stage_dir, payload)


class SourceContractTests(unittest.TestCase):
    def test_reuses_existing_escaping_and_digest_capability(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("from tools import register_classic_preview as menu", text)
        self.assertIn("menu._quote", text)
        self.assertIn("menu._sha", text)

    def test_no_polling_background_or_privileged_operations(self):
        text = SOURCE.read_text(encoding="utf-8")
        for token in ("while True", "import subprocess", "import threading",
                      "geteuid", "import socket", "sleep(", "schedule"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
