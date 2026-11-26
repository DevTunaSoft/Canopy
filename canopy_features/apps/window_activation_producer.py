"""Bounded, read-only producer of the trusted ``hostActivationSnapshot`` record.

This module composes two already-tested pure contracts from the windows state
model into the **exact** host snapshot shape that the Classic host owns:

* ``windows/workspace_inventory.py`` -- canonical workspaces and skipped-record
  notes, consumed here through the composed focus-decision record;
* ``windows/focus_decision_snapshot.py`` -- the immutable composition of the
  workspace inventory, the deny-by-default focus broker and the switcher view.

It adds only host-owned facts (backend id, sequence, launcher state and the
launcher's approved-name install set) and emits the eight keys the compiled
consumer requires: ``schema``, ``sequence``, ``backend``, ``negotiation``,
``launcherEnabled``, ``installed``, ``owners`` and ``grants``. The optional
``focus`` sub-object is deliberately never emitted, and ``owners``/``grants``
are always empty: this module invents no process, window or permission
telemetry, exactly like the host's current trusted snapshot source.

This is a **pure composition layer**: no I/O, clock, randomness, threads,
sockets, environment, Qt, compositor or WM observation, and no process launch.
Every input is validated before any record is built; hostile or unbounded
input raises ``ProducerError`` with no partial result. Output is deterministic
and immutable. Nothing here proves a compiled connection, a running desktop,
real window-manager behaviour or Linux Mint acceptance -- injecting this
record into the compiled host is a later, serialized step that requires
ownership of ``prototype/classic/main.cpp`` and is explicitly NOT done here.
"""
from dataclasses import dataclass
import json
from types import MappingProxyType

from canopy_features.windows import focus_decision_snapshot as decisions
from canopy_features.windows.window_state_capabilities import KNOWN_BACKENDS

SCHEMA = 1

# The compiled consumer reads ``schema``, ``sequence`` and ``backend`` as a
# 32-bit int/known string, so the producer never emits a wider sequence.
MAX_SEQUENCE = 2_147_483_647
MAX_ID_LENGTH = 128
MAX_INSTALLED = 64

# Mirrors ``approvedDockNames()`` / ``knownBackends()`` in the compiled state
# component and the ``KNOWN_BACKENDS`` ids of window_state_capabilities.py.
APPROVED_DOCK_NAMES = (
    "Browser", "Mail", "Files", "Calendar",
    "Photos", "Music", "Terminal", "Settings",
)
_APPROVED = frozenset(APPROVED_DOCK_NAMES)
_PARTIAL_BACKENDS = frozenset({"headless"})

NEGOTIATION_SUPPORTED = "SUPPORTED"
NEGOTIATION_PARTIAL = "PARTIAL"
NEGOTIATION_UNSUPPORTED = "UNSUPPORTED"

# Exact required key set of the trusted host snapshot (fixed order).
HOST_KEYS = (
    "schema", "sequence", "backend", "negotiation", "launcherEnabled",
    "installed", "owners", "grants",
)


class ProducerError(ValueError):
    """Malformed, unbounded or untrusted input to the producer."""


@dataclass(frozen=True)
class HostActivationSnapshot:
    """Immutable snapshot with the exact trusted host key set."""

    schema: int
    sequence: int
    backend: str
    negotiation: str
    launcher_enabled: bool
    installed: tuple
    owners: tuple
    grants: tuple

    def to_dict(self):
        """Fresh read-only view with the exact host keys in fixed order."""
        return MappingProxyType({
            "schema": self.schema,
            "sequence": self.sequence,
            "backend": self.backend,
            "negotiation": self.negotiation,
            "launcherEnabled": self.launcher_enabled,
            "installed": self.installed,
            "owners": self.owners,
            "grants": self.grants,
        })

    def to_json_bytes(self):
        """Serialize the snapshot to deterministic JSON bytes.

        Tuples become JSON arrays, which the compiled consumer reads as
        ``QVariantList``. This is a serializer for a later host step, NOT an
        injection or an acceptance claim; no file, socket or process is used.
        """
        # json.dumps renders tuples as JSON arrays, which the compiled
        # consumer reads as QVariantList; no mutable list is exposed.
        return json.dumps(dict(self.to_dict()), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _backend(value):
    # Type-check before membership: an unhashable container must fail closed
    # with ProducerError, never leak a raw TypeError from the dict lookup.
    if (type(value) is not str or not value
            or len(value) > MAX_ID_LENGTH or value not in KNOWN_BACKENDS):
        raise ProducerError("backend is not a known host backend id")
    return value


def _sequence(value):
    if type(value) is not int or not 0 <= value <= MAX_SEQUENCE:
        raise ProducerError("sequence must be a bounded non-negative int")
    return value


def _flag(value, field):
    if type(value) is not bool:
        raise ProducerError(field + " must be a bool")
    return value


def _installed(value):
    """Return approved launcher names in the canonical host order.

    The compiled host iterates its fixed approved-name list, so the producer
    mirrors that order and refuses unordered containers, duplicates and any
    name outside the allowlist. Only list/tuple input is accepted: a str,
    bytes, mapping or lazy iterator cannot define a bounded host install set.
    """
    if type(value) not in (list, tuple) or len(value) > MAX_INSTALLED:
        raise ProducerError("installed must be a bounded list or tuple")
    supplied = []
    for name in value:
        if type(name) is not str or name not in _APPROVED:
            raise ProducerError("installed contains an unapproved name")
        if name in supplied:
            raise ProducerError("installed contains a duplicate name")
        supplied.append(name)
    return tuple(name for name in APPROVED_DOCK_NAMES if name in supplied)


def _negotiation(backend):
    # Mirrors hostActivationSnapshot(): headless is PARTIAL, a known real
    # backend is SUPPORTED. UNSUPPORTED is only reachable for an unknown
    # backend, which _backend() already refuses, so it is never emitted here.
    return NEGOTIATION_PARTIAL if backend in _PARTIAL_BACKENDS else NEGOTIATION_SUPPORTED


def _decision(focus_broker, workspace, switcher_state, policy):
    """Compose and re-pin the workspace/focus/switcher decision record."""
    try:
        record = decisions.compose(focus_broker, workspace, switcher_state, policy)
    except decisions.SnapshotError as exc:
        raise ProducerError("workspace/focus decision record rejected") from exc
    # A failed focus decision must not be republished as a trusted activation
    # snapshot: fail closed before any host token is copied.
    if record.status == decisions.STATUS_BLOCKED:
        raise ProducerError("focus decision record is blocked")
    return record


def compose(workspace, focus_broker, switcher_state, *,
            backend, sequence, launcher_enabled, installed, policy=None):
    """Compose trusted workspace/focus contracts into the exact host record.

    ``workspace`` is a ``WorkspaceInventory``, ``focus_broker`` a
    ``FocusBroker``, ``switcher_state`` a ``SwitchState`` and ``policy`` an
    optional ``PermissionPolicy`` -- the four inputs of the already-tested
    ``focus_decision_snapshot.compose`` contract. Host-owned facts are passed
    by keyword; ``installed`` is the launcher's approved-name install set.
    Nothing is read, launched or observed; equal inputs give equal bytes.
    """
    backend = _backend(backend)
    sequence = _sequence(sequence)
    launcher_enabled = _flag(launcher_enabled, "launcherEnabled")
    installed = _installed(installed)
    _decision(focus_broker, workspace, switcher_state, policy)
    return HostActivationSnapshot(
        schema=SCHEMA,
        sequence=sequence,
        backend=backend,
        negotiation=_negotiation(backend),
        launcher_enabled=launcher_enabled,
        installed=installed,
        owners=(),
        grants=(),
    )


__all__ = [
    "SCHEMA", "MAX_SEQUENCE", "MAX_ID_LENGTH", "MAX_INSTALLED",
    "APPROVED_DOCK_NAMES", "NEGOTIATION_SUPPORTED", "NEGOTIATION_PARTIAL",
    "NEGOTIATION_UNSUPPORTED", "HOST_KEYS", "ProducerError",
    "HostActivationSnapshot", "compose",
]
