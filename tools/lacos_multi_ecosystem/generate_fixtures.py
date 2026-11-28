#!/usr/bin/env python3
"""Regenerate deterministic synthetic fixtures for the multi-ecosystem gate.

This maintainer tool writes only files under
``scratch/lacos_multi_ecosystem/fixtures/``. It never reads a guest, a host
package database, or any unmerged feature branch.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "scratch" / \
    "lacos_multi_ecosystem" / "fixtures"
SNAPSHOT = "capability_snapshot.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, document) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def generate() -> int:
    source = _load(FIXTURES / SNAPSHOT)
    cases = {}

    def add(name: str, code: str, mutate) -> None:
        document = copy.deepcopy(source)
        mutate(document)
        cases[name + ".json"] = code
        _dump(FIXTURES / (name + ".json"), document)

    add("missing_ecosystem", "ECOSYSTEM_COVERAGE_INCOMPLETE",
        lambda d: d["ecosystems"].pop())
    add("unknown_ecosystem", "ECOSYSTEM_UNKNOWN",
        lambda d: d["ecosystems"][0].__setitem__("id", "snap_package"))
    add("duplicate_ecosystem", "ECOSYSTEM_DUPLICATE",
        lambda d: d["ecosystems"][1].__setitem__(
            "id", d["ecosystems"][0]["id"]))
    add("core_mutation_capability", "CAPABILITY_FORBIDDEN",
        lambda d: d["ecosystems"][0]["capabilities"].append("core_mutation"))
    add("privileged_capability", "CAPABILITY_FORBIDDEN",
        lambda d: d["ecosystems"][0]["capabilities"].append("privileged"))
    add("partial_upgrade", "CAPABILITY_FORBIDDEN",
        lambda d: d["ecosystems"][2]["capabilities"].append("partial_upgrade"))
    add("paid_tiers", "POLICY_NO_PAID_TIERS_REQUIRED",
        lambda d: d["policy"].__setitem__("paid_tiers", True))
    add("accounts", "POLICY_ACCOUNTS_FORBIDDEN",
        lambda d: d["policy"].__setitem__("accounts", True))
    add("telemetry", "POLICY_TELEMETRY_FORBIDDEN",
        lambda d: d["policy"].__setitem__("telemetry", True))
    add("duplicate_services", "POLICY_DUPLICATE_SERVICE_FORBIDDEN",
        lambda d: d["policy"].__setitem__("duplicate_always_on_services", True))
    add("foreign_repo_mixing", "POLICY_FOREIGN_REPO_REQUIRED",
        lambda d: d["policy"].__setitem__("foreign_host_repo_mixing", True))
    add("runtime_by_default", "POLICY_RUNTIME_DEFAULT_FORBIDDEN",
        lambda d: d["policy"].__setitem__("runtime_installed_by_default", True))
    add("unsigned_source", "SOURCE_UNVERIFIED",
        lambda d: d["ecosystems"][0]["sources"][0].__setitem__("verified", False))
    add("runtime_scope_source", "SOURCE_SCOPE_INVALID",
        lambda d: d["ecosystems"][0]["sources"][0].__setitem__(
            "scope", "verified-runtime"))
    add("wrong_provenance", "PROVENANCE_INVALID",
        lambda d: d["ecosystems"][0]["sources"][0].__setitem__(
            "provenance", "third-party"))
    add("atomic_gate_incomplete", "ATOMIC_CONTRACT_INCOMPLETE",
        lambda d: d["contracts"]["atomic_updates"].__setitem__(
            "signature_ok", False))
    add("backup_rollback_in_flight", "BACKUP_CONTRACT_INCOMPLETE",
        lambda d: d["contracts"]["backup_recovery"].__setitem__(
            "rollback_clear", False))
    add("isolation_duplicate_stack", "ISOLATION_CONTRACT_INCOMPLETE",
        lambda d: d["contracts"]["app_isolation"].__setitem__(
            "no_duplicate_stack", False))
    add("handoff_executed", "HANDOFF_EXECUTED_FORBIDDEN",
        lambda d: d["contracts"]["atomic_updates"].__setitem__(
            "handoff_executed", True))
    add("promotion_performed", "PROMOTION_FORBIDDEN",
        lambda d: d["contracts"]["backup_recovery"].__setitem__(
            "promotion_performed", True))
    add("launch_permitted", "LAUNCH_PERMITTED_FORBIDDEN",
        lambda d: d["contracts"]["app_isolation"].__setitem__(
            "launch_permitted", True))
    add("source_pin_mismatch", "SOURCE_PIN_INVALID",
        lambda d: d["source_pins"].__setitem__(
            "lacos_sources:capability_manifest.py", "0" * 64))
    add("source_head_mismatch", "SOURCE_HEAD_INVALID",
        lambda d: d["source_heads"].__setitem__("lacos_sources", "0" * 40))
    add("real_guest_claim", "EVIDENCE_LABELS_INVALID",
        lambda d: d["evidence_labels"].__setitem__(1, "NATIVE RUNTIME"))
    add("top_extra_field", "TOP_FIELDS_INVALID",
        lambda d: d.__setitem__("guest_acceptance", "ACCEPTED"))
    add("capabilities_string", "CAPABILITIES_INVALID",
        lambda d: d["ecosystems"][0].__setitem__("capabilities", "search"))
    add("runtime_contract_claim", "SOURCE_CONTRACT_INVALID",
        lambda d: d["contracts"]["sources"].__setitem__(
            "signature_status", "VERIFIED"))

    cases["raw_duplicate_key.json"] = "DUPLICATE_JSON_KEY"
    (FIXTURES / "raw_duplicate_key.json").write_text(
        '{"schema_version": 1,\n"schema_version": 1,\n'
        '"evidence_labels": ["STATIC SOURCE ONLY", "SYNTHETIC"]}\n',
        encoding="utf-8", newline="\n")
    cases["raw_huge_integer.json"] = "INPUT_OUT_OF_BOUNDS"
    (FIXTURES / "raw_huge_integer.json").write_text(
        '{"schema_version": ' + "9" * 5000 + '}\n',
        encoding="utf-8", newline="\n")
    _dump(FIXTURES / "negative_cases.json", cases)
    print(f"GENERATE\tfixtures={len(cases) + 1}\tnegatives={len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(generate())
