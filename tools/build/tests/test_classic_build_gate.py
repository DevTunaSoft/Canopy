#!/usr/bin/env python3
"""Regression tests for the source-pin contract of the Classic build gate.

Fixtures are synthetic scratch bundles (no network, no repository binary and
no credentials). Run with:

    python -m unittest tools.build.tests.test_classic_build_gate -v
    python -m unittest tests.test_classic_build_gate -v
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
QA_DIR = ROOT / "tools" / "qa"
sys.path.insert(0, str(QA_DIR))

import classic_build_gate as gate  # noqa: E402

# The historical pin that made the gate fail at the live integration tip.
STALE_PIN = "b31c995a650202b66c08064a7cc3b7b4f0609d2d"
CORRECT_PIN = "c" * 40
SHA40_LITERAL = re.compile(r"\b[0-9a-f]{40}\b")


def _build_module():
    path = ROOT / "tools" / "build" / "classic_release_build.py"
    spec = importlib.util.spec_from_file_location("classic_release_build_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateRunMixin:
    def fresh(self, source_sha=None):
        root = Path(tempfile.mkdtemp(prefix="classic-gate-test-"))
        if source_sha is None:
            gate.make_bundle(root / "case")
        else:
            gate.make_bundle(root / "case", source_sha=source_sha)
        return root

    def verdict(self, root, pin=gate.FIXTURE_SOURCE_SHA):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = gate.verify(root / "case", pin)
        text = buffer.getvalue()
        first = next((line.split()[1] for line in text.splitlines()
                      if line.startswith("FIRST ")), "NONE")
        return rc, first, text


class PinContractTests(GateRunMixin, unittest.TestCase):
    def test_no_hardcoded_integration_sha_in_gate(self):
        text = (QA_DIR / "classic_build_gate.py").read_text(encoding="utf-8")
        self.assertNotIn("EXPECTED_SOURCE_SHA", text)
        self.assertIsNone(SHA40_LITERAL.search(text))
        self.assertIsNotNone(gate.normalize_source_sha("A" * 40))

    def test_no_hardcoded_integration_sha_in_build_script(self):
        text = (ROOT / "tools" / "build" / "classic_release_build.py").read_text(
            encoding="utf-8")
        self.assertIsNone(SHA40_LITERAL.search(text))
        self.assertIn('--source-sha", required=True', text)
        module = _build_module()
        self.assertEqual(module.canonical_sha(STALE_PIN), STALE_PIN)
        self.assertEqual(module.canonical_sha("F" * 40), "f" * 40)
        for bad in (None, "", "xyz", "g" * 40, "f" * 39, "f" * 41):
            self.assertIsNone(module.canonical_sha(bad))

    def test_stale_pin_fails_closed(self):
        root = self.fresh(source_sha=CORRECT_PIN)
        rc, first, text = self.verdict(root, pin=STALE_PIN)
        self.assertEqual(rc, 1, text)
        self.assertEqual(first, "SOURCE_SHA", text)
        self.assertIn("VERDICT FAIL", text)

    def test_correct_pin_passes(self):
        root = self.fresh(source_sha=CORRECT_PIN)
        rc, first, text = self.verdict(root, pin=CORRECT_PIN)
        self.assertEqual(rc, 0, text)
        self.assertEqual(first, "NONE", text)
        self.assertIn("VERDICT PASS", text)

    def test_malformed_pin_fails_closed(self):
        root = self.fresh()
        for bad in ("", "xyz", "g" * 40, "f" * 39, None, 40):
            with self.subTest(pin=bad):
                rc, first, text = self.verdict(root, pin=bad)
                self.assertEqual(rc, 1, text)
                self.assertEqual(first, "SOURCE_SHA", text)

    def test_gate_cli_requires_explicit_source_pin(self):
        root = self.fresh()
        completed = subprocess.run(
            [sys.executable, str(QA_DIR / "classic_build_gate.py"), "verify",
             "--evidence", str(root / "case")],
            capture_output=True, text=True, timeout=90)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("--source-sha", completed.stderr)

    def test_build_rejects_stale_pin_before_any_build(self):
        out = Path(tempfile.mkdtemp(prefix="classic-build-stale-pin-"))
        script = ROOT / "tools" / "build" / "classic_release_build.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--source", str(ROOT),
             "--source-sha", STALE_PIN, "--out", str(out)],
            capture_output=True, text=True, timeout=90)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("BUILD_FAIL: source HEAD", completed.stdout)
        self.assertFalse((out / "evidence").exists())


class GreenTests(GateRunMixin, unittest.TestCase):
    def test_synthetic_bundle_is_green(self):
        root = self.fresh()
        rc, first, text = self.verdict(root)
        self.assertEqual(rc, 0)
        self.assertEqual(first, "NONE")
        self.assertIn("SUMMARY checks=12 pass=12 fail=0", text)
        self.assertIn("VERDICT PASS", text)

    def test_png_generator_and_strict_parser(self):
        payload = gate.make_png(760, 500)
        path = Path(tempfile.mkdtemp(prefix="classic-gate-png-")) / "shot.png"
        path.write_bytes(payload)
        width, height, samples = gate._png_pixels(path)
        self.assertEqual((width, height), (760, 500))
        self.assertGreaterEqual(len(samples), 8)
        path.write_bytes(gate.make_png(760, 500, uniform=True))
        _, _, uniform_samples = gate._png_pixels(path)
        self.assertEqual(len(uniform_samples), 1)

    def test_full_gate_selftest_covers_all_negative_controls(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = gate.selftest()
        text = buffer.getvalue()
        self.assertEqual(rc, 0, text)
        self.assertIn("SUMMARY cases=13 correct=13", text)
        self.assertIn("MUTATION stale-pin expected=SOURCE_SHA first=SOURCE_SHA rc=1 PASS", text)
        self.assertIn("MUTATION malformed-pin expected=SOURCE_SHA first=SOURCE_SHA rc=1 PASS", text)


class NegativeControlTests(GateRunMixin, unittest.TestCase):
    def assert_red(self, mutation, expected_first):
        root = self.fresh()
        mutation(root / "case")
        rc, first, text = self.verdict(root)
        self.assertEqual(rc, 1, text)
        self.assertEqual(first, expected_first, text)
        self.assertIn("VERDICT FAIL", text)

    def test_wrong_source_sha(self):
        self.assert_red(
            lambda d: gate._edit_json(d, "source_sha", "1" * 40), "SOURCE_SHA")

    def test_wrong_toolchain_record(self):
        self.assert_red(
            lambda d: gate._edit_text(d / gate.TOOLCHAIN_NAME,
                                      "cmake: CMake version 4.5.1",
                                      "cmake: wrong version"), "TOOLCHAIN")

    def test_reproducibility_hash_mismatch(self):
        self.assert_red(lambda d: gate._edit_json(d, "reproducibility", {
            "source_date_epoch": "0", "build_hashes": ["2" * 64, "3" * 64],
        }), "REPRO_HASHES")

    def test_binary_manifest_hash_mismatch(self):
        self.assert_red(
            lambda d: gate._edit_manifest(d, gate.BINARY_REL, "4" * 64), "BINARY")

    def test_manifest_path_traversal(self):
        self.assert_red(
            lambda d: gate._edit_manifest_key(d, "../escape"), "MANIFEST_KEYS")

    def test_untouched_log_hash_mismatch(self):
        self.assert_red(lambda d: gate._edit_text(
            d / "selftest-1200x750.log", "CANOPY_APPROVED_ART_VERIFIED",
            "CANOPY_APPROVED_ART_VERIFIED\n# scratch mutation"), "FILE_HASHES")

    def test_missing_selftest_marker(self):
        self.assert_red(lambda d: (
            gate._edit_text(d / "selftest-1920x1080.log",
                            "SELF_TEST_PASS: nonuniform window screenshot captured", ""),
            gate.remanifest(d)), "SELFTEST_LOGS")

    def test_wrong_screenshot_resolution(self):
        self.assert_red(lambda d: (
            gate._replace_png(d, "screenshots/classic-1200x750.png", 800, 500),
            gate.remanifest(d)), "SCREENSHOTS")

    def test_uniform_screenshot(self):
        self.assert_red(lambda d: (
            gate._replace_uniform(d, "screenshots/classic-760x500.png", 760, 500),
            gate.remanifest(d)), "SCREENSHOTS")

    def test_capability_marker_missing(self):
        self.assert_red(lambda d: (
            gate._edit_text(d / gate.CAPABILITY_LOG, "CANOPY_GIO_DISABLED",
                            "CANOPY_GIO_ENABLED"), gate.remanifest(d)),
            "CAPABILITY_LOG")


class RealEvidenceTests(unittest.TestCase):
    def test_real_evidence_if_supplied(self):
        root = os.environ.get("CANOPY_CLASSIC_EVIDENCE")
        if not root:
            self.skipTest("CANOPY_CLASSIC_EVIDENCE not set")
        pin = os.environ.get("CANOPY_CLASSIC_SOURCE_SHA")
        if not pin:
            self.fail("CANOPY_CLASSIC_SOURCE_SHA must accompany CANOPY_CLASSIC_EVIDENCE")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = gate.verify(Path(root), pin)
        text = buffer.getvalue()
        self.assertEqual(rc, 0, text)
        self.assertIn("VERDICT PASS", text)


if __name__ == "__main__":
    unittest.main()
