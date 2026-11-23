"""Regression: credential-handle allowlist names must be refused case-insensitively.

The credential-handle denylist (``_NEVER_ALLOW``) protects names such as
XAUTHORITY that look ordinary but grant access to secrets. On Windows the
process environment is case-insensitive, so a caller-supplied lowercase
variant resolves the same value; the validator must therefore refuse every
case variant, not just the canonical spelling. All marker values below are
synthetic literals, never real credentials.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canopy_features.apps.environment_allowlist import (  # noqa: E402
    EnvironmentAllowlistError, build_environment,
)

HANDLES = ("XAUTHORITY", "SSH_AUTH_SOCK", "SSH_AGENT_PID",
           "GPG_AGENT_INFO", "KRB5CCNAME")


def _variants(name):
    """Deterministic set of case spellings for one denylisted handle."""
    spells = {
        name,
        name.lower(),
        name.upper(),
        name.title(),
        name.swapcase(),
        "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(name)),
    }
    return sorted(spells)


class EnvironmentAllowlistCaseVariantTests(unittest.TestCase):
    def test_every_case_variant_of_credential_handles_is_refused(self):
        # RED on base: lowercase/title/mixed variants of XAUTHORITY,
        # SSH_AGENT_PID, GPG_AGENT_INFO and KRB5CCNAME are copied silently.
        for handle in HANDLES:
            for variant in _variants(handle):
                with self.subTest(handle=handle, variant=variant):
                    with self.assertRaises(EnvironmentAllowlistError):
                        build_environment([variant], {variant: "SYNTHETIC"})

    def test_case_variant_cannot_pull_value_from_case_insensitive_source(self):
        # Simulates Windows os.environ holding the canonical uppercase key
        # while the caller allowlists a lowercase spelling. Refusal must
        # happen at name validation, before any source lookup/copy.
        source = {"XAUTHORITY": "SYNTHETIC_XAUTH_MARKER"}
        for variant in ("xauthority", "Xauthority", "xAUTHORITY"):
            with self.subTest(variant=variant):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment([variant], source)
                self.assertEqual(source, {"XAUTHORITY": "SYNTHETIC_XAUTH_MARKER"})

    def test_benign_lowercase_names_are_still_copied(self):
        # Control: the case-insensitive guard is scoped to the credential
        # handles, not to all allowlist names.
        env = build_environment(["path", "MyVar"],
                                {"path": "/usr/bin", "MyVar": "ok"})
        self.assertEqual(env, {"path": "/usr/bin", "MyVar": "ok"})

    def test_sensitive_name_refusal_is_unchanged_for_case_variants(self):
        # Existing keyword-based filtering remains case-insensitive.
        for name in ("github_token", "GitHub_Token", "sessionsecret"):
            with self.subTest(name=name):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment([name], {name: "SYNTHETIC"})


if __name__ == "__main__":
    unittest.main()
