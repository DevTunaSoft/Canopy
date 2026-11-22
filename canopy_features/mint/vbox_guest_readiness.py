"""Offline normalizer for EXISTING VirtualBox guest preflight evidence.

Nothing here probes a host, starts a VM, invokes VBoxManage, runs Qt, or
claims a Linux Mint guest acceptance. Callers supply facts already captured
during an earlier VM campaign. This module reduces them to one bounded,
deterministic report in which every acceptance field stays NOT_RUN.

Reuse: guest readiness facts come from the pure, existing
tools.mint_guest_preflight.assess() evaluator. The Mint/Cinnamon/session
checks are not reimplemented here.
"""
from tools import mint_guest_preflight as guest

MAX_TEXT = 120
MAX_MAP_ENTRIES = 64
MAX_MAP_TEXT = 200

POWER_STATES = frozenset({"running", "poweroff", "saved", "paused", "unknown"})
EVIDENCE_KEYS = frozenset({
    "release", "env", "available", "qt_version",
    "vm_name", "power_state", "vboxmanage_available",
})


class EvidenceError(ValueError):
    """Supplied evidence is malformed, oversized or unsafe to normalize."""


def _text(value, label, maximum=MAX_TEXT):
    if (not isinstance(value, str) or not value or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise EvidenceError(f"invalid {label}")
    return value


def _mapping(value, label):
    if not isinstance(value, dict) or len(value) > MAX_MAP_ENTRIES:
        raise EvidenceError(f"invalid {label}")
    for key, item in value.items():
        _text(key, f"{label} key", MAX_MAP_TEXT)
        if not isinstance(item, str) or len(item) > MAX_MAP_TEXT:
            raise EvidenceError(f"invalid {label} value")
    return value


def _available(value):
    if not isinstance(value, dict) or len(value) > MAX_MAP_ENTRIES:
        raise EvidenceError("invalid available")
    for key, item in value.items():
        _text(key, "available key", MAX_MAP_TEXT)
        if type(item) is not bool:
            raise EvidenceError("invalid available value")
    return value


def _qt_version(value):
    if value is None:
        return None
    if (not isinstance(value, str) or not value or len(value) > 40
            or any(not (c.isdigit() or c == ".") for c in value)):
        raise EvidenceError("invalid qt_version")
    return value


def normalize(evidence):
    """Return a bounded, non-acceptance report from already-captured facts."""
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
        raise EvidenceError("unrecognized evidence schema")
    release = _mapping(evidence["release"], "release")
    env = _mapping(evidence["env"], "env")
    available = _available(evidence["available"])
    qt_version = _qt_version(evidence["qt_version"])
    vm_name = _text(evidence["vm_name"], "vm_name")
    power_state = evidence["power_state"]
    if not isinstance(power_state, str) or power_state not in POWER_STATES:
        raise EvidenceError("invalid vm power_state")
    vboxmanage = evidence["vboxmanage_available"]
    if type(vboxmanage) is not bool:
        raise EvidenceError("vboxmanage_available must be boolean")

    # Pure reuse of the existing evaluator: no host or VM access here.
    preflight = guest.assess(release, env, available, qt_version)

    attributable = power_state == "running" and vboxmanage
    blockers = []
    if not vboxmanage:
        blockers.append("VBoxManage unavailable; VM state not verified")
    if power_state != "running":
        blockers.append(f"VM not running (power_state={power_state}); "
                        "guest evidence not attributable to a live VM")
    blockers.extend(f"guest preflight: {item}" for item in preflight["blockers"])

    return {
        "schema_version": 1,
        "kind": "offline-vbox-guest-preflight-normalization",
        "actual_run": False,
        "vboxmanage_invoked": False,
        "vm_started": False,
        "linux_mint_execution_independently_proven": False,
        "mint_guest_acceptance": "NOT_RUN",
        "runtime_functional_test": "NOT_RUN",
        "visual_acceptance": "NOT_RUN",
        "status": "NORMALIZED_NOT_RUN" if not blockers else "BLOCKED",
        "vm_name": vm_name,
        "vm_power_state": power_state,
        "vboxmanage_available": vboxmanage,
        "guest_evidence_attributable_to_live_vm": attributable,
        "preflight": preflight,
        "blockers": blockers,
    }
