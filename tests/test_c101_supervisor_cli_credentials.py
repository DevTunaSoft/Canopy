"""Regression tests for fail-closed credential argument handling (SYNTHETIC)."""
import os
import tempfile
import unittest
from pathlib import Path

from canopy_supervisor import credentials

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


if __name__ == "__main__":
    unittest.main()
