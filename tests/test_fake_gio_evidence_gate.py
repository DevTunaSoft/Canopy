"""Deterministic tests for the synthetic fake-GIO evidence gate.

All log text here is fabricated fixture input; these tests validate the gate,
not a real launch, Mint guest or visual result.
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools.qa import fake_gio_evidence_gate as gate


def fixture_log():
    lines = []
    for name, calls in gate.EXPECTED_MAPPING_CALLS.items():
        lines.append("CASE_PASS: %s | can=1 launch=1 calls=%s"
                     % (name, " > ".join(calls)))
    for name in ("refusal:opt-in-disabled", "refusal:unknown-action",
                 "refusal:unavailable", "refusal:launch-failure-no-fallback"):
        lines.append("CASE_PASS: %s | %s"
                     % (name, gate.EXPECTED_REFUSAL_DETAILS[name]))
    lines.append("SUMMARY: cases=11 result=ALL_PASS")
    return "\n".join(lines) + "\n"


def fallback_log():
    name = gate.FALLBACK_CASE_NAMES[0]
    return ("CASE_PASS: %s | %s\nSUMMARY: cases=1 result=ALL_PASS\n"
            % (name, gate.EXPECTED_REFUSAL_DETAILS[name]))


class FakeGioEvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_dir = Path(self.tmp.name)
        self.write_defaults()

    def write_defaults(self):
        (self.log_dir / "gio-fixture.log").write_text(fixture_log(), encoding="utf-8")
        (self.log_dir / "gio-fallback.log").write_text(fallback_log(), encoding="utf-8")
        (self.log_dir / "fake-gio-call-log.txt").write_text(
            "\n".join(gate.EXPECTED_FINAL_CALL_LOG) + "\n", encoding="utf-8")
        (self.log_dir / "source-sha256-check.txt").write_text(
            "".join("%s  %s\n" % (digest, name)
                    for name, digest in sorted(gate.SOURCE_SHA256.items())),
            encoding="utf-8")

    def test_valid_logs_give_synthetic_not_mint_evidence(self):
        evidence = gate.assess(self.log_dir)
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["classification"], "SYNTHETIC")
        self.assertFalse(evidence["linux_mint"])
        self.assertFalse(evidence["real_gio"])
        self.assertFalse(evidence["real_desktop_launch"])
        self.assertFalse(evidence["visual_approval"])
        self.assertEqual(evidence["screen_reader"], "NOT_RUN")
        self.assertEqual(evidence["case_count"], 12)
        self.assertEqual(len(evidence["mapping"]), 7)
        self.assertEqual(len(evidence["refusals"]), 5)
        self.assertEqual(len(evidence["artifact_sha256"]), 3)

    def test_six_dock_mappings_are_exact(self):
        mapping = gate.assess(self.log_dir)["mapping"]
        self.assertEqual(
            [mapping["mapping:" + label][-1] for label in
             ("Browser", "Terminal", "Calendar", "Photos", "Mail", "Files")],
            ["launch firefox.desktop", "launch gnome-terminal.desktop",
             "launch org.gnome.Calendar.desktop", "launch pix.desktop",
             "launch thunderbird.desktop", "launch nemo.desktop"],
        )

    def test_msys_binary_marker_source_hashes_accepted(self):
        (self.log_dir / "source-sha256-check.txt").write_text(
            "".join("%s *%s\n" % (digest, name)
                    for name, digest in sorted(gate.SOURCE_SHA256.items())),
            encoding="utf-8")
        self.assertEqual(gate.assess(self.log_dir)["case_count"], 12)

    def test_wrong_mapping_call_fails_closed(self):
        text = fixture_log().replace(
            "new firefox.desktop > should_show firefox.desktop",
            "new chromium.desktop > should_show firefox.desktop", 1)
        (self.log_dir / "gio-fixture.log").write_text(text, encoding="utf-8")
        with self.assertRaises(gate.FakeGioEvidenceError):
            gate.assess(self.log_dir)

    def test_case_fail_and_missing_case_fail_closed(self):
        text = fixture_log().replace(
            "CASE_PASS: mapping:Browser |", "CASE_FAIL: mapping:Browser |", 1)
        (self.log_dir / "gio-fixture.log").write_text(text, encoding="utf-8")
        with self.assertRaises(gate.FakeGioEvidenceError):
            gate.assess(self.log_dir)
        self.write_defaults()
        text = fixture_log().replace(
            "CASE_PASS: mapping:Files | can=1 launch=1 calls=", "", 1)
        (self.log_dir / "gio-fixture.log").write_text(text, encoding="utf-8")
        with self.assertRaises(gate.FakeGioEvidenceError):
            gate.assess(self.log_dir)

    def test_final_call_log_and_source_hash_mutations_fail_closed(self):
        (self.log_dir / "fake-gio-call-log.txt").write_text(
            "launch firefox.desktop\n", encoding="utf-8")
        with self.assertRaises(gate.FakeGioEvidenceError):
            gate.assess(self.log_dir)
        self.write_defaults()
        (self.log_dir / "source-sha256-check.txt").write_text(
            "0" * 64 + "  SystemAppLauncher.cpp\n", encoding="utf-8")
        with self.assertRaises(gate.FakeGioEvidenceError):
            gate.assess(self.log_dir)

    def test_cli_writes_json_with_sha256_artifacts(self):
        output = self.log_dir / "evidence" / "fake-gio-evidence.json"
        rc = gate.main([
            "--log-dir", str(self.log_dir), "--output", str(output),
        ])
        self.assertEqual(rc, 0)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["classification"], "SYNTHETIC")
        self.assertEqual(len(payload["artifact_sha256"]["gio-fixture.log"]), 64)


if __name__ == "__main__":
    unittest.main()
