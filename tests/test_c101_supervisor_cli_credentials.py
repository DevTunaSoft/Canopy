"""Regression tests for fail-closed credential argument handling (SYNTHETIC)."""
import json
import os
import sqlite3
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

    def test_db_blob_value_fails_closed(self):
        database = self.base / "opencode.db"
        connection = sqlite3.connect(database)
        connection.execute("create table credential (integration_id text, active integer, value)")
        connection.execute(
            "insert into credential values ('opencode', 1, ?)",
            (sqlite3.Binary(('{"access":"' + PLACEHOLDER + '"}').encode()),),
        )
        connection.commit()
        connection.close()
        with self.assertRaises(credentials.CredentialError):
            credentials.get_opencode_api_key(data_home=self.base)

    def test_oversized_db_value_fails_closed(self):
        database = self.base / "opencode.db"
        connection = sqlite3.connect(database)
        connection.execute("create table credential (integration_id text, active integer, value)")
        payload = json.dumps({"access": PLACEHOLDER, "pad": "x" * 70000})
        connection.execute("insert into credential values ('opencode', 1, ?)", (payload,))
        connection.commit()
        connection.close()
        with self.assertRaises(credentials.CredentialError):
            credentials.get_opencode_api_key(data_home=self.base)

    def test_oversized_auth_json_fails_closed(self):
        payload = json.dumps({
            "opencode": {"access": PLACEHOLDER},
            "pad": "x" * 300000,
        })
        (self.base / "auth.json").write_text(payload, encoding="utf-8")
        with self.assertRaises(credentials.CredentialError):
            credentials.get_opencode_api_key(data_home=self.base)

    def test_oversized_config_fails_closed(self):
        (self.base / "config.json").write_text(
            json.dumps({"pad": "x" * 300000}), encoding="utf-8")
        with self.assertRaises(ValueError):
            cli.load_config(self.base)


if __name__ == "__main__":
    unittest.main()
