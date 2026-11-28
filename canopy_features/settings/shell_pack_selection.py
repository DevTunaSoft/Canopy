"""Fail-closed Shell Pack inventory and two-phase selection contract.

This is a pure host-side settings contract. It does not load QML, start a
service, read a compositor, touch the approved Classic artwork, or write a
file. It models only the *decision* and *persistence boundary* of a switch:
a target is prepared, the host attempts the presentation transition, and
only a verified success may commit the persisted selection. Any failure
leaves the last committed selection intact.

The eight built-in identities are fixed by the owner's Canopy/LacOS
directive. They are reserved, included at no cost, and share one Canopy
Core: one compositor/session, one launcher, one window service, one
notification service and one settings/accessibility service. Future packs
are accepted without a numeric cap, but every identity is still bounded and
validated; no pack may introduce a paid tier or a second always-on service.
"""
from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional, Tuple

__all__ = [
    "SCHEMA_VERSION",
    "INCLUDED_TIER",
    "PAID_TIERS",
    "RESERVED_PREFIX",
    "MAX_ID_CHARS",
    "MAX_HISTORY",
    "BUILTIN_IDS",
    "BUILTIN_PACKS",
    "SHARED_CORE_SERVICES",
    "ShellPackSelectionError",
    "PackIdentity",
    "SelectionSnapshot",
    "PackSwitchLedger",
    "validate_pack_id",
    "validate_future_pack",
    "is_builtin",
    "inventory_snapshot",
    "shared_core_snapshot",
]

SCHEMA_VERSION = 1
INCLUDED_TIER = "included"
# Explicitly empty: there is no premium/upgrade/pro path for any pack.
PAID_TIERS = frozenset()
RESERVED_PREFIX = "org.canopy."
MAX_ID_CHARS = 128
MAX_HISTORY = 16

_PACK_ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*){2,}\Z", re.ASCII)


class ShellPackSelectionError(ValueError):
    """Invalid pack identity, transition token or selection state."""


@dataclass(frozen=True)
class PackIdentity:
    """Immutable, cost-free identity of one presentation pack."""

    pack_id: str
    name: str
    builtin: bool

    def __post_init__(self):
        if type(self.pack_id) is not str or not self.pack_id:
            raise ShellPackSelectionError("pack id must be a non-empty string")
        if type(self.name) is not str or not self.name or len(self.name) > 80:
            raise ShellPackSelectionError("pack name is invalid or unbounded")
        if not self.name.isprintable() or self.name != self.name.strip():
            raise ShellPackSelectionError("pack name has control or padding text")
        if type(self.builtin) is not bool:
            raise ShellPackSelectionError("builtin flag must be a bool")
        if not self.builtin and not self.pack_id.startswith(RESERVED_PREFIX):
            validate_pack_id(self.pack_id)

    @property
    def tier(self) -> str:
        # No tier field is stored on a pack: every identity is included.
        return INCLUDED_TIER

    def as_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "name": self.name,
            "builtin": self.builtin,
            "tier": self.tier,
        }


# Owner directive: the initial eight, in declared order. Classic keeps its
# approved identity; no artwork, QML or geometry is changed by this contract.
BUILTIN_PACKS = (
    PackIdentity("org.canopy.classic", "Classic", True),
    PackIdentity("org.canopy.modern", "Modern", True),
    PackIdentity("org.canopy.heritage", "Heritage", True),
    PackIdentity("org.canopy.flow", "Flow", True),
    PackIdentity("org.canopy.lite", "Lite", True),
    PackIdentity("org.canopy.studio", "Studio", True),
    PackIdentity("org.canopy.cloud", "Cloud", True),
    PackIdentity("org.canopy.touch", "Touch", True),
)
BUILTIN_IDS = tuple(pack.pack_id for pack in BUILTIN_PACKS)

# The host owns these once. A pack may request an affordance but never starts
# a parallel instance of any of them.
SHARED_CORE_SERVICES = frozenset({
    "compositor-session",
    "app-launcher",
    "window-management",
    "notifications",
    "settings",
    "accessibility",
    "system-status",
})


def validate_pack_id(value, *, allow_builtin: bool = True) -> str:
    """Return a bounded pack id or raise the module's domain error.

    Built-in identities are reserved and exact; future identities follow the
    same reverse-DNS shape as the offline manifest contract and must never
    impersonate the reserved ``org.canopy.`` namespace.
    """
    if type(value) is not str or not value or len(value) > MAX_ID_CHARS:
        raise ShellPackSelectionError("pack id must be a bounded string")
    if allow_builtin and value in BUILTIN_IDS:
        return value
    if not _PACK_ID.fullmatch(value) or value.startswith(RESERVED_PREFIX):
        raise ShellPackSelectionError("pack id is malformed or reserved")
    return value


def is_builtin(value) -> bool:
    """True only for an exact built-in identity; never raises or normalizes."""
    return type(value) is str and value in BUILTIN_IDS


def inventory_snapshot() -> Tuple[dict, ...]:
    """Immutable-ordered projection of the eight included built-ins."""
    return tuple(pack.as_dict() for pack in BUILTIN_PACKS)


def shared_core_snapshot() -> tuple:
    """Deterministic tuple view of the single shared service set."""
    return tuple(sorted(SHARED_CORE_SERVICES))


@dataclass(frozen=True)
class SelectionSnapshot:
    """Frozen view of the selection ledger's bounded bookkeeping."""

    schema: int
    committed_id: Optional[str]
    pending_id: Optional[str]
    token: Optional[str]
    sequence: int
    history: Tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "schema": self.schema,
            "committed_id": self.committed_id,
            "pending_id": self.pending_id,
            "token": self.token,
            "sequence": self.sequence,
            "history": list(self.history),
        }


class PackSwitchLedger:
    """Two-phase, bounded selection ledger with rollback on failed switches.

    ``prepare`` records the intended target and returns a one-use token;
    ``commit`` is the only operation that changes the persisted selection;
    ``rollback`` drops the pending target without changing that selection.
    A second concurrent prepare is refused instead of queueing work.
    """

    def __init__(self, initial_id: Optional[str] = None):
        if initial_id is not None:
            initial_id = validate_pack_id(initial_id)
        self._lock = threading.Lock()
        self._committed = initial_id
        self._pending = None
        self._token = None
        self._sequence = 0
        self._history = deque(maxlen=MAX_HISTORY)

    def prepare(self, target: str) -> str:
        target = validate_pack_id(target)
        if not self._lock.acquire(blocking=False):
            raise ShellPackSelectionError("a selection transition is pending")
        try:
            if self._pending is not None:
                raise ShellPackSelectionError("a selection transition is pending")
            # A no-op transition is never prepared; the host reports it as
            # ALREADY_ACTIVE instead.
            if target == self._committed:
                raise ShellPackSelectionError("target is already committed")
            token = "selection-%d" % (self._sequence + 1)
            self._pending = target
            self._token = token
            return token
        finally:
            self._lock.release()

    def commit(self, token: str) -> SelectionSnapshot:
        if not self._lock.acquire(blocking=False):
            raise ShellPackSelectionError("a selection transition is pending")
        try:
            self._check_token(token)
            previous = self._committed
            self._committed = self._pending
            self._history.append("%s->%s" % (previous, self._committed))
            self._clear_pending()
            self._sequence += 1
            return self._snapshot()
        finally:
            self._lock.release()

    def rollback(self, token: str) -> SelectionSnapshot:
        if not self._lock.acquire(blocking=False):
            raise ShellPackSelectionError("a selection transition is pending")
        try:
            self._check_token(token)
            self._history.append("rollback->%s" % self._committed)
            self._clear_pending()
            self._sequence += 1
            return self._snapshot()
        finally:
            self._lock.release()

    def _check_token(self, token):
        if (type(token) is not str or self._token is None
                or token != self._token):
            raise ShellPackSelectionError("selection token is invalid or spent")

    def _clear_pending(self):
        self._pending = None
        self._token = None

    def _snapshot(self) -> SelectionSnapshot:
        return SelectionSnapshot(
            schema=SCHEMA_VERSION,
            committed_id=self._committed,
            pending_id=self._pending,
            token=self._token,
            sequence=self._sequence,
            history=tuple(self._history),
        )

    def snapshot(self) -> SelectionSnapshot:
        if not self._lock.acquire(blocking=False):
            raise ShellPackSelectionError("a selection transition is pending")
        try:
            return self._snapshot()
        finally:
            self._lock.release()


def validate_future_pack(pack_id: str) -> str:
    """Validate an additional non-reserved identity; there is no pack cap.

    Identity acceptance is intentionally stateless: the host/supervisor owns
    installation, review and signing. This contract only bounds the name and
    keeps the reserved built-in namespace exclusive.
    """
    return validate_pack_id(pack_id, allow_builtin=False)

