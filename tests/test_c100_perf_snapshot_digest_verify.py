"""Contract tests for the bounded offline digest-pin verification gate.

Run: python -m unittest tests.test_c100_perf_snapshot_digest_verify -v
"""
import ast
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from canopy_features.performance.frame_pacing import parse_frame_times
from canopy_features.performance.performance_snapshot import compose_snapshot
from tools.qa import perf_snapshot_digest as digest_gate
from tools.qa import perf_snapshot_digest_verify as gate


def artifact(sample=16.7, pss_kib=150_000):
    return compose_snapshot(
        frame_pacing=parse_frame_times([sample], refresh_hz=60),
        pss_kib=pss_kib,
    ).as_dict()


_UNSET = object()


def valid_record(value=_UNSET, sha=_UNSET, length=_UNSET):
    value = artifact() if value is _UNSET else value
    computed = digest_gate.digest_artifact(value)
    return {
        "schema": gate.SCHEMA,
        "artifact": value,
        "sha256": computed.sha256 if sha is _UNSET else sha,
        "byte_length": computed.byte_length if length is _UNSET else length,
    }


APPROVAL_KEYS = ("release_approved", "linux_mint_acceptance_proven",
                 "real_hardware_measured", "owner_visual_approval",
                 "measurement_performed")


class RealVerificationTests(unittest.TestCase):
    def test_matching_pin(self):
        report = gate.verify_record(valid_record()).as_dict()
        self.assertEqual(report["status"], "MATCH")
        self.assertEqual(report["schema"], gate.SCHEMA)
        for key in APPROVAL_KEYS:
            self.assertIs(report[key], False)

    def test_wrong_sha_pin_is_mismatch(self):
        pin = "0" * 64
        report = gate.verify_record(valid_record(sha=pin)).as_dict()
        self.assertEqual(report["status"], "MISMATCH")

    def test_wrong_byte_length_is_mismatch(self):
        report = gate.verify_record(valid_record(length=1)).as_dict()
        self.assertEqual(report["status"], "MISMATCH")

    def test_different_artifact_with_stale_pin_is_mismatch(self):
        record = valid_record()
        record["artifact"] = artifact(sample=99.9)
        self.assertEqual(gate.verify_record(record).as_dict()["status"],
                         "MISMATCH")

    def test_json_roundtrip_matches(self):
        record = valid_record()
        reparsed = json.loads(json.dumps(record))
        self.assertEqual(gate.verify_json(json.dumps(reparsed)).as_dict()["status"],
                         "MATCH")

    def test_report_is_immutable(self):
        rec = gate.verify_record(valid_record())
        with self.assertRaises(AttributeError):
            rec.status = "MISMATCH"

    def test_forged_record_cannot_emit_approval(self):
        forged = gate.VerifyReport("MATCH")
        report = forged.as_dict()
        for key in APPROVAL_KEYS:
            self.assertIs(report[key], False)

    def test_no_raw_value_echo(self):
        value = artifact()
        value["frame_pacing"]["backend"] = "SECRET_VERIFY_MARKER"
        record = valid_record(value=value)
        rendered = json.dumps(gate.verify_record(record).as_dict(), sort_keys=True)
        self.assertNotIn("SECRET_VERIFY_MARKER", rendered)

    def test_deterministic_bytes(self):
        text = json.dumps(valid_record())
        self.assertEqual(
            json.dumps(gate.verify_json(text).as_dict(), sort_keys=True),
            json.dumps(gate.verify_json(text).as_dict(), sort_keys=True),
        )


class InputValidationTests(unittest.TestCase):
    def test_bad_key_set(self):
        base = valid_record()
        for bad in ({}, {"schema": 1}, dict(base, extra=1)):
            with self.subTest(keys=sorted(bad)), self.assertRaises(gate.VerifyError):
                gate.verify_record(bad)

    def test_wrong_schema_types_and_values(self):
        for bad in ("1", True, 2, 1.0, None):
            record = valid_record()
            record["schema"] = bad
            with self.subTest(bad=bad), self.assertRaises(gate.VerifyError):
                gate.verify_record(record)

    def test_malformed_sha_pins(self):
        for bad in ("", "abc", "A" * 64, "g" * 64, "0" * 65, 7, None, [], {}):
            record = valid_record(sha=bad)
            with self.subTest(bad=bad), self.assertRaises(gate.VerifyError):
                gate.verify_record(record)

    def test_malformed_byte_lengths(self):
        for bad in (0, -1, True, "7", None,
                    digest_gate.MAX_CANONICAL_BYTES + 1):
            record = valid_record(length=bad)
            with self.subTest(bad=bad), self.assertRaises(gate.VerifyError):
                gate.verify_record(record)

    def test_forged_claim_artifact_rejected(self):
        record = valid_record()
        record["artifact"]["measurement_performed"] = True
        with self.assertRaises(gate.VerifyError) as ctx:
            gate.verify_record(record)
        self.assertEqual(str(ctx.exception), "snapshot artifact rejected")
        self.assertIsInstance(ctx.exception.__cause__,
                              digest_gate.DigestError)

    def test_non_mapping_artifact_rejected(self):
        for bad in (None, [], 7, "x", True):
            record = valid_record()
            record["artifact"] = bad
            with self.subTest(bad=bad), self.assertRaises(gate.VerifyError):
                gate.verify_record(record)

    def test_forged_report_bad_status_fails_closed(self):
        for bad in ("", "APPROVED", "MATCH ", 7, None, [], {}):
            rec = gate.VerifyReport(bad)
            with self.subTest(bad=bad), self.assertRaises(gate.VerifyError):
                rec.as_dict()

    def test_json_wrong_types_rejected(self):
        for bad in (None, 7, [], {}):
            with self.subTest(bad=bad), self.assertRaises(gate.VerifyError):
                gate.verify_json(bad)

    def test_json_empty_oversized_deep_nonfinite(self):
        cases = ["", "x" * (gate.MAX_VERIFY_BYTES + 1),
                 "[" * 4000 + "]" * 4000,
                 json.dumps(valid_record()).replace('"schema": 1',
                                                    '"schema": NaN', 1)]
        for text in cases:
            with self.subTest(size=len(text)), self.assertRaises(gate.VerifyError):
                gate.verify_json(text)


class FileBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, payload, name="record.json"):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_file(self):
        path = self._write(valid_record())
        self.assertEqual(gate.verify_file(path).as_dict()["status"], "MATCH")

    def test_relative_path_rejected(self):
        with self.assertRaises(gate.VerifyError):
            gate.verify_file(Path("relative.json"))

    def test_missing_file_rejected(self):
        with self.assertRaises(gate.VerifyError):
            gate.verify_file(self.root / "nope.json")

    def test_directory_rejected(self):
        with self.assertRaises(gate.VerifyError):
            gate.verify_file(self.root)

    def test_symlink_final_rejected(self):
        target = self._write(valid_record(), "target.json")
        link = self.root / "link.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(gate.VerifyError):
            gate.verify_file(link)

    def test_oversized_file_rejected(self):
        path = self.root / "big.json"
        path.write_text("x" * (gate.MAX_VERIFY_BYTES + 1), encoding="utf-8")
        with self.assertRaises(gate.VerifyError):
            gate.verify_file(path)

    def test_posix_fdopen_failure_translated(self):
        with mock.patch.object(gate.os, "open", return_value=999), \
                mock.patch.object(gate.os, "fdopen",
                                  side_effect=IsADirectoryError("is a dir")):
            with self.assertRaises(gate.VerifyError) as ctx:
                gate.verify_file(self.root / "anything.json")
        self.assertNotIn("is a dir", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, IsADirectoryError)

    def test_main_match(self):
        path = self._write(valid_record())
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "MATCH")

    def test_main_mismatch_has_marker(self):
        path = self._write(valid_record(sha="0" * 64))
        err = io.StringIO()
        with redirect_stderr(err):
            code = gate.main([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("QT_PERF_DIGEST_VERIFY_FAIL:", err.getvalue())

    def test_main_error_has_marker_and_no_echo(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = gate.main([str(self.root / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("QT_PERF_DIGEST_VERIFY_FAIL:", err.getvalue())


class PurityTests(unittest.TestCase):
    def test_no_forbidden_imports_or_exec(self):
        source = Path(gate.__file__).resolve().read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = {"argparse", "hmac", "json", "os", "pathlib", "stat",
                   "sys", "tools"}
        forbidden = {"time", "random", "subprocess", "socket", "threading",
                     "datetime", "multiprocessing", "ctypes"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(top, forbidden)
                    self.assertIn(top, allowed)
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                self.assertNotIn(top, forbidden)
                self.assertIn(top, allowed)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, {"system", "popen", "Popen"})


if __name__ == "__main__":
    unittest.main()
