"""Unit tests for the bounded LacOS multi-ecosystem capability map.

These tests intentionally live under the owned tools directory because tests/
is outside this change's ownership. Foundation CI discovery is NOT_RUN here.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scratch" / "lacos_multi_ecosystem" / "fixtures"
SNAPSHOT = FIXTURES / "capability_snapshot.json"

from canopy_features.multi_ecosystem import (  # noqa: E402
    CANONICAL_ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    MUTATING_CAPABILITIES,
    READ_ONLY_CAPABILITIES,
    SOURCE_HEADS,
    SOURCE_SHA256,
    MultiEcosystemError,
    build_capability_map,
    reject_duplicate_keys,
    view_dict,
)


def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"),
                      object_pairs_hook=reject_duplicate_keys)


class MultiEcosystemContractTests(unittest.TestCase):
    def setUp(self):
        self.view = build_capability_map(snapshot())

    def test_five_canonical_ecosystems(self):
        self.assertEqual(
            tuple(item.id for item in self.view.ecosystems),
            CANONICAL_ECOSYSTEM_IDS)

    def test_capability_coverage_and_classification(self):
        self.assertEqual(self.view.capability_count, 27)
        for item in self.view.ecosystems:
            for entry in item.capabilities:
                if entry.capability in READ_ONLY_CAPABILITIES:
                    self.assertEqual(entry.access, "read_only")
                    self.assertEqual(entry.status, "READ_ONLY_DECLARED")
                else:
                    self.assertIn(entry.capability, MUTATING_CAPABILITIES)
                    self.assertEqual(entry.access, "mutating")
                    self.assertEqual(entry.status, "DESCRIBE_ONLY")

    def test_no_grants_or_operational_runtime(self):
        self.assertEqual(dict(self.view.grants), {})
        self.assertFalse(self.view.launch_permitted)
        self.assertEqual(self.view.guest_acceptance, "NOT_RUN")
        self.assertEqual(dict(self.view.real_guest),
                         {"status": "BLOCKED", "gate": "NOT_RUN"})
        self.assertEqual(self.view.runtime, "BLOCKED_NOT_RUN")

    def test_synthetic_evidence_and_source_pins(self):
        self.assertEqual(list(self.view.evidence_labels),
                         ["STATIC SOURCE ONLY", "SYNTHETIC"])
        self.assertEqual(dict(self.view.source_pins), SOURCE_SHA256)
        self.assertEqual(dict(self.view.source_heads), SOURCE_HEADS)

    def test_deterministic_digest(self):
        again = build_capability_map(snapshot())
        self.assertEqual(self.view.digest, again.digest)
        self.assertEqual(view_dict(self.view), view_dict(again))

    def test_immutable_view(self):
        with self.assertRaises(Exception):
            self.view.ecosystems[0].capabilities[0].label = "mutated"
        with self.assertRaises(Exception):
            self.view.policy["paid_tiers"] = True

    def test_forbidden_capability_vocabulary(self):
        for name in ("core_mutation", "host_repo_mixing", "partial_upgrade",
                     "privileged", "telemetry", "paid_tier", "always_on",
                     "accounts", "duplicate_service"):
            self.assertIn(name, FORBIDDEN_CAPABILITIES)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(MultiEcosystemError) as ctx:
            json.loads('{"schema_version": 1, "schema_version": 1}',
                       object_pairs_hook=reject_duplicate_keys)
        self.assertEqual(ctx.exception.code, "DUPLICATE_JSON_KEY")

    def test_extra_top_field_rejected(self):
        document = snapshot()
        document["guest_acceptance"] = "ACCEPTED"
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "TOP_FIELDS_INVALID")

    def test_missing_ecosystem_rejected(self):
        document = snapshot()
        document["ecosystems"].pop()
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "ECOSYSTEM_COVERAGE_INCOMPLETE")

    def test_unknown_ecosystem_rejected(self):
        document = snapshot()
        document["ecosystems"][0]["id"] = "snap_package"
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "ECOSYSTEM_UNKNOWN")

    def test_core_mutation_capability_rejected(self):
        document = snapshot()
        document["ecosystems"][0]["capabilities"].append("core_mutation")
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "CAPABILITY_FORBIDDEN")

    def test_paid_tiers_rejected(self):
        document = snapshot()
        document["policy"]["paid_tiers"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "POLICY_NO_PAID_TIERS_REQUIRED")

    def test_accounts_rejected(self):
        document = snapshot()
        document["policy"]["accounts"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "POLICY_ACCOUNTS_FORBIDDEN")

    def test_telemetry_rejected(self):
        document = snapshot()
        document["policy"]["telemetry"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "POLICY_TELEMETRY_FORBIDDEN")

    def test_duplicate_service_rejected(self):
        document = snapshot()
        document["policy"]["duplicate_always_on_services"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code,
                         "POLICY_DUPLICATE_SERVICE_FORBIDDEN")

    def test_foreign_repo_rejected(self):
        document = snapshot()
        document["policy"]["foreign_host_repo_mixing"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "POLICY_FOREIGN_REPO_REQUIRED")

    def test_runtime_by_default_rejected(self):
        document = snapshot()
        document["policy"]["runtime_installed_by_default"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code,
                         "POLICY_RUNTIME_DEFAULT_FORBIDDEN")

    def test_unverified_source_rejected(self):
        document = snapshot()
        document["ecosystems"][0]["sources"][0]["verified"] = False
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "SOURCE_UNVERIFIED")

    def test_atomic_gate_blocks_mutating_capabilities(self):
        document = snapshot()
        document["contracts"]["atomic_updates"]["signature_ok"] = False
        result = build_capability_map(document)
        self.assertFalse(result.contract_gates_ok)
        for item in result.ecosystems:
            for entry in item.capabilities:
                if entry.access == "mutating":
                    self.assertEqual(entry.status, "BLOCKED_CONTRACT")
                    self.assertIn("ATOMIC_CONTRACT_INCOMPLETE", entry.reasons)

    def test_backup_rollback_blocks_mutating_capabilities(self):
        document = snapshot()
        document["contracts"]["backup_recovery"]["rollback_clear"] = False
        result = build_capability_map(document)
        for item in result.ecosystems:
            for entry in item.capabilities:
                if entry.access == "mutating":
                    self.assertIn("BACKUP_CONTRACT_INCOMPLETE", entry.reasons)

    def test_isolation_duplicate_stack_blocks_mutating_capabilities(self):
        document = snapshot()
        document["contracts"]["app_isolation"]["no_duplicate_stack"] = False
        result = build_capability_map(document)
        for item in result.ecosystems:
            for entry in item.capabilities:
                if entry.access == "mutating":
                    self.assertIn("ISOLATION_CONTRACT_INCOMPLETE",
                                  entry.reasons)

    def test_real_guest_claim_rejected(self):
        document = snapshot()
        document["evidence_labels"][1] = "NATIVE RUNTIME"
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "EVIDENCE_LABELS_INVALID")

    def test_source_pin_mismatch_rejected(self):
        document = snapshot()
        document["source_pins"]["lacos_sources:capability_manifest.py"] = "0" * 64
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "SOURCE_PIN_INVALID")

    def test_handoff_execution_claim_rejected(self):
        document = snapshot()
        document["contracts"]["atomic_updates"]["handoff_executed"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "HANDOFF_EXECUTED_FORBIDDEN")

    def test_restore_promotion_claim_rejected(self):
        document = snapshot()
        document["contracts"]["backup_recovery"]["promotion_performed"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "PROMOTION_FORBIDDEN")

    def test_launch_permitted_claim_rejected(self):
        document = snapshot()
        document["contracts"]["app_isolation"]["launch_permitted"] = True
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "LAUNCH_PERMITTED_FORBIDDEN")

    def test_string_capabilities_rejected(self):
        document = snapshot()
        document["ecosystems"][0]["capabilities"] = "search"
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "CAPABILITIES_INVALID")

    def test_unordered_container_rejected(self):
        document = snapshot()
        document["ecosystems"][0]["capabilities"] = {"search"}
        with self.assertRaises(MultiEcosystemError) as ctx:
            build_capability_map(document)
        self.assertEqual(ctx.exception.code, "CANONICAL_JSON_INVALID")


if __name__ == "__main__":
    unittest.main()
