"""Bounded, read-only-first capability map over the five LacOS P0 ecosystems.

The map consumes a *synthetic declaration snapshot*: five ecosystem manifests
plus the atomic-update, backup/recovery and application-isolation contract
facts. It produces inert descriptions only. It never grants a capability,
executes a handoff step, launches an app, contacts a guest, or promotes a
staged file. Real-guest work stays BLOCKED / NOT_RUN.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Mapping, Tuple

from .contract import (
    ALLOWED_PROVENANCE,
    ALLOWED_SIGNATURES,
    CANONICAL_ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    FORBIDDEN_EVIDENCE_LABELS,
    KNOWN_CAPABILITIES,
    MAX_CAPABILITIES,
    MAX_ECOSYSTEMS,
    MAX_SOURCES,
    MUTATING_CAPABILITIES,
    READ_ONLY_CAPABILITIES,
    REQUIRED_EVIDENCE_LABELS,
    SOURCE_HEADS,
    SOURCE_SHA256,
    MultiEcosystemError,
    bounded_text,
    canonical_json,
    check_bounds,
    exact_bool,
    exact_int,
    exact_keys,
    hex40,
    hex64,
)

_TOP_KEYS = ("schema_version", "evidence_labels", "policy", "ecosystems",
             "contracts", "source_pins", "source_heads")
_POLICY_KEYS = ("no_core_mutation", "foreign_host_repo_mixing", "paid_tiers",
                "telemetry", "duplicate_always_on_services", "accounts",
                "on_demand_only", "runtime_installed_by_default")
_ECOSYSTEM_KEYS = ("id", "enabled", "on_demand", "runtime_installed_by_default",
                   "capabilities", "sources", "isolation")
_SOURCE_KEYS = ("id", "provenance", "signature", "verified", "scope")
_CONTRACT_KEYS = ("sources", "atomic_updates", "backup_recovery",
                  "app_isolation")
_SOURCE_CONTRACT_KEYS = ("context", "declaration_status", "signature_status",
                         "guest_acceptance", "host_probe")
_ATOMIC_KEYS = ("signature_ok", "digest_match", "checkpoint_retained",
                "pinned", "core_immutable", "no_layered_mutation",
                "activation_deferred", "stock_plasma_fallback",
                "handoff_executed")
_BACKUP_KEYS = ("plan_sealed", "checkpoint_present", "rollback_clear",
                "owner_data_scoped", "restore_review_required",
                "integrity_verified", "promotion_performed")
_ISOLATION_KEYS = ("upstream_only", "no_duplicate_stack", "read_only_default",
                   "explicit_write_review", "no_core_mutation",
                   "no_paid_tiers", "no_telemetry", "no_accounts",
                   "guest_acceptance", "launch_permitted")

_ATOMIC_GATES = tuple(key for key in _ATOMIC_KEYS if key != "handoff_executed")
_BACKUP_GATES = tuple(key for key in _BACKUP_KEYS if key != "promotion_performed")
_ISOLATION_GATES = tuple(key for key in _ISOLATION_KEYS
                         if key not in ("guest_acceptance", "launch_permitted"))

_READ_ONLY_REASONS = ("DECLARATION_READ_ONLY", "SOURCE_CONTRACT_DECLARED")
_DESCRIBE_REASONS = (
    "DECLARATION_READ_ONLY_FIRST", "ATOMIC_HANDOFF_DECLARED",
    "BACKUP_REVIEW_REQUIRED", "ISOLATION_UPSTREAM_DECLARED",
)


@dataclass(frozen=True)
class CapabilityEntry:
    """One ecosystem/capability description; never an operational grant."""

    ecosystem: str
    capability: str
    access: str
    status: str
    reasons: Tuple[str, ...]
    contract_refs: Tuple[str, ...]


@dataclass(frozen=True)
class EcosystemEntry:
    """One declared P0 ecosystem with inert capability descriptions."""

    id: str
    source_ids: Tuple[str, ...]
    signature_schemes: Tuple[str, ...]
    isolation: str
    capabilities: Tuple[CapabilityEntry, ...]
    status: str


@dataclass(frozen=True)
class CapabilityMap:
    """Immutable read-only-first capability map; grants are always empty."""

    schema_version: int
    status: str
    evidence_labels: Tuple[str, ...]
    policy: Mapping[str, bool]
    contracts: Mapping[str, str]
    source_pins: Mapping[str, str]
    source_heads: Mapping[str, str]
    ecosystems: Tuple[EcosystemEntry, ...]
    contract_gates_ok: bool
    digest: str

    @property
    def grants(self) -> Mapping[str, Tuple[str, ...]]:
        return MappingProxyType({})

    @property
    def guest_acceptance(self) -> str:
        return "NOT_RUN"

    @property
    def real_guest(self) -> Mapping[str, str]:
        return MappingProxyType({"status": "BLOCKED", "gate": "NOT_RUN"})

    @property
    def runtime(self) -> str:
        return "BLOCKED_NOT_RUN"

    @property
    def launch_permitted(self) -> bool:
        return False

    @property
    def capability_count(self) -> int:
        return sum(len(item.capabilities) for item in self.ecosystems)


def _payload(view: CapabilityMap) -> dict:
    return {
        "schema_version": view.schema_version,
        "status": view.status,
        "evidence_labels": list(view.evidence_labels),
        "policy": dict(view.policy),
        "contracts": dict(view.contracts),
        "source_pins": dict(view.source_pins),
        "source_heads": dict(view.source_heads),
        "ecosystems": [
            {
                "id": item.id,
                "source_ids": list(item.source_ids),
                "signature_schemes": list(item.signature_schemes),
                "isolation": item.isolation,
                "status": item.status,
                "capabilities": [
                    {
                        "ecosystem": entry.ecosystem,
                        "capability": entry.capability,
                        "access": entry.access,
                        "status": entry.status,
                        "reasons": list(entry.reasons),
                        "contract_refs": list(entry.contract_refs),
                    }
                    for entry in item.capabilities
                ],
            }
            for item in view.ecosystems
        ],
        "contract_gates_ok": view.contract_gates_ok,
        "capability_count": view.capability_count,
        "grants": {},
        "guest_acceptance": view.guest_acceptance,
        "real_guest": dict(view.real_guest),
        "runtime": view.runtime,
        "launch_permitted": view.launch_permitted,
    }


def view_dict(view: CapabilityMap) -> dict:
    """Deterministic plain mapping, including the content digest."""
    result = _payload(view)
    result["digest"] = view.digest
    return result


def _validate_policy(policy) -> Mapping[str, bool]:
    exact_keys(policy, _POLICY_KEYS, "POLICY_FIELDS_INVALID")
    expected = {
        "no_core_mutation": True,
        "foreign_host_repo_mixing": False,
        "paid_tiers": False,
        "telemetry": False,
        "duplicate_always_on_services": False,
        "accounts": False,
        "on_demand_only": True,
        "runtime_installed_by_default": False,
    }
    codes = {
        "no_core_mutation": "POLICY_NO_CORE_MUTATION_REQUIRED",
        "foreign_host_repo_mixing": "POLICY_FOREIGN_REPO_REQUIRED",
        "paid_tiers": "POLICY_NO_PAID_TIERS_REQUIRED",
        "telemetry": "POLICY_TELEMETRY_FORBIDDEN",
        "duplicate_always_on_services": "POLICY_DUPLICATE_SERVICE_FORBIDDEN",
        "accounts": "POLICY_ACCOUNTS_FORBIDDEN",
        "on_demand_only": "POLICY_ON_DEMAND_REQUIRED",
        "runtime_installed_by_default": "POLICY_RUNTIME_DEFAULT_FORBIDDEN",
    }
    result = {}
    for key, value in expected.items():
        actual = exact_bool(policy[key], "POLICY_TYPE_INVALID")
        if actual is not value:
            raise MultiEcosystemError(codes[key])
        result[key] = actual
    return MappingProxyType(result)


def _validate_labels(labels) -> Tuple[str, ...]:
    if type(labels) is not list or len(labels) != len(REQUIRED_EVIDENCE_LABELS):
        raise MultiEcosystemError("EVIDENCE_LABELS_INVALID")
    result = tuple(bounded_text(item, "EVIDENCE_LABELS_INVALID")
                   for item in labels)
    if (set(result) != set(REQUIRED_EVIDENCE_LABELS)
            or set(result) & FORBIDDEN_EVIDENCE_LABELS):
        raise MultiEcosystemError("EVIDENCE_LABELS_INVALID")
    return result


def _validate_pins(pins, heads) -> Tuple[Mapping[str, str], Mapping[str, str]]:
    exact_keys(pins, SOURCE_SHA256, "SOURCE_PINS_INVALID")
    exact_keys(heads, SOURCE_HEADS, "SOURCE_HEADS_INVALID")
    result_pins = {}
    for key, expected in SOURCE_SHA256.items():
        value = hex64(pins[key], "SOURCE_PIN_INVALID")
        if value != expected:
            raise MultiEcosystemError("SOURCE_PIN_INVALID")
        result_pins[key] = value
    result_heads = {}
    for key, expected in SOURCE_HEADS.items():
        value = hex40(heads[key], "SOURCE_HEAD_INVALID")
        if value != expected:
            raise MultiEcosystemError("SOURCE_HEAD_INVALID")
        result_heads[key] = value
    return MappingProxyType(result_pins), MappingProxyType(result_heads)


def _validate_contracts(contracts) -> Tuple[Mapping[str, str], Tuple[str, ...]]:
    exact_keys(contracts, _CONTRACT_KEYS, "CONTRACT_FIELDS_INVALID")
    sources = contracts["sources"]
    exact_keys(sources, _SOURCE_CONTRACT_KEYS, "SOURCE_CONTRACT_FIELDS_INVALID")
    source_expected = {
        "context": "synthetic-guest",
        "declaration_status": "DECLARED",
        "signature_status": "DECLARED_NOT_VERIFIED",
        "guest_acceptance": "NOT_RUN",
        "host_probe": "HOST_ONLY",
    }
    for key, expected in source_expected.items():
        value = bounded_text(sources[key], "SOURCE_CONTRACT_INVALID")
        if value != expected:
            raise MultiEcosystemError("SOURCE_CONTRACT_INVALID")

    atomic = contracts["atomic_updates"]
    exact_keys(atomic, _ATOMIC_KEYS, "ATOMIC_CONTRACT_FIELDS_INVALID")
    if exact_bool(atomic["handoff_executed"], "ATOMIC_TYPE_INVALID"):
        raise MultiEcosystemError("HANDOFF_EXECUTED_FORBIDDEN")
    atomic_ok = all(exact_bool(atomic[key], "ATOMIC_TYPE_INVALID")
                    for key in _ATOMIC_GATES)

    backup = contracts["backup_recovery"]
    exact_keys(backup, _BACKUP_KEYS, "BACKUP_CONTRACT_FIELDS_INVALID")
    if exact_bool(backup["promotion_performed"], "BACKUP_TYPE_INVALID"):
        raise MultiEcosystemError("PROMOTION_FORBIDDEN")
    backup_ok = all(exact_bool(backup[key], "BACKUP_TYPE_INVALID")
                    for key in _BACKUP_GATES)

    isolation = contracts["app_isolation"]
    exact_keys(isolation, _ISOLATION_KEYS, "ISOLATION_CONTRACT_FIELDS_INVALID")
    if bounded_text(isolation["guest_acceptance"],
                    "ISOLATION_TYPE_INVALID") != "NOT_RUN":
        raise MultiEcosystemError("REAL_GUEST_BLOCKED")
    if exact_bool(isolation["launch_permitted"], "ISOLATION_TYPE_INVALID"):
        raise MultiEcosystemError("LAUNCH_PERMITTED_FORBIDDEN")
    isolation_ok = all(exact_bool(isolation[key], "ISOLATION_TYPE_INVALID")
                       for key in _ISOLATION_GATES)

    summary = MappingProxyType({
        "sources": "DECLARED_SYNTHETIC",
        "atomic_updates": ("READY_FOR_HANDOFF_DECLARED" if atomic_ok
                           else "CONTRACT_GATE_MISSING"),
        "backup_recovery": ("SEALED_REVIEW_REQUIRED_DECLARED" if backup_ok
                            else "CONTRACT_GATE_MISSING"),
        "app_isolation": ("UPSTREAM_DESCRIBE_ONLY_DECLARED" if isolation_ok
                          else "CONTRACT_GATE_MISSING"),
    })
    return summary, (atomic_ok, backup_ok, isolation_ok)


def _validate_ecosystems(ecosystems, gates) -> Tuple[EcosystemEntry, ...]:
    if type(ecosystems) is not list or len(ecosystems) > MAX_ECOSYSTEMS:
        raise MultiEcosystemError("ECOSYSTEMS_INVALID")
    seen = set()
    result = []
    for raw in ecosystems:
        exact_keys(raw, _ECOSYSTEM_KEYS, "ECOSYSTEM_FIELDS_INVALID")
        ecosystem_id = bounded_text(raw["id"], "ECOSYSTEM_ID_INVALID")
        if ecosystem_id not in CANONICAL_ECOSYSTEM_IDS:
            raise MultiEcosystemError("ECOSYSTEM_UNKNOWN")
        if ecosystem_id in seen:
            raise MultiEcosystemError("ECOSYSTEM_DUPLICATE")
        seen.add(ecosystem_id)
        if exact_bool(raw["enabled"], "ECOSYSTEM_TYPE_INVALID") is not True:
            raise MultiEcosystemError("ECOSYSTEM_DISABLED")
        if exact_bool(raw["on_demand"], "ECOSYSTEM_TYPE_INVALID") is not True:
            raise MultiEcosystemError("POLICY_ON_DEMAND_REQUIRED")
        if exact_bool(raw["runtime_installed_by_default"],
                      "ECOSYSTEM_TYPE_INVALID"):
            raise MultiEcosystemError("POLICY_RUNTIME_DEFAULT_FORBIDDEN")

        caps = raw["capabilities"]
        if type(caps) is not list or not 1 <= len(caps) <= MAX_CAPABILITIES:
            raise MultiEcosystemError("CAPABILITIES_INVALID")
        cap_names = []
        for cap in caps:
            name = bounded_text(cap, "CAPABILITY_INVALID")
            if name in FORBIDDEN_CAPABILITIES:
                raise MultiEcosystemError("CAPABILITY_FORBIDDEN")
            if name not in KNOWN_CAPABILITIES:
                raise MultiEcosystemError("CAPABILITY_UNKNOWN")
            if name in cap_names:
                raise MultiEcosystemError("CAPABILITY_DUPLICATE")
            cap_names.append(name)

        sources = raw["sources"]
        if type(sources) is not list or not 1 <= len(sources) <= MAX_SOURCES:
            raise MultiEcosystemError("SOURCES_INVALID")
        source_ids = []
        signatures = []
        for source in sources:
            exact_keys(source, _SOURCE_KEYS, "SOURCE_FIELDS_INVALID")
            source_id = bounded_text(source["id"], "SOURCE_ID_INVALID")
            if source_id in source_ids:
                raise MultiEcosystemError("SOURCE_ID_DUPLICATE")
            source_ids.append(source_id)
            provenance = bounded_text(source["provenance"], "PROVENANCE_INVALID")
            signature = bounded_text(source["signature"], "SIGNATURE_INVALID")
            if provenance not in ALLOWED_PROVENANCE[ecosystem_id]:
                raise MultiEcosystemError("PROVENANCE_INVALID")
            if signature not in ALLOWED_SIGNATURES[ecosystem_id]:
                raise MultiEcosystemError("SIGNATURE_INVALID")
            if exact_bool(source["verified"], "SOURCE_TYPE_INVALID") is not True:
                raise MultiEcosystemError("SOURCE_UNVERIFIED")
            if bounded_text(source["scope"], "SOURCE_SCOPE_INVALID") != "guest-only":
                raise MultiEcosystemError("SOURCE_SCOPE_INVALID")
            signatures.append(signature)

        isolation = bounded_text(raw["isolation"], "ISOLATION_INVALID")
        if len(isolation) < 40 or "no " not in isolation.lower():
            raise MultiEcosystemError("ISOLATION_INVALID")

        entries = []
        for name in sorted(cap_names):
            read_only = name in READ_ONLY_CAPABILITIES
            if read_only:
                status = "READ_ONLY_DECLARED"
                reasons = _READ_ONLY_REASONS
                refs = ("sources",)
            else:
                failed = []
                if not gates[0]:
                    failed.append("ATOMIC_CONTRACT_INCOMPLETE")
                if not gates[1]:
                    failed.append("BACKUP_CONTRACT_INCOMPLETE")
                if not gates[2]:
                    failed.append("ISOLATION_CONTRACT_INCOMPLETE")
                status = "BLOCKED_CONTRACT" if failed else "DESCRIBE_ONLY"
                reasons = tuple(failed) if failed else _DESCRIBE_REASONS
                refs = ("sources", "atomic_updates", "backup_recovery",
                        "app_isolation")
            entries.append(CapabilityEntry(
                ecosystem=ecosystem_id, capability=name,
                access="read_only" if read_only else "mutating",
                status=status, reasons=reasons, contract_refs=refs))
        result.append(EcosystemEntry(
            id=ecosystem_id, source_ids=tuple(source_ids),
            signature_schemes=tuple(dict.fromkeys(signatures)),
            isolation=isolation,
            capabilities=tuple(entries),
            status="DECLARED"))

    if seen != frozenset(CANONICAL_ECOSYSTEM_IDS):
        raise MultiEcosystemError("ECOSYSTEM_COVERAGE_INCOMPLETE")
    result.sort(key=lambda item: CANONICAL_ECOSYSTEM_IDS.index(item.id))
    return tuple(result)


def build_capability_map(document) -> CapabilityMap:
    """Evaluate a parsed, bounded synthetic snapshot; fail closed on hostility."""
    check_bounds(document)
    exact_keys(document, _TOP_KEYS, "TOP_FIELDS_INVALID")
    if exact_int(document["schema_version"], "SCHEMA_INVALID") != 1:
        raise MultiEcosystemError("SCHEMA_INVALID")

    labels = _validate_labels(document["evidence_labels"])
    policy = _validate_policy(document["policy"])
    pins, heads = _validate_pins(document["source_pins"],
                                 document["source_heads"])
    contracts, gates = _validate_contracts(document["contracts"])
    ecosystems = _validate_ecosystems(document["ecosystems"], gates)

    view = CapabilityMap(
        schema_version=1,
        status="DECLARED_READ_ONLY_FIRST",
        evidence_labels=labels,
        policy=policy,
        contracts=contracts,
        source_pins=pins,
        source_heads=heads,
        ecosystems=ecosystems,
        contract_gates_ok=all(gates),
        digest="",
    )
    object.__setattr__(view, "digest", hashlib.sha256(
        canonical_json(_payload(view)).encode("utf-8")).hexdigest())
    return view
