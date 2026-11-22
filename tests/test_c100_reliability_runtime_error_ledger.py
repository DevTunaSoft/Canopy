"""Offline unit tests for the bounded, redacted runtime fault ledger.

No Mint VM, compositor or compiled Qt binary is executed here. Synthetic
stderr bytes exercise only the Qt diagnostic reuse path.
"""
from pathlib import Path
import unittest

from canopy_features.reliability.runtime_error_ledger import (
    FaultRecord, FaultRecordError, MAX_MESSAGE_BYTES, MAX_RECORDS,
    RuntimeFaultLedger, redact,
)


class RedactionTests(unittest.TestCase):
    def setUp(self):
        self.ledger = RuntimeFaultLedger()

    def test_token_assignment_is_redacted_everywhere(self):
        record = self.ledger.record(
            component="classic-qt", code="auth.failure",
            message="login rejected token=SUPERSECRET123 for user")
        self.assertNotIn("SUPERSECRET123", record.message)
        self.assertNotIn("SUPERSECRET123", repr(record))
        self.assertNotIn("SUPERSECRET123", str(self.ledger.snapshot()))
        self.assertIn("[REDACTED]", record.message)

    def test_bearer_and_password_assignment_are_redacted(self):
        messages = (
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def",
            "password: hunter2; api_key=ABCD1234",
            "PRIVATE-KEY = ssh-rsa-AAAAsecret",
        )
        for message in messages:
            with self.subTest(message=message):
                clean = redact(message)
                self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", clean)
                self.assertNotIn("hunter2", clean)
                self.assertNotIn("ABCD1234", clean)
                self.assertNotIn("ssh-rsa-AAAAsecret", clean)
                self.assertIn("[REDACTED]", clean)

    def test_forbidden_context_keys_are_rejected(self):
        for key in ("token", "Password", "api_key", "authorization", "cookie"):
            with self.subTest(key=key):
                with self.assertRaises(FaultRecordError):
                    self.ledger.record(
                        component="classic-qt", code="auth.failure",
                        message="fault", context={key: "SUPERSECRET"})

    def test_context_string_values_are_redacted(self):
        record = self.ledger.record(
            component="classic-qt", code="launch.failure",
            message="launch failed",
            context={"detail": "password=hunter2 for Files"})
        self.assertNotIn("hunter2", repr(record))
        self.assertEqual(record.fields["detail"],
                         "password=[REDACTED] for Files")


class BoundedLedgerTests(unittest.TestCase):
    def test_record_cap_drops_oldest_without_growth(self):
        ledger = RuntimeFaultLedger(capacity=8)
        for index in range(100):
            ledger.record(component="classic-qt", code="fault",
                          message="fault %d" % index)
        self.assertEqual(ledger.count, 8)
        self.assertLessEqual(ledger.count, ledger.capacity)
        snapshot = ledger.snapshot()
        self.assertEqual([row["sequence"] for row in snapshot],
                         list(range(93, 101)))
        self.assertEqual(snapshot[-1]["message"], "fault 99")

    def test_default_capacity_is_within_global_cap(self):
        ledger = RuntimeFaultLedger()
        self.assertEqual(ledger.capacity, MAX_RECORDS)
        for invalid in (0, -1, MAX_RECORDS + 1, True, 4.0):
            with self.subTest(capacity=invalid):
                with self.assertRaises(FaultRecordError):
                    RuntimeFaultLedger(capacity=invalid)

    def test_message_and_context_text_are_byte_bounded(self):
        ledger = RuntimeFaultLedger()
        record = ledger.record(
            component="classic-qt", code="fault",
            message="M" * 5000,
            context={"detail": "C" * 5000})
        self.assertLessEqual(len(record.message.encode("utf-8")),
                             MAX_MESSAGE_BYTES)
        self.assertLessEqual(
            len(record.fields["detail"].encode("utf-8")), 256)
        self.assertTrue(record.message.endswith("…"))

    def test_redaction_runs_before_truncation(self):
        ledger = RuntimeFaultLedger()
        record = ledger.record(
            component="classic-qt", code="fault",
            message=("A" * 5000) + " token=SUPERSECRET999")
        self.assertNotIn("SUPERSECRET999", repr(record))
        self.assertLessEqual(len(record.message.encode("utf-8")),
                             MAX_MESSAGE_BYTES)

    def test_invalid_inputs_are_rejected_before_append(self):
        ledger = RuntimeFaultLedger()
        bad_calls = (
            dict(component="classic-qt", code="fault", message=123),
            dict(component="classic-qt", code="fault", message="x",
                 severity="fatal"),
            dict(component="bad component!", code="fault", message="x"),
            dict(component="classic-qt", code="", message="x"),
            dict(component="classic-qt", code="fault", message="x",
                 context={"nested": {}}),
            dict(component="classic-qt", code="fault", message="x",
                 context={"value": float("nan")}),
            dict(component="classic-qt", code="fault", message="x",
                 context={str(i): i for i in range(9)}),
            dict(component="classic-qt", code="fault", message="\ud800"),
        )
        for call in bad_calls:
            with self.subTest(call=sorted(call)):
                with self.assertRaises(FaultRecordError):
                    ledger.record(**call)
        self.assertEqual(ledger.count, 0)

    def test_record_is_immutable_and_context_view_is_read_only(self):
        ledger = RuntimeFaultLedger()
        record = ledger.record(component="classic-qt", code="fault",
                               message="x", context={"count": 1})
        self.assertIsInstance(record, FaultRecord)
        with self.assertRaises(Exception):
            record.message = "changed"
        with self.assertRaises(TypeError):
            record.fields["count"] = 2
        record.to_dict()["context"]["count"] = 99
        self.assertEqual(record.fields["count"], 1)


class StructuredOutputTests(unittest.TestCase):
    def test_record_has_stable_schema_and_scalar_context(self):
        ledger = RuntimeFaultLedger()
        record = ledger.record(
            component="classic-qt", code="qml.binding", severity="critical",
            message="binding loop", context={"ready": True, "count": 2})
        row = record.to_dict()
        self.assertEqual(row["schema_version"], 1)
        self.assertEqual(row["sequence"], 1)
        self.assertEqual(row["severity"], "critical")
        self.assertEqual(row["component"], "classic-qt")
        self.assertEqual(row["code"], "qml.binding")
        self.assertEqual(row["context"], {"count": 2, "ready": True})
        self.assertEqual(ledger.snapshot(), (row,))

    def test_ingest_qml_stderr_reuses_detector_and_redacts(self):
        ledger = RuntimeFaultLedger()
        stderr = (
            b'CANOPY_CLASSIC_WINDOW_READY\n'
            b'qrc:/Main.qml:13: ReferenceError: token=SUPERSECRET777 is not defined\n'
            b'qrc:/Main.qml:20: Binding loop detected for property "width"\n'
        )
        records = ledger.ingest_stderr(stderr)
        self.assertEqual(len(records), 2)
        self.assertEqual([row["code"] for row in ledger.snapshot()],
                         ["qml.diagnostic", "qml.diagnostic"])
        self.assertTrue(all(row["severity"] == "critical"
                            for row in ledger.snapshot()))
        self.assertNotIn("SUPERSECRET777", str(ledger.snapshot()))
        self.assertEqual(ledger.count, 2)

    def test_ingest_benign_stderr_adds_no_records(self):
        ledger = RuntimeFaultLedger()
        self.assertEqual(ledger.ingest_stderr(
            b'Qt warning: software backend selected\n'
            b'CANOPY_CLASSIC_WINDOW_READY\n'), ())
        self.assertEqual(ledger.count, 0)

    def test_no_polling_threads_network_or_file_io(self):
        source = (Path(__file__).resolve().parents[1] /
                  "canopy_features/reliability/runtime_error_ledger.py")
        code = source.read_text(encoding="utf-8")
        for banned in ("QTimer", "time.sleep", "Thread(", "import socket",
                       "import subprocess", "asyncio", "open(", "import os"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, code)


if __name__ == "__main__":
    unittest.main()
