"""Synthetic-only regression tests for the app-isolation contract.

Run from the worktree root with::

    PYTHONPATH=<worktree-root> python -m unittest discover -s tools/lacos_app_isolation -p 'test_*.py'

No real guest, package manager, portal, systemd unit, sandbox or application
is contacted. Fixture bytes live only under scratch/lacos_app_isolation.
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from canopy_features.app_isolation import (  # noqa: E402
    DESCRIBE_ONLY,
    FORBIDDEN_PERMISSIONS,
    MAX_MECHANISMS,
    MAX_PERMISSIONS,
    MECHANISMS,
    MECHANISMS_BY_ECOSYSTEM,
    NOT_RUN,
    REFUSE,
    AppIsolationError,
    AppSpec,
    IsolationRequest,
    SourceClaim,
    canonical_bytes,
    describe,
    evaluate_request,
    valid_mechanism,
)
from synthetic_fixtures import (  # noqa: E402
    FIXTURE_DIR, load_request, sha256_file,
)


def decision(name: str):
    return evaluate_request(load_request(name))


class ContractTest(unittest.TestCase):
    def test_valid_flatpak_is_describe_only(self):
        result = decision("F001_valid_flatpak.json")
        self.assertEqual(result.action, DESCRIBE_ONLY)
        self.assertTrue(result.safe_to_describe)
        self.assertFalse(result.launch_permitted)
        self.assertEqual(result.reasons, ())
        self.assertTrue(result.steps[-1].startswith("REVIEW_REQUIRED"))
        self.assertTrue(all(step.startswith("UPSTREAM ")
                            or step.startswith("REVIEW_REQUIRED")
                            for step in result.steps))

    def test_request_digest_is_canonical(self):
        request = load_request("F001_valid_flatpak.json")
        self.assertEqual(
            request.digest(),
            hashlib.sha256(canonical_bytes(request.to_document())).hexdigest())
        document = decision("F001_valid_flatpak.json").to_document()
        self.assertEqual(document["guest_acceptance"], NOT_RUN)
        self.assertFalse(document["launch_permitted"])

    def test_rootless_podman_is_not_a_complete_sandbox(self):
        result = decision("F002_valid_podman.json")
        self.assertEqual(result.action, DESCRIBE_ONLY)
        self.assertIn("rootless_oci", result.mechanisms)
        self.assertTrue(any("not a complete sandbox" in step
                            for step in result.steps))

    def test_explicit_write_needs_review_ack(self):
        self.assertEqual(decision("F003_valid_write_ack.json").action,
                         DESCRIBE_ONLY)
        refused = decision("F020_write_without_review.json")
        self.assertEqual(refused.action, REFUSE)
        self.assertIn("WRITE_NEEDS_REVIEW", refused.reasons)

    def test_signature_gate(self):
        refused = decision("F010_unsigned.json")
        self.assertIn("SIGNATURE_NOT_VERIFIED", refused.reasons)
        self.assertIn("SIGNATURE_UNSUPPORTED", refused.reasons)

    def test_provenance_gate(self):
        refused = decision("F011_foreign_provenance.json")
        self.assertIn("PROVENANCE_UNTRUSTED", refused.reasons)

    def test_core_mutation_refused(self):
        refused = decision("F012_core_mutation.json")
        self.assertIn("CORE_MUTATION_REFUSED", refused.reasons)
        self.assertIn("FORBIDDEN_PERMISSION", refused.reasons)

    def test_duplicate_sandbox_refused(self):
        refused = decision("F013_duplicate_sandbox.json")
        self.assertIn("DUPLICATE_SANDBOX_REFUSED", refused.reasons)
        self.assertIn("MECHANISM_NOT_UPSTREAM", refused.reasons)

    def test_duplicate_service_refused(self):
        self.assertIn("DUPLICATE_SERVICE_REFUSED",
                      decision("F014_duplicate_service.json").reasons)

    def test_no_paid_telemetry_or_accounts(self):
        for name in ("F015_paid_tier.json", "F016_telemetry.json",
                     "F017_account.json"):
            self.assertIn("NON_FOSS_CONDITION", decision(name).reasons)

    def test_host_context_grants_nothing(self):
        self.assertIn("HOST_ONLY_NO_GRANT",
                      decision("F018_host_context.json").reasons)

    def test_real_guest_is_blocked_and_not_run(self):
        result = decision("F019_real_guest.json")
        self.assertEqual(result.action, NOT_RUN)
        self.assertEqual(result.steps, ())
        self.assertIn("REAL_GUEST_BLOCKED", result.reasons)
        self.assertIn("GUEST_NOT_RUN", result.reasons)

    def test_unknown_permission_refused(self):
        self.assertIn("PERMISSION_NOT_ALLOWED",
                      decision("F021_unknown_permission.json").reasons)

    def test_source_ecosystem_mismatch_refused(self):
        self.assertIn("SOURCE_ECOSYSTEM_MISMATCH",
                      decision("F022_wrong_ecosystem_source.json").reasons)

    def test_hostile_documents_fail_closed(self):
        for name in ("F024_hostile_duplicate_key.json",
                     "F025_huge_integer.json"):
            with self.assertRaises(AppIsolationError):
                load_request(name)

    def test_wrong_types_fail_closed(self):
        self.assertEqual(evaluate_request("not-a-request").action, REFUSE)
        with self.assertRaises(AppIsolationError):
            AppSpec.from_document({"app_id": "org.example.a",
                                   "ecosystem": "flatpak_flathub",
                                   "access_mode": "read_only",
                                   "permissions": "documents_read"})
        with self.assertRaises(AppIsolationError):
            SourceClaim.from_document({"source_id": "flatpak_flathub",
                                       "provenance": "official-flathub",
                                       "signature": "gpg",
                                       "verified": "true",
                                       "scope": "guest-only"})

    def test_upstream_catalog_has_no_duplicate_stack(self):
        self.assertEqual(set(MECHANISMS), set().union(
            *MECHANISMS_BY_ECOSYSTEM.values()))
        self.assertFalse(any("compositor" in key for key in MECHANISMS))
        self.assertFalse(any("second_" in key for key in MECHANISMS))
        self.assertFalse(valid_mechanism("flatpak_flathub", "own_sandbox"))
        with self.assertRaises(AppIsolationError):
            describe("flatpak_flathub", ("documents_read",), ("own_sandbox",))

    def test_bounds_are_enforced(self):
        with self.assertRaises(AppIsolationError):
            AppSpec.from_document({
                "app_id": "org.example.a", "ecosystem": "flatpak_flathub",
                "access_mode": "read_only",
                "permissions": ["permission_{}".format(i)
                                for i in range(MAX_PERMISSIONS + 1)]})
        with self.assertRaises(AppIsolationError):
            IsolationRequest.from_document(dict(
                load_request("F001_valid_flatpak.json").to_document(),
                mechanisms=["m_{}".format(i)
                            for i in range(MAX_MECHANISMS + 1)]))

    def test_fixture_hashes_match_pins(self):
        lines = (FIXTURE_DIR / "SHA256SUMS").read_text("ascii").splitlines()
        self.assertEqual(len(lines), 19)
        for line in lines:
            digest, name = line.split("  ", 1)
            self.assertEqual(sha256_file(FIXTURE_DIR / name), digest)

    def test_forbidden_set_covers_product_constraints(self):
        for name in ("core_mutation", "privileged", "always_on", "telemetry",
                     "paid_tier", "account_required", "duplicate_sandbox",
                     "duplicate_compositor", "duplicate_service",
                     "unrestricted_network"):
            self.assertIn(name, FORBIDDEN_PERMISSIONS)


if __name__ == "__main__":
    unittest.main()
