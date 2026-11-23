"""Offline regression tests: credential-shaped IPC/event payload field names.

The host event bus is the scalar validation boundary for trusted Shell Host
IPC envelopes. Its denylist must reject credential-bearing names in every
spelling, not just a handful of exact whole names, so secrets cannot be
published into dispatch records or bounded JSON diagnostic reports.
Pure Python: no Qt, sockets, timers, threads, files or process launches.
"""
import unittest

from canopy_core.host_events import (
    HostEventError,
    HostEvents,
    _encode_fields,
)


COMPOUND_CREDENTIAL_FIELDS = (
    "user_password", "access_token", "api_key", "session_secret",
    "auth_credential", "private_key_id", "refresh_token",
    "user_passwd", "password_value", "session_cookie",
    "account_apikey", "auth_token_value",
)

SHORT_CREDENTIAL_ALIASES = (
    "pw", "pwd", "pass", "key", "api", "auth", "cookie", "bearer",
    "private", "signature", "cert", "certificate", "accesskey",
)

BENIGN_FIELDS = (
    "title", "count", "ready", "rate", "nothing", "item_count",
    "window_count", "state", "available", "monkey_count",
    "keyboard_layout", "passive_mode", "author_name",
)


class CredentialFieldDenyTests(unittest.TestCase):
    def test_compound_credential_names_are_rejected(self):
        for name in COMPOUND_CREDENTIAL_FIELDS:
            with self.subTest(field=name):
                with self.assertRaises(HostEventError):
                    _encode_fields({name: "SENSITIVE"})

    def test_short_credential_aliases_are_rejected(self):
        for name in SHORT_CREDENTIAL_ALIASES:
            with self.subTest(field=name):
                with self.assertRaises(HostEventError):
                    _encode_fields({name: "SENSITIVE"})

    def test_public_emit_rejects_credential_fields_without_dispatch(self):
        seen = []
        callback = lambda event: seen.append(event)
        bus = HostEvents({"app.catalog.changed": [callback]})
        bus.subscribe("app.catalog.changed", callback)
        for name in ("user_password", "access_token", "api_key"):
            with self.subTest(field=name):
                with self.assertRaises(HostEventError):
                    bus.emit("app.catalog.changed", {name: "SENSITIVE"})
        self.assertEqual(seen, [])
        self.assertEqual(bus.emit("app.catalog.changed", {"count": 1}).delivered, 1)
        self.assertEqual(bus.emit("app.catalog.changed", {"count": 2}).event.sequence, 2)

    def test_exact_forbidden_names_and_unsafe_shapes_still_rejected(self):
        for name in ("token", "secret", "password", "credential", "cookie",
                     "authorization", "private_key", "__proto__",
                     "prototype", "constructor", "A", "1bad"):
            with self.subTest(field=name):
                with self.assertRaises(HostEventError):
                    _encode_fields({name: 1})

    def test_benign_field_names_still_accepted(self):
        for name in BENIGN_FIELDS:
            with self.subTest(field=name):
                self.assertEqual(dict(_encode_fields({name: 1})), {name: 1})
        common = {"title": "Café", "count": 12, "ready": True,
                  "rate": 0.75, "nothing": None}
        self.assertEqual(dict(_encode_fields(common)), common)

    def test_rejection_does_not_mutate_caller_payload_or_echo_name(self):
        marker = "zyx123unique"
        payload = {"user_password_" + marker: "SENSITIVE", "count": 1}
        with self.assertRaises(HostEventError) as caught:
            _encode_fields(payload)
        self.assertNotIn(marker, str(caught.exception))
        self.assertEqual(set(payload), {"user_password_" + marker, "count"})


if __name__ == "__main__":
    unittest.main()
