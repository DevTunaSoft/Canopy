"""Trusted window-role mapping for dock grouping and window switching.

Pure, offline data transform owned by the host. A trusted adapter supplies
observed window records; this module classifies each record into a fixed
allowlist of roles, derives deterministic dock groups and a switch order.
It never observes real windows, launches apps, imports Qt, polls, opens
sockets, starts threads or keeps state between calls. Output is immutable and
depends only on the supplied records.

This is NOT a window manager, dock implementation, compositor integration,
Qt bridge or proof of a working desktop. Future work must wire these decisions
into the compiled Classic application and validate them there.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional, Tuple

MAX_WINDOWS = 512
MAX_APP_ID_LENGTH = 128
MAX_ID_VALUE = 1_000_000_000_000

__all__ = [
    "MAX_WINDOWS", "WindowRoleError", "RolePolicy", "ROLE_POLICIES",
    "TRUSTED_ROLES", "WindowRecord", "ResolvedRole", "DockGroup",
    "policy_for", "classify", "build_dock_groups", "switch_order",
]


class WindowRoleError(ValueError):
    """Invalid window record, oversized input or untrusted role request."""


@dataclass(frozen=True)
class RolePolicy:
    """Decision flags for one trusted role."""
    name: str
    dock_group: bool
    switchable: bool
    transient: bool


# Fixed, host-owned allowlist. Unknown input never extends this mapping.
# Only an ordinary app window creates a dock group and enters switch order.
# Transient roles follow their parent's group; the rest are excluded.
ROLE_POLICIES = MappingProxyType({
    "app": RolePolicy("app", True, True, False),
    "dialog": RolePolicy("dialog", False, False, True),
    "utility": RolePolicy("utility", False, False, True),
    "menu": RolePolicy("menu", False, False, True),
    "splash": RolePolicy("splash", False, False, True),
    "notification": RolePolicy("notification", False, False, False),
    "desktop": RolePolicy("desktop", False, False, False),
    "dock": RolePolicy("dock", False, False, False),
    "unknown": RolePolicy("unknown", False, False, False),
})
TRUSTED_ROLES = frozenset(ROLE_POLICIES)


@dataclass(frozen=True)
class WindowRecord:
    """One host-observed window. Caller supplies trusted, bounded values."""
    window_id: int
    app_id: str
    role_hints: Tuple[str, ...] = ()
    parent_id: Optional[int] = None


@dataclass(frozen=True)
class ResolvedRole:
    """Fail-closed classification result for one window record."""
    role: str
    trusted: bool
    ambiguous: bool


@dataclass(frozen=True)
class DockGroup:
    """Deterministic dock grouping key and its window ids in input order."""
    key: Tuple[str, str]
    window_ids: Tuple[int, ...]


def policy_for(role):
    """Return the policy for a trusted role name, else raise WindowRoleError."""
    if type(role) is not str or role not in ROLE_POLICIES:
        raise WindowRoleError("untrusted window role")
    return ROLE_POLICIES[role]


def _validate_id(value, label):
    if type(value) is not int or not 1 <= value <= MAX_ID_VALUE:
        raise WindowRoleError("invalid " + label)
    return value


def _validate_app_id(value):
    if (type(value) is not str or not value
            or len(value) > MAX_APP_ID_LENGTH
            or any(ord(char) < 0x20 or ord(char) == 0x7f for char in value)):
        raise WindowRoleError("invalid app id")
    return value


def _validated_records(records):
    if type(records) not in (list, tuple) or len(records) > MAX_WINDOWS:
        raise WindowRoleError("invalid or oversized window record set")
    by_id = {}
    for record in records:
        if not isinstance(record, WindowRecord):
            raise WindowRoleError("window record required")
        _validate_id(record.window_id, "window id")
        _validate_app_id(record.app_id)
        if type(record.role_hints) is not tuple:
            raise WindowRoleError("role hints must be a tuple")
        for hint in record.role_hints:
            if type(hint) is not str:
                raise WindowRoleError("role hints must be strings")
        if record.parent_id is not None:
            _validate_id(record.parent_id, "parent window id")
        if record.window_id in by_id:
            raise WindowRoleError("duplicate window id")
        by_id[record.window_id] = record
    return tuple(records), by_id


def classify(record):
    """Map one record's role hints to a single trusted role, failing closed.

    No hints or any unrecognized hint resolve to ``unknown`` (untrusted).
    More than one distinct trusted hint is ambiguous and also resolves to
    ``unknown``; the module never guesses a privileged role from mixed hints.
    Repeated identical hints are not ambiguous.
    """
    if not isinstance(record, WindowRecord):
        raise WindowRoleError("window record required")
    hints = record.role_hints
    if type(hints) is not tuple:
        raise WindowRoleError("role hints must be a tuple")
    if not hints:
        return ResolvedRole("unknown", False, False)
    recognized = set()
    for hint in hints:
        if type(hint) is not str:
            raise WindowRoleError("role hints must be strings")
        if hint not in TRUSTED_ROLES:
            return ResolvedRole("unknown", False, False)
        recognized.add(hint)
    if len(recognized) != 1:
        return ResolvedRole("unknown", False, True)
    role = next(iter(recognized))
    return ResolvedRole(role, True, False)


def _group_key(record, by_id, memo):
    """Resolve a group key, following transient parents with bounded memory."""
    chain = []
    seen = set()
    current = record
    while True:
        rid = current.window_id
        if rid in memo:
            key = memo[rid]
            break
        if rid in seen:
            # Parent cycle: fail closed to an orphan group, never loop forever.
            key = ("orphan", current.app_id)
            break
        seen.add(rid)
        chain.append(current)
        resolved = classify(current)
        role = resolved.role
        if resolved.trusted and role == "app":
            key = ("app", current.app_id)
            break
        if resolved.trusted and ROLE_POLICIES[role].transient:
            parent = (by_id.get(current.parent_id)
                      if current.parent_id is not None else None)
            if parent is None:
                # Missing or dangling parent: keep the transient window in a
                # distinct orphan group; never merge it into a guessed app.
                key = ("orphan", current.app_id)
                break
            current = parent
            continue
        key = None
        break
    for item in chain:
        memo[item.window_id] = key
    return key


def build_dock_groups(records):
    """Return immutable dock groups sorted by key, or raise WindowRoleError.

    An ``app`` window keys its own group (``"app", app_id``). A transient
    window with a resolvable parent joins that parent's group. A transient
    window with a missing, dangling or cyclic parent gets an ``"orphan"``
    key instead of crashing. Non-groupable roles are omitted.
    """
    validated, by_id = _validated_records(records)
    memo = {}
    grouped = {}
    for record in validated:
        key = _group_key(record, by_id, memo)
        if key is None:
            continue
        grouped.setdefault(key, []).append(record.window_id)
    return tuple(DockGroup(key, tuple(window_ids))
                 for key, window_ids in sorted(grouped.items()))


def switch_order(records):
    """Return switchable window ids in caller-supplied (e.g. MRU) order.

    Only trusted, non-transient app windows qualify. Dialogs and other
    transient windows are reached through their parent's dock group.
    """
    validated, _ = _validated_records(records)
    order = []
    for record in validated:
        resolved = classify(record)
        if resolved.trusted and ROLE_POLICIES[resolved.role].switchable:
            order.append(record.window_id)
    return tuple(order)
