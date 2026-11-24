"""Regression tests for fail-closed credential argument handling (SYNTHETIC)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from canopy_supervisor import cli, credentials

PLACEHOLDER = "INERT_PLACEHOLDER"


class CredentialArgumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        saved = os.environ.pop("OPENCODE_API_KEY", None)
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "OPENCODE_API_KEY", saved)

    def test_non_string_explicit_credential_fails_closed(self):
        with self.assertRaises(credentials.CredentialError) as caught:
            credentials.get_opencode_api_key(PLACEHOLDER.encode(), data_home=self.base)
        self.assertNotIn(PLACEHOLDER, str(caught.exception))

    def test_string_explicit_credential_still_accepted(self):
        self.assertEqual(
            credentials.get_opencode_api_key(PLACEHOLDER, data_home=self.base),
            PLACEHOLDER,
        )

    def test_non_string_opencode_exe_fails_closed(self):
        with self.assertRaises(ValueError) as caught:
            cli.resolve_opencode_exe(PLACEHOLDER.encode())
        self.assertNotIn(PLACEHOLDER, str(caught.exception))

    def test_falsy_wrong_type_state_root_fails_closed(self):
        for value in ([], {}, False):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError) as caught:
                    cli._state_root(SimpleNamespace(state_root=value))
                self.assertNotIn(PLACEHOLDER, str(caught.exception))

    def test_wrong_type_data_home_fails_closed(self):
        for value in ([], {}, False, 123):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(credentials.CredentialError) as caught:
                    credentials.get_opencode_api_key(data_home=value)
                self.assertNotIn(PLACEHOLDER, str(caught.exception))

    def test_auth_json_prefers_opencode_provider(self):
        (self.base / "auth.json").write_text(json.dumps({
            "other": {"access": "INERT_OTHER"},
            "opencode": {"access": PLACEHOLDER},
        }), encoding="utf-8")
        self.assertEqual(
            credentials.get_opencode_api_key(data_home=self.base),
            PLACEHOLDER,
        )

    def test_auth_json_never_falls_back_to_other_provider(self):
        (self.base / "auth.json").write_text(json.dumps({
            "opencode": {"access": 12345},
            "other": {"access": PLACEHOLDER},
        }), encoding="utf-8")
        with self.assertRaises(credentials.CredentialError):
            credentials.get_opencode_api_key(data_home=self.base)

    def test_auth_json_without_opencode_provider_fails_closed(self):
        (self.base / "auth.json").write_text(json.dumps({
            "other": {"access": PLACEHOLDER},
        }), encoding="utf-8")
        with self.assertRaises(credentials.CredentialError):
            credentials.get_opencode_api_key(data_home=self.base)


if __name__ == "__main__":
    unittest.main()
