"""Offline unit tests for the captured-Qt-log classifier.

All logs are synthetic byte buffers. No Qt binary, X server or Linux Mint
guest is used. These tests validate classification logic only, never a real
desktop session or compiled Qt execution.
"""
import unittest

from canopy_features.mint.qt_log_diagnostics import (
    READY_MARKER,
    Finding,
    LogClassification,
    classify_log,
)


class QtLogDiagnosticsTests(unittest.TestCase):
    def test_healthy_ready_log(self):
        result = classify_log(b"CANOPY_GIO_ENABLED\n" + READY_MARKER.encode() + b"\n")
        self.assertIsInstance(result, LogClassification)
        self.assertEqual(result.severity, "READY")
        self.assertTrue(result.ready)
        self.assertFalse(result.truncated)
        self.assertTrue(all(isinstance(item, Finding) for item in result.findings))
        self.assertNotIn("readiness_missing", result.categories)

    def test_missing_readiness_marker_is_reported(self):
        result = classify_log(b"CANOPY_GIO_ENABLED\nCANOPY_GIO_DISABLED\n")
        self.assertFalse(result.ready)
        self.assertEqual(result.severity, "INCONCLUSIVE")
        self.assertIn("readiness_missing", result.categories)
        marker = [f.marker for f in result.findings if f.category == "readiness_missing"]
        self.assertEqual(marker, [READY_MARKER])

    def test_crash_log_is_classified_as_crash(self):
        log = (
            b"CANOPY_GIO_ENABLED\n"
            b"ASSERT failure in QCoreApplication: \"called recursively\"\n"
            b"Segmentation fault (core dumped)\n"
        )
        result = classify_log(log)
        self.assertEqual(result.severity, "CRASH")
        self.assertIn("crash", result.categories)
        self.assertFalse(result.ready)
        self.assertIn("readiness_missing", result.categories)

    def test_qfatal_crash_variant(self):
        result = classify_log(b"qt.qpa.plugin: Fatal: could not load plugin\n")
        self.assertEqual(result.severity, "CRASH")
        self.assertTrue(any(f.marker == "Fatal:" for f in result.findings))

    def test_warning_log_is_non_fatal_and_keeps_readiness(self):
        log = (
            b"Qt warning: software backend selected\n"
            b"CANOPY_APP_LAUNCH_REJECTED: unknown dock action\n"
            + READY_MARKER.encode() + b"\n"
        )
        result = classify_log(log)
        self.assertEqual(result.severity, "WARNING")
        self.assertEqual(result.categories, frozenset({"warning"}))
        self.assertTrue(result.ready)
        self.assertNotIn("crash", result.categories)
        self.assertNotIn("fatal", result.categories)

    def test_qml_binding_failure_reuses_existing_detector(self):
        log = (
            b"qrc:/Canopy/Classic/Main.qml:180:25: "
            b"Unable to assign [undefined] to QColor\n"
            + READY_MARKER.encode() + b"\n"
        )
        result = classify_log(log)
        self.assertEqual(result.severity, "FATAL")
        self.assertEqual(result.categories, frozenset({"qml_fatal"}))
        self.assertTrue(result.ready)

    def test_reference_error_and_binding_loop_are_fatal(self):
        log = (
            b"qrc:/Main.qml:13: ReferenceError: missingName is not defined\n"
            b"qrc:/Main.qml:20: Binding loop detected for property \"width\"\n"
        )
        result = classify_log(log)
        self.assertEqual(result.severity, "FATAL")
        self.assertEqual(len([f for f in result.findings if f.category == "qml_fatal"]), 2)

    def test_self_test_failure_is_fatal(self):
        result = classify_log(
            b"SELF_TEST_FAIL: original dock artwork failed to load\n"
        )
        self.assertEqual(result.severity, "FATAL")
        self.assertIn("fatal", result.categories)

    def test_truncated_log_without_terminal_newline(self):
        log = (
            b"CANOPY_GIO_ENABLED\n"
            b"SELF_TEST_FAIL: original dock artwork failed to load"
        )
        result = classify_log(log)
        self.assertTrue(result.truncated)
        self.assertEqual(result.severity, "FATAL")
        self.assertIn("truncated", result.categories)
        self.assertIn("readiness_missing", result.categories)
        truncated = [f for f in result.findings if f.category == "truncated"]
        self.assertEqual(len(truncated), 1)
        self.assertIn("dock artwork", truncated[0].line)

    def test_truncated_marker_does_not_count_as_readiness(self):
        result = classify_log(b"CANOPY_CLASSIC_WINDOW_READ")
        self.assertFalse(result.ready)
        self.assertTrue(result.truncated)
        self.assertIn("readiness_missing", result.categories)

    def test_empty_log_is_inconclusive_not_ready(self):
        result = classify_log(b"")
        self.assertEqual(result.severity, "INCONCLUSIVE")
        self.assertFalse(result.ready)
        self.assertFalse(result.truncated)
        self.assertEqual(result.categories, frozenset({"readiness_missing"}))

    def test_bounded_tail_keeps_readiness_and_finding(self):
        # Simulates the bounded 64 KiB tail retained by tools/measure_qt.py.
        prefix = b"x" * 70_000
        log = prefix + b"Binding loop detected for property x\n" + READY_MARKER.encode() + b"\n"
        result = classify_log(log)
        self.assertTrue(result.ready)
        self.assertEqual(result.severity, "FATAL")
        self.assertIn("qml_fatal", result.categories)

    def test_severity_precedence_crash_over_warning(self):
        log = (
            b"Qt warning: software backend selected\n"
            b"qFatal: aborted\n"
            + READY_MARKER.encode() + b"\n"
        )
        result = classify_log(log)
        self.assertEqual(result.severity, "CRASH")
        self.assertTrue(result.ready)

    def test_accepts_bytearray_and_rejects_str(self):
        self.assertEqual(classify_log(bytearray(b"CANOPY_CLASSIC_WINDOW_READY\n")).severity, "READY")
        with self.assertRaises(TypeError):
            classify_log("CANOPY_CLASSIC_WINDOW_READY\n")

    def test_findings_are_immutable(self):
        result = classify_log(
            b"ReferenceError: missingName is not defined\n"
        )
        self.assertIsInstance(result.findings, tuple)
        item = result.findings[0]
        self.assertIsInstance(item, Finding)
        with self.assertRaises(Exception):
            item.line = "mutated"


if __name__ == "__main__":
    unittest.main()
