"""Contract tests for the bounded offline performance snapshot digest gate.

Run: python -m unittest tests.test_c100_perf_snapshot_digest -v
"""
import ast
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from canopy_features.performance.frame_pacing import parse_frame_times
from canopy_features.performance.performance_snapshot import compose_snapshot
from tools.qa import perf_snapshot_digest as gate


def artifact(sample=16.7, pss_kib=150_000):
    """Build a real snapshot artifact through the merged producer."""
    return compose_snapshot(
        frame_pacing=parse_frame_times([sample], refresh_hz=60),
        pss_kib=pss_kib,
    ).as_dict()


APPROVAL_KEYS = ("release_approved", "linux_mint_acceptance_proven",
                 "real_hardware_measured", "owner_visual_approval",
                 "measurement_performed")


class RealArtifactTests(unittest.TestCase):
    def test_digest_of_real_artifact(self):
        report = gate.digest_artifact(artifact()).as_dict()
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(report["schema"], gate.SCHEMA)
        self.assertRegex(report["sha256"], r"^[0-9a-f]{64}$")
        self.assertIsInstance(report["byte_length"], int)
        self.assertGreater(report["byte_length"], 0)

    def test_digest_matches_independent_canonical_hash(self):
        value = artifact()
        expected_bytes = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
        report = gate.digest_artifact(value)
        self.assertEqual(report.sha256, hashlib.sha256(expected_bytes).hexdigest())
        self.assertEqual(report.byte_length, len(expected_bytes))

    def test_deterministic_across_key_order(self):
        value = artifact()
        first = gate.digest_artifact(value)
        shuffled = dict(reversed(list(value.items())))
        self.assertEqual(gate.digest_artifact(shuffled), first)

    def test_deterministic_across_json_roundtrip(self):
        value = artifact()
        first = gate.digest_artifact(value)
        reparsed = json.loads(json.dumps(value))
        self.assertEqual(gate.digest_artifact(reparsed), first)

    def test_different_artifacts_have_different_digests(self):
        self.assertNotEqual(
            gate.digest_artifact(artifact(sample=16.7)),
            gate.digest_artifact(artifact(sample=99.9)),
        )

    def test_negative_claims_hardcoded(self):
        report = gate.digest_artifact(artifact()).as_dict()
        for key in APPROVAL_KEYS:
            self.assertIs(report[key], False)

    def test_no_raw_value_echo(self):
        value = artifact()
        value["frame_pacing"]["backend"] = "SECRET_BACKEND_MARKER"
        report = gate.digest_artifact(value).as_dict()
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("SECRET_BACKEND_MARKER", rendered)

    def test_report_is_immutable(self):
        rec = gate.digest_artifact(artifact())
        with self.assertRaises(AttributeError):
            rec.sha256 = "0" * 64

    def test_as_dict_returns_fresh_container(self):
        rec = gate.digest_artifact(artifact())
        first = rec.as_dict()
        first["sha256"] = "0" * 64
        self.assertNotEqual(rec.as_dict()["sha256"], "0" * 64)

    def test_deterministic_bytes(self):
        payload = artifact()
        a = json.dumps(gate.digest_artifact(payload).as_dict(), sort_keys=True)
        b = json.dumps(gate.digest_artifact(payload).as_dict(), sort_keys=True)
        self.assertEqual(a, b)


class ValidatorCompositionTests(unittest.TestCase):
    def test_forged_claim_rejected_with_fixed_token(self):
        for key in ("measurement_performed", "real_hardware_measured",
                    "linux_mint_acceptance", "owner_visual_approval"):
            value = artifact()
            value[key] = True
            with self.subTest(key=key), self.assertRaises(gate.DigestError):
                gate.digest_artifact(value)

    def test_extra_key_rejected(self):
        value = artifact()
        value["injected"] = "x"
        with self.assertRaises(gate.DigestError):
            gate.digest_artifact(value)

    def test_missing_key_rejected(self):
        value = artifact()
        del value["pss_kib"]
        with self.assertRaises(gate.DigestError):
            gate.digest_artifact(value)

    def test_wrong_types_rejected(self):
        for bad in (None, [], 7, "x", True):
            with self.subTest(bad=bad), self.assertRaises(gate.DigestError):
                gate.digest_artifact(bad)

    def test_nested_gpu_claim_rejected(self):
        value = artifact()
        value["frame_pacing"]["real_gpu_measurement"] = True
        with self.assertRaises(gate.DigestError):
            gate.digest_artifact(value)

    def test_subvalidator_detail_not_echoed(self):
        value = artifact()
        value["linux_mint_acceptance"] = "SENTINEL_ACCEPTED_77"
        with self.assertRaises(gate.DigestError) as ctx:
            gate.digest_artifact(value)
        self.assertNotIn("SENTINEL_ACCEPTED_77", str(ctx.exception))
        self.assertEqual(str(ctx.exception), "snapshot artifact rejected")
        self.assertIsInstance(ctx.exception.__cause__,
                              gate.snapshot_validator.ArtifactError)


class ForgedReportTests(unittest.TestCase):
    def test_bad_digest_tokens_fail_closed(self):
        for bad in ("", "abc", "A" * 64, "g" * 64, "0" * 65, 7, None, [], {}):
            rec = gate.DigestReport(bad, 100)
            with self.subTest(bad=bad), self.assertRaises(gate.DigestError):
                rec.as_dict()

    def test_bad_byte_length_fails_closed(self):
        for bad in (0, -1, gate.MAX_CANONICAL_BYTES + 1, True, "100", None):
            rec = gate.DigestReport("a" * 64, bad)
            with self.subTest(bad=bad), self.assertRaises(gate.DigestError):
                rec.as_dict()

    def test_forged_record_cannot_emit_approval(self):
        rec = gate.DigestReport("b" * 64, 123)
        report = rec.as_dict()
        for key in APPROVAL_KEYS:
            self.assertIs(report[key], False)


class JsonBoundaryTests(unittest.TestCase):
    def test_json_accepts_bytes_and_str(self):
        text = json.dumps(artifact())
        self.assertIsInstance(gate.digest_json(text), gate.DigestReport)
        self.assertIsInstance(
            gate.digest_json(text.encode("utf-8")), gate.DigestReport)

    def test_json_wrong_types_rejected(self):
        for bad in (None, 7, [], {}):
            with self.subTest(bad=bad), self.assertRaises(gate.DigestError):
                gate.digest_json(bad)

    def test_json_empty_and_oversized_rejected(self):
        for bad in ("", "x" * (gate.MAX_ARTIFACT_BYTES + 1)):
            with self.subTest(size=len(bad)), self.assertRaises(gate.DigestError):
                gate.digest_json(bad)

    def test_json_nonfinite_constant_rejected(self):
        text = json.dumps(artifact()).replace('"schema": 1', '"schema": NaN', 1)
        with self.assertRaises(gate.DigestError):
            gate.digest_json(text)

    def test_json_deep_nesting_rejected(self):
        text = "[" * 4000 + "]" * 4000
        with self.assertRaises(gate.DigestError):
            gate.digest_json(text)

    def test_json_flipped_claim_rejected(self):
        value = artifact()
        value["measurement_performed"] = True
        with self.assertRaises(gate.DigestError):
            gate.digest_json(json.dumps(value))


class FileBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, payload, name="artifact.json"):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_file(self):
        path = self._write(artifact())
        self.assertIsInstance(gate.digest_file(path), gate.DigestReport)

    def test_relative_path_rejected(self):
        with self.assertRaises(gate.DigestError):
            gate.digest_file(Path("relative.json"))

    def test_missing_file_rejected(self):
        with self.assertRaises(gate.DigestError):
            gate.digest_file(self.root / "nope.json")

    def test_directory_rejected(self):
        with self.assertRaises(gate.DigestError):
            gate.digest_file(self.root)

    def test_symlink_final_rejected(self):
        target = self._write(artifact(), "target.json")
        link = self.root / "link.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(gate.DigestError):
            gate.digest_file(link)

    def test_oversized_file_rejected(self):
        path = self.root / "big.json"
        path.write_text("x" * (gate.MAX_ARTIFACT_BYTES + 1), encoding="utf-8")
        with self.assertRaises(gate.DigestError):
            gate.digest_file(path)

    def test_posix_fdopen_failure_translated(self):
        with mock.patch.object(gate.os, "open", return_value=999), \
                mock.patch.object(gate.os, "fdopen",
                                  side_effect=IsADirectoryError("is a dir")):
            with self.assertRaises(gate.DigestError) as ctx:
                gate.digest_file(self.root / "anything.json")
        self.assertNotIn("is a dir", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, IsADirectoryError)

    def test_main_success(self):
        path = self._write(artifact())
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "VALID")

    def test_main_failure_has_marker_and_no_echo(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = gate.main([str(self.root / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("QT_PERF_DIGEST_FAIL:", err.getvalue())


class PurityTests(unittest.TestCase):
    def test_no_forbidden_imports_or_exec(self):
        source = Path(gate.__file__).resolve().read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = {"argparse", "hashlib", "json", "os", "pathlib", "re",
                   "stat", "sys", "tools"}
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
