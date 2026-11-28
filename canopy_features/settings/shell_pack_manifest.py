"""Bounded first-party Shell Pack definition and synthetic switch ledger.

Data only. This module reads the checked-in Modern pack *manifest* with the
existing offline checker and models prepare/apply/verify/rollback as an
immutable bookkeeping ledger. It never loads or evaluates ``ui/Main.qml``,
starts a process or service, reads a compositor, writes settings, contacts a
network, or changes a desktop session. A ledger is not proof that a real
switch works.

Classic is preserved as a reserved built-in identity; no Classic artwork,
QML, geometry or preference is read or modified here. Every first-party pack
is included at no cost: no paid tier, unlock, subscription, activation,
account, advertisement or mandatory telemetry is represented or accepted.

The on-disk v1 checker reserves ``org.canopy.`` for built-in identities, so
the catalog manifest for Modern uses the non-reserved id
``io.canopy.modern``. The explicit binding below maps it to the reserved
built-in identity ``org.canopy.modern`` without granting extra privileges.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import FrozenSet, Mapping, Optional, Tuple

from tools.check_shell_pack import (
    CAPABILITIES,
    PackValidationError,
    require_real_path_components,
    validate_pack,
)

__all__ = [
    "SCHEMA_VERSION",
    "INCLUDED_TIER",
    "PAID_TIERS",
    "ACTIVATION_REQUIRED",
    "TELEMETRY_ENDPOINTS",
    "MAX_DEFINITIONS",
    "MAX_LEDGER_STEPS",
    "CLASSIC_BUILTIN_ID",
    "MODERN_BUILTIN_ID",
    "MODERN_MANIFEST_ID",
    "MODERN_PACK_DIR",
    "SHARED_CORE_SERVICES",
    "PACK_OWNED_SERVICES",
    "ShellPackManifestError",
    "PackDefinition",
    "InventorySnapshot",
    "SwitchStep",
    "SwitchLedger",
    "load_modern_definition",
    "inventory_snapshot",
    "shared_core_snapshot",
    "prepare_switch",
    "apply_switch",
    "verify_switch",
    "rollback_switch",
    "release_inactive",
]

SCHEMA_VERSION = 1
INCLUDED_TIER = "included"
# Deliberately empty: there is no premium, upgrade or pro path for a pack.
PAID_TIERS = frozenset()
ACTIVATION_REQUIRED = False
TELEMETRY_ENDPOINTS = frozenset()
MAX_DEFINITIONS = 8
MAX_PROBLEM_CHARS = 240
MAX_LEDGER_STEPS = 12
MAX_NOTE_CHARS = 160

CLASSIC_BUILTIN_ID = "org.canopy.classic"
MODERN_BUILTIN_ID = "org.canopy.modern"
MODERN_MANIFEST_ID = "io.canopy.modern"
MODERN_PACK_DIR = Path("tools/shell_packs/modern")
BUILTIN_IDS = frozenset({CLASSIC_BUILTIN_ID, MODERN_BUILTIN_ID})

# The host owns one instance of each. A pack may request a UI affordance but
# may never start a parallel copy of any service below.
SHARED_CORE_SERVICES = frozenset({
    "compositor-session",
    "app-launcher",
    "window-management",
    "notifications",
    "system-status",
    "settings",
    "accessibility",
})
PACK_OWNED_SERVICES = frozenset()

_PHASES = frozenset({
    "ALREADY_ACTIVE", "PREPARED", "APPLIED", "COMMITTED",
    "ROLLED_BACK", "RELEASED",
})
_STEP_NAMES = frozenset({
    "NOOP", "PREPARE", "APPLY", "VERIFY", "ROLLBACK", "RELEASE_INACTIVE",
})


class ShellPackManifestError(ValueError):
    """Invalid first-party binding or illegal switch-ledger transition."""


def _clean(value, label: str, maximum: int) -> str:
    if (type(value) is not str or not value or len(value) > maximum
            or value != value.strip() or not value.isprintable()):
        raise ShellPackManifestError(f"invalid {label}")
    return value


@dataclass(frozen=True)
class PackDefinition:
    """Immutable, data-only definition of one first-party presentation."""

    builtin_id: str
    manifest_id: str
    name: str
    capabilities: FrozenSet[str]
    entrypoint: str
    source: str
    tier: str = INCLUDED_TIER
    owned_services: FrozenSet[str] = PACK_OWNED_SERVICES

    def __post_init__(self):
        if type(self.builtin_id) is not str or self.builtin_id not in BUILTIN_IDS:
            raise ShellPackManifestError("unknown first-party built-in identity")
        if type(self.manifest_id) is not str or not self.manifest_id:
            raise ShellPackManifestError("invalid manifest identity")
        _clean(self.name, "pack name", 80)
        _clean(self.source, "pack source", 120)
        if (not isinstance(self.capabilities, frozenset)
                or not self.capabilities <= CAPABILITIES):
            raise ShellPackManifestError("capabilities must be host affordances")
        if type(self.entrypoint) is not str or len(self.entrypoint) > 120:
            raise ShellPackManifestError("invalid entrypoint label")
        if self.tier != INCLUDED_TIER or PAID_TIERS:
            raise ShellPackManifestError("first-party packs must be free")
        if (ACTIVATION_REQUIRED or TELEMETRY_ENDPOINTS
                or not isinstance(self.owned_services, frozenset)
                or self.owned_services):
            raise ShellPackManifestError("pack cannot own services or telemetry")

    @property
    def free(self) -> bool:
        return self.tier == INCLUDED_TIER and not ACTIVATION_REQUIRED

    def as_dict(self) -> dict:
        return {
            "builtin_id": self.builtin_id,
            "manifest_id": self.manifest_id,
            "name": self.name,
            "capabilities": tuple(sorted(self.capabilities)),
            "entrypoint": self.entrypoint,
            "source": self.source,
            "tier": self.tier,
            "owned_services": tuple(sorted(self.owned_services)),
        }


@dataclass(frozen=True)
class InventorySnapshot:
    """Frozen inventory view. No path is resolved and no code is loaded."""

    definitions: Tuple[PackDefinition, ...]
    problems: Tuple[str, ...] = ()
    checked_manifests: int = 0

    def __post_init__(self):
        if (not isinstance(self.definitions, tuple)
                or len(self.definitions) > MAX_DEFINITIONS):
            raise ShellPackManifestError("inventory exceeds bounded definition set")
        if any(not isinstance(item, PackDefinition) for item in self.definitions):
            raise ShellPackManifestError("inventory entries must be definitions")
        if not isinstance(self.problems, tuple):
            raise ShellPackManifestError("problems must be a tuple")

    def get(self, builtin_id: str) -> Optional[PackDefinition]:
        if type(builtin_id) is not str:
            return None
        return next((item for item in self.definitions
                     if item.builtin_id == builtin_id), None)

    def by_manifest_id(self, manifest_id: str) -> Optional[PackDefinition]:
        if type(manifest_id) is not str:
            return None
        return next((item for item in self.definitions
                     if item.manifest_id == manifest_id), None)

    def as_dict(self) -> dict:
        return {
            "definitions": [item.as_dict() for item in self.definitions],
            "problems": list(self.problems),
            "checked_manifests": self.checked_manifests,
            "paid_tiers": sorted(PAID_TIERS),
            "activation_required": ACTIVATION_REQUIRED,
            "telemetry_endpoints": sorted(TELEMETRY_ENDPOINTS),
        }


@dataclass(frozen=True)
class SwitchStep:
    """One bookkeeping step; performs no action."""

    name: str
    status: str
    note: str = ""

    def __post_init__(self):
        if self.name not in _STEP_NAMES:
            raise ShellPackManifestError("unknown ledger step")
        _clean(self.status, "step status", 40)
        if type(self.note) is not str or len(self.note) > MAX_NOTE_CHARS:
            raise ShellPackManifestError("step note is unbounded")

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "note": self.note}


@dataclass(frozen=True)
class SwitchLedger:
    """Immutable synthetic transition state, with no callables or I/O."""

    from_id: Optional[str]
    target_id: str
    active_id: Optional[str]
    committed_id: Optional[str]
    phase: str
    steps: Tuple[SwitchStep, ...] = ()
    rolled_back: bool = False

    def __post_init__(self):
        if self.phase not in _PHASES:
            raise ShellPackManifestError("unknown ledger phase")
        if not isinstance(self.steps, tuple) or len(self.steps) > MAX_LEDGER_STEPS:
            raise ShellPackManifestError("ledger step count is unbounded")
        if any(not isinstance(step, SwitchStep) for step in self.steps):
            raise ShellPackManifestError("ledger steps must be SwitchStep values")
        if type(self.rolled_back) is not bool:
            raise ShellPackManifestError("rolled_back must be a bool")

    def as_dict(self) -> dict:
        return {
            "from_id": self.from_id,
            "target_id": self.target_id,
            "active_id": self.active_id,
            "committed_id": self.committed_id,
            "phase": self.phase,
            "steps": [step.as_dict() for step in self.steps],
            "rolled_back": self.rolled_back,
            "real_runtime_verified": False,
        }


def _classic_definition() -> PackDefinition:
    """Reserved Classic identity only; approved identity/assets stay untouched."""
    return PackDefinition(
        builtin_id=CLASSIC_BUILTIN_ID,
        manifest_id=CLASSIC_BUILTIN_ID,
        name="Classic",
        capabilities=frozenset(),
        entrypoint="host-owned",
        source="built-in:approved-classic",
    )


def _pack_root(pack_root: Optional[Path]) -> Path:
    root = (Path(pack_root) if pack_root is not None
            else Path(__file__).resolve().parents[2] / MODERN_PACK_DIR)
    require_real_path_components(root, "modern pack root must be a real directory")
    return root


def load_modern_definition(pack_root: Optional[Path] = None) -> PackDefinition:
    """Validate the Modern manifest only; never load or run its QML entrypoint."""
    root = _pack_root(pack_root)
    manifest = validate_pack(root)
    manifest_id = manifest["id"]
    if manifest_id != MODERN_MANIFEST_ID:
        raise ShellPackManifestError("Modern manifest identity is not the bound id")
    capabilities = frozenset(manifest["capabilities"])
    if not capabilities or not capabilities <= CAPABILITIES:
        raise ShellPackManifestError("Modern requests unsupported capabilities")
    return PackDefinition(
        builtin_id=MODERN_BUILTIN_ID,
        manifest_id=manifest_id,
        name=manifest["name"],
        capabilities=capabilities,
        entrypoint=manifest["entrypoint"],
        source=str(MODERN_PACK_DIR.as_posix()),
    )


def inventory_snapshot(pack_root: Optional[Path] = None) -> InventorySnapshot:
    """Return a bounded, fail-closed view of Classic + Modern definitions."""
    definitions = [_classic_definition()]
    problems = []
    try:
        definitions.append(load_modern_definition(pack_root))
    except (PackValidationError, ShellPackManifestError, OSError, TypeError, ValueError) as exc:
        problems.append(str(exc)[:MAX_PROBLEM_CHARS])
    # An invalid Modern descriptor is reported, never silently replaced with
    # a guessed definition, and Classic remains independently available.
    return InventorySnapshot(
        definitions=tuple(definitions),
        problems=tuple(problems),
        checked_manifests=1,
    )


def shared_core_snapshot() -> Mapping[str, str]:
    """Immutable service-ownership view: the host owns each service once."""
    return MappingProxyType({name: "host-owned" for name in SHARED_CORE_SERVICES})


def _known(snapshot: InventorySnapshot, pack_id, label: str) -> str:
    if not isinstance(snapshot, InventorySnapshot):
        raise ShellPackManifestError("inventory snapshot is required")
    if type(pack_id) is not str or snapshot.get(pack_id) is None:
        raise ShellPackManifestError(f"{label} is not in the first-party inventory")
    return pack_id


def prepare_switch(snapshot: InventorySnapshot, current_id: str,
                   target_id: str) -> SwitchLedger:
    """Prepare a target offscreen in bookkeeping only; do not activate it."""
    current_id = _known(snapshot, current_id, "current pack")
    target_id = _known(snapshot, target_id, "target pack")
    if current_id == target_id:
        return SwitchLedger(
            from_id=current_id, target_id=target_id, active_id=current_id,
            committed_id=current_id, phase="ALREADY_ACTIVE",
            steps=(SwitchStep("NOOP", "OK", "same pack; nothing prepared"),),
        )
    return SwitchLedger(
        from_id=current_id, target_id=target_id, active_id=current_id,
        committed_id=current_id, phase="PREPARED",
        steps=(SwitchStep(
            "PREPARE", "OK",
            "metadata-only candidate; host must verify compatibility offscreen",
        ),),
    )


def apply_switch(ledger: SwitchLedger) -> SwitchLedger:
    """Mark the prepared target active but uncommitted; no UI is touched."""
    if not isinstance(ledger, SwitchLedger) or ledger.phase != "PREPARED":
        raise ShellPackManifestError("apply requires a PREPARED ledger")
    return replace(
        ledger,
        active_id=ledger.target_id,
        phase="APPLIED",
        steps=ledger.steps + (
            SwitchStep("APPLY", "APPLIED_PENDING_VERIFY", "bookkeeping only"),
        ),
    )


def verify_switch(ledger: SwitchLedger, healthy: bool) -> SwitchLedger:
    """Commit only a healthy target; otherwise restore the committed pack."""
    if not isinstance(ledger, SwitchLedger) or ledger.phase != "APPLIED":
        raise ShellPackManifestError("verify requires an APPLIED ledger")
    if type(healthy) is not bool:
        raise ShellPackManifestError("health verdict must be a bool")
    steps = ledger.steps + (SwitchStep(
        "VERIFY", "OK" if healthy else "FAILED", "synthetic verdict only",
    ),)
    if healthy:
        return replace(
            ledger, committed_id=ledger.target_id, phase="COMMITTED", steps=steps,
        )
    return replace(
        ledger, active_id=ledger.committed_id, phase="ROLLED_BACK",
        steps=steps + (SwitchStep("ROLLBACK", "OK", "committed pack restored"),),
        rolled_back=True,
    )


def rollback_switch(ledger: SwitchLedger, reason: str = "pre-transition stop") -> SwitchLedger:
    """Explicitly roll back a prepared or applied, still-uncommitted target."""
    if not isinstance(ledger, SwitchLedger) or ledger.phase not in ("PREPARED", "APPLIED"):
        raise ShellPackManifestError("rollback requires a PREPARED or APPLIED ledger")
    _clean(reason, "rollback reason", MAX_NOTE_CHARS)
    return replace(
        ledger,
        active_id=ledger.committed_id,
        phase="ROLLED_BACK",
        steps=ledger.steps + (
            SwitchStep("ROLLBACK", "OK", "synthetic rollback: " + reason),
        ),
        rolled_back=True,
    )


def release_inactive(ledger: SwitchLedger) -> SwitchLedger:
    """Record host-side release of the old presentation after a commit."""
    if not isinstance(ledger, SwitchLedger) or ledger.phase != "COMMITTED":
        raise ShellPackManifestError("release requires a COMMITTED ledger")
    return replace(
        ledger,
        phase="RELEASED",
        steps=ledger.steps + (SwitchStep(
            "RELEASE_INACTIVE", "OK",
            "host unsubscribes old UI; shared core services unchanged",
        ),),
    )
