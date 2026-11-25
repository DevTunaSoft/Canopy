"""Offline unit tests for versioned, bounded trusted-shell IPC validation.

No real IPC, socket, Qt process or Linux Mint session is exercised here.
"""
from pathlib import Path
import unittest

from canopy_core.host_events import MAX_VALUE_BYTES, PROTOCOL_VERSION
from canopy_features.security.ipc_message_schema import (
    IpcMessage, IpcSchemaError, MAX_TARGETS, SCHEMA_VERSION,
    validate_ipc_message,
)


def envelope(**overrides):
    message = {
        "version": SCHEMA_VERSION,
        "topic": "app.catalog.changed",
        "sequence": 3,
        "payload": {"item_count": 4, "available": True},
    }
    message.update(overrides)
    return message


class IpcMessageSchemaTests(unittest.TestCase):
    def test_valid_envelope_is_immutable_and_canonical(self):
        payload = {"item_count": 4, "available": True}
        message = envelope(payload=payload, targets=["shell.modern", "shell.classic"])
        parsed = validate_ipc_message(message)
        self.assertIsInstance(parsed, IpcMessage)
        self.assertEqual((parsed.version, parsed.topic, parsed.sequence),
                         (SCHEMA_VERSION, "app.catalog.changed", 3))
        self.assertEqual(parsed.fields,
                         (("available", True), ("item_count", 4)))
        self.assertEqual(parsed.targets, ("shell.classic", "shell.modern"))
        self.assertEqual(parsed.payload["item_count"], 4)
        with self.assertRaises(TypeError):
            parsed.payload["item_count"] = 9
        payload["item_count"] = 99
        self.assertEqual(parsed.payload["item_count"], 4)

    def test_schema_version_is_tied_to_host_protocol(self):
        self.assertEqual(SCHEMA_VERSION, PROTOCOL_VERSION)

    def test_unknown_or_noninteger_schema_version_rejected(self):
        for version in (0, 2, 99, True, "1", None):
            with self.subTest(version=version):
                with self.assertRaisesRegex(IpcSchemaError, "version"):
                    validate_ipc_message(envelope(version=version))

    def test_unknown_topic_or_extra_or_missing_envelope_key_rejected(self):
        bad = [
            envelope(topic="app.unknown"),
            envelope(topic="APP.CATALOG.CHANGED"),
            envelope(topic=42),
            envelope(unexpected=1),
            envelope(),
        ]
        bad[-1].pop("payload")
        for message in bad:
            with self.subTest(message=repr(sorted(message))):
                with self.assertRaises(IpcSchemaError):
                    validate_ipc_message(message)

    def test_sequence_bounds_and_types_rejected(self):
        for sequence in (-1, True, 1_000_000_001, "3", None):
            with self.subTest(sequence=sequence):
                with self.assertRaisesRegex(IpcSchemaError, "sequence"):
                    validate_ipc_message(envelope(sequence=sequence))

    def test_giant_collections_rejected_without_traversal(self):
        giant = [
            envelope(payload=dict.fromkeys(range(100_000), 1)),
            envelope(payload={"items": list(range(100_000))}),
            envelope(targets=["shell.classic"] * 100_000),
        ]
        for message in giant:
            with self.subTest(kind="giant-collection"):
                with self.assertRaises(IpcSchemaError):
                    validate_ipc_message(message)

    def test_target_collection_bounds_and_content(self):
        self.assertEqual(validate_ipc_message(envelope(targets=[])).targets, ())
        for targets in (
            ["shell.classic"] * (MAX_TARGETS + 1),
            ["Shell.Classic"], ["bad target"], [b"shell.classic"], [42],
            "shell.classic", {"shell.classic": 1}, None,
        ):
            with self.subTest(targets=repr(targets)[:40]):
                with self.assertRaises(IpcSchemaError):
                    validate_ipc_message(envelope(targets=targets))

    def test_payload_reuses_host_scalar_and_secret_rules(self):
        for payload in (
            {"token": "x"}, {"__proto__": 1}, {"nested": {}},
            {"title": "a" * (MAX_VALUE_BYTES + 1)},
            {"rate": float("nan")}, {str(i): i for i in range(9)},
        ):
            with self.subTest(payload=repr(payload)[:40]):
                with self.assertRaisesRegex(IpcSchemaError, "payload"):
                    validate_ipc_message(envelope(payload=payload))

    def test_module_has_no_polling_service_or_io_hooks(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/security/ipc_message_schema.py").read_text()
        for forbidden in ("QTimer", "asyncio", "subprocess", "import socket",
                          "Thread(", "time.sleep", "importlib", "open("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
