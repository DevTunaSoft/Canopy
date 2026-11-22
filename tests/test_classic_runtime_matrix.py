"""Synthetic stand-ins test matrix mechanics; they are not real Qt runtime evidence."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

from tools.qa import classic_runtime_matrix as matrix
from tools.qt_smoke import qml_diagnostics


GOOD_STDOUT = b"CANOPY_CLASSIC_WINDOW_READY\n"
GOOD_STDERR = (
    b"CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and legacy blue wave\n"
    b"SELF_TEST_PASS: nonuniform window screenshot captured\n"
)

REAL_FLAGS = {
    "--approved-art-dir", "--landscape-wallpaper", "--self-test-approved",
    "--self-test-size", "--self-test-screenshot", "--self-test-launcher-screenshot",
    "--terminal-refinement", "--icon-framing-review",
}

READY_PREREQ = {
    "status": "PASS", "binary_name": "stub", "binary_available": True,
    "compiler_available": True, "compilers_found": [], "reason": None,
}


def make_png(path, width, height):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(((x * 7 + y * 11) % 256, 64, 96, 255))
    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows)))
            + chunk(b"IEND", b""))
    Path(path).write_bytes(data)


class ClassicRuntimeMatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "captures"
        self.out.mkdir()
        self.binary = self.root / "fake-qt"
        self.binary.write_text("stub", encoding="utf-8")
        self.art = self.root / "approved"
        self.art.mkdir()
        self.wallpaper = self.root / "wallpaper.png"
        self.wallpaper.write_bytes(b"stub")

    def runner(self, *, exit_code=0, stdout=GOOD_STDOUT, stderr=GOOD_STDERR,
               timed_out=False, png="good"):
        def execute(command, timeout_seconds, liveness_seconds):
            size = command[command.index("--self-test-size") + 1]
            width, height = map(int, size.split("x"))
            shot = Path(command[command.index("--self-test-screenshot") + 1])
            if png == "good":
                make_png(shot, width, height)
            elif png == "wrong":
                make_png(shot, width + 1, height)
            elif png == "corrupt":
                shot.write_bytes(b"not a PNG")
            return matrix.ProcessOutcome(
                returncode=exit_code, stdout=stdout, stderr=stderr,
                timed_out=timed_out,
            )
        return execute

    def run_matrix(self, **kwargs):
        options = dict(
            binary=kwargs.pop("binary", self.binary),
            art_dir=kwargs.pop("art_dir", self.art),
            wallpaper=kwargs.pop("wallpaper", self.wallpaper),
            output_dir=kwargs.pop("output_dir", self.out),
            prerequisites=kwargs.pop("prerequisites", READY_PREREQ),
            runner=kwargs.pop("runner", self.runner()),
        )
        options.update(kwargs)
        return matrix.run_matrix(**options)

    def test_sizes_locked_to_three_supported_resolutions(self):
        self.assertEqual(matrix.SIZES, ((760, 500), (1200, 750), (1920, 1080)))
        self.assertEqual(self.run_matrix()["sizes"],
                         ["760x500", "1200x750", "1920x1080"])

    def test_invented_or_duplicate_sizes_rejected(self):
        for sizes in (((800, 600),), ((760, 500), (760, 500))):
            with self.subTest(sizes=sizes):
                with self.assertRaises(matrix.MatrixError):
                    matrix.normalize_sizes(sizes)

    def test_build_command_uses_only_real_flags_and_values(self):
        command = matrix.build_command(self.binary, self.art, self.wallpaper,
                                       760, 500, self.out / "shot.png")
        self.assertEqual(command[0], str(self.binary))
        flags = [item for item in command if item.startswith("--")]
        self.assertTrue(set(flags).issubset(REAL_FLAGS))
        self.assertEqual(flags, ["--approved-art-dir", "--landscape-wallpaper",
                                 "--self-test-approved", "--self-test-size",
                                 "--self-test-screenshot"])
        self.assertEqual(command[command.index("--self-test-size") + 1], "760x500")
        self.assertEqual(command[command.index("--approved-art-dir") + 1], str(self.art))
        self.assertIn("--self-test-approved", command)

    def test_build_command_optional_flags_are_real(self):
        command = matrix.build_command(
            self.binary, self.art, self.wallpaper, 1920, 1080,
            self.out / "shot.png", terminal=self.root / "terminal.png",
            framing_review=True,
        )
        self.assertIn("--terminal-refinement", command)
        self.assertIn("--icon-framing-review", command)
        self.assertTrue(set(f for f in command if f.startswith("--")).issubset(REAL_FLAGS))

    def test_invalid_timeout_and_liveness_rejected(self):
        for timeout in (1, 31, 5.5, True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(matrix.MatrixError):
                    self.run_matrix(timeout_seconds=timeout)
        with self.assertRaises(matrix.MatrixError):
            self.run_matrix(liveness_seconds=10)

    def test_absent_binary_is_not_run_requirement(self):
        report = matrix.run_matrix(
            binary=self.root / "missing-binary", art_dir=self.art,
            wallpaper=self.wallpaper, output_dir=self.out,
            compiler_probe=lambda name: None,
        )
        self.assertEqual(report["prerequisites"]["status"], "NOT_RUN")
        self.assertEqual(report["overall"], "NOT_RUN")
        self.assertFalse(report["prerequisites"]["binary_available"])
        self.assertEqual([row["status"] for row in report["tests"]], ["NOT_RUN"] * 3)
        self.assertTrue(all(row["screenshot_sha256"] is None for row in report["tests"]))
        self.assertIn("binary/compiler prerequisite", report["notes"][0])

    def test_synthetic_standin_never_claims_runtime_pass(self):
        report = self.run_matrix(synthetic=True)
        self.assertEqual(report["mechanics_status"], "PASS")
        self.assertEqual(report["overall"], "NOT_RUN")
        self.assertEqual(report["capture_source"], "synthetic-test-stand-in")
        self.assertIn("not runtime evidence", report["notes"][-1])
        self.assertTrue(all(len(row["screenshot_sha256"]) == 64 for row in report["tests"]))

    def test_full_matrix_pass_with_verified_captures(self):
        report = self.run_matrix()
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(report["capture_source"], "real-compiled-binary")
        for row in report["tests"]:
            self.assertEqual(row["status"], "PASS")
            self.assertEqual(row["exit_code"], 0)
            self.assertTrue(row["window_ready"])
            self.assertTrue(row["approved_art_verified"])
            self.assertTrue(row["png_valid"])
            self.assertEqual(row["qml_errors"], [])

    def test_nonzero_exit_is_fail(self):
        report = self.run_matrix(runner=self.runner(exit_code=4))
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual([row["exit_code"] for row in report["tests"]], [4, 4, 4])
        self.assertEqual([row["status"] for row in report["tests"]], ["FAIL"] * 3)

    def test_timeout_is_fail_and_recorded(self):
        report = self.run_matrix(runner=self.runner(timed_out=True, exit_code=-9))
        self.assertEqual(report["overall"], "FAIL")
        self.assertTrue(all(row["timed_out"] for row in report["tests"]))
        self.assertTrue(all(row["screenshot_sha256"] is None for row in report["tests"]))

    def test_qml_diagnostics_reused_and_fatal_errors_fail(self):
        stderr = GOOD_STDERR + b"qrc:/Main.qml:20: ReferenceError: missing is not defined\n"
        report = self.run_matrix(runner=self.runner(stderr=stderr))
        self.assertEqual(report["overall"], "FAIL")
        for row in report["tests"]:
            self.assertEqual(row["qml_errors"], qml_diagnostics(stderr))
            self.assertTrue(any("ReferenceError" in item for item in row["qml_errors"]))

    def test_benign_qt_notice_does_not_fail(self):
        stderr = GOOD_STDERR + b"Qt warning: software backend selected\n"
        self.assertEqual(self.run_matrix(runner=self.runner(stderr=stderr))["overall"], "PASS")

    def test_missing_startup_markers_fail(self):
        for stderr in (GOOD_STDERR.replace(b"CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and legacy blue wave\n", b""),
                       b""):
            with self.subTest(stderr=stderr[:40]):
                report = self.run_matrix(runner=self.runner(stderr=stderr))
                self.assertEqual(report["overall"], "FAIL")
                self.assertTrue(all(row["status"] == "FAIL" for row in report["tests"]))

    def test_wrong_png_dimensions_and_corrupt_png_fail(self):
        for mode in ("wrong", "corrupt"):
            with self.subTest(mode=mode):
                report = self.run_matrix(runner=self.runner(png=mode))
                self.assertEqual(report["overall"], "FAIL")
                self.assertTrue(all(not row["png_valid"] for row in report["tests"]))
                self.assertTrue(all(row["screenshot_sha256"] is None for row in report["tests"]))

    def test_run_process_true_exit_and_output_capture(self):
        outcome = matrix.run_process(
            [sys.executable, "-c",
             "import sys; sys.stderr.write('CANOPY_CLASSIC_WINDOW_READY\\n')"],
            timeout_seconds=6, liveness_seconds=0,
        )
        self.assertEqual(outcome.returncode, 0)
        self.assertIn(b"CANOPY_CLASSIC_WINDOW_READY", outcome.stderr)
        self.assertFalse(outcome.timed_out)

    def test_run_process_timeout_is_bounded(self):
        outcome = matrix.run_process(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            timeout_seconds=2, liveness_seconds=0,
        )
        self.assertTrue(outcome.timed_out)
        self.assertIsNotNone(outcome.returncode)

    def test_report_is_json_serializable_and_well_formed(self):
        report = self.run_matrix()
        text = json.dumps(report, sort_keys=True)
        parsed = json.loads(text)
        self.assertEqual(parsed, report)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["kind"], "compiled-qt-classic-runtime-smoke-matrix")
        for key in ("prerequisites", "timeout_seconds", "liveness_seconds",
                    "sizes", "tests", "mechanics_status", "overall", "notes"):
            self.assertIn(key, report)
        for row in report["tests"]:
            for key in ("resolution", "status", "exit_code", "timed_out",
                        "window_ready", "approved_art_verified", "qml_errors",
                        "screenshot", "screenshot_sha256", "png_valid",
                        "command_flags"):
                self.assertIn(key, row)

    def test_main_reports_not_run_without_binary(self):
        output = self.root / "cli-report"
        code = matrix.main([
            "--binary", str(self.root / "missing"),
            "--output-dir", str(output),
            "--timeout", "5",
        ])
        self.assertEqual(code, 2)
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["overall"], "NOT_RUN")
        self.assertFalse(os.path.exists(output / "qt-760x500.png"))


if __name__ == "__main__":
    unittest.main()
