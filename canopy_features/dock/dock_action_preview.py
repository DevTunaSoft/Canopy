"""Compose one auditable dock-action preview from four tested state models.

Pure data only: the host supplies the immutable outputs of the dock click
mapper, pinned-items state, running-indicator state and keyboard focus order.
This module reconciles them into one bounded decision record with stable
reason codes. It starts no process, performs no filesystem or network work,
owns no timers or threads, and reads no geometry, artwork or GUI state.

Every actionable preview requires all four sources to agree on the same
approved dock label: the click must be actionable, the tile must be pinned and
navigable, keyboard focus must not point at a different tile, and the host's
running snapshot must agree with the decision kind (launch vs focus). Denials
carry no target, action or source fields, so untrusted text cannot reach a log
or a QML bridge through this record.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional

from canopy_features.catalog.missing_app_availability import AppAvailability
from canopy_features.dock.click_intents import (
    APPROVED_DOCK_NAMES,
    ClickIntent,
    IntentKind,
)
from canopy_features.dock.dock_pinned_items import PinnedItems
from canopy_features.dock.dock_running_indicators import IndicatorState
from canopy_features.dock.keyboard_navigation import DockFocusOrder

__all__ = [
    "APPROVED",
    "DENIED",
    "REASON_APP_UNAVAILABLE",
    "REASON_ALREADY_RUNNING",
    "REASON_FOCUS_MISMATCH",
    "REASON_INTENT_IGNORED",
    "REASON_INTENT_REJECTED",
    "REASON_INVALID_INDICATORS",
    "REASON_INVALID_INPUT",
    "REASON_INVALID_PINNED",
    "REASON_INVALID_TARGET",
    "REASON_NOT_IN_FOCUS_ORDER",
    "REASON_NOT_PINNED",
    "REASON_NOT_RUNNING",
    "REASON_OK",
    "REASON_TARGET_MISMATCH",
    "DockActionPreview",
    "PreviewInputError",
    "compose_dock_action_preview",
]

APPROVED = "APPROVED"
DENIED = "DENIED"

REASON_OK = "ok"
REASON_APP_UNAVAILABLE = "app_unavailable"
REASON_INVALID_INPUT = "invalid_input"
REASON_INVALID_TARGET = "invalid_target"
REASON_TARGET_MISMATCH = "target_mismatch"
REASON_INTENT_REJECTED = "intent_rejected"
REASON_INTENT_IGNORED = "intent_ignored"
REASON_INVALID_PINNED = "invalid_pinned"
REASON_NOT_PINNED = "not_pinned"
REASON_NOT_IN_FOCUS_ORDER = "not_in_focus_order"
REASON_FOCUS_MISMATCH = "focus_mismatch"
REASON_INVALID_INDICATORS = "invalid_indicators"
REASON_ALREADY_RUNNING = "already_running"
REASON_NOT_RUNNING = "not_running"

# Each actionable kind has exactly one reason emitted by the trusted click
# mapper. A reason belonging to a different decision makes the source record
# contradictory, even when its token is otherwise well formed.
_LAUNCH_REASON = "installed"
_FOCUS_REASON = "running"


class PreviewInputError(ValueError):
    """Caller passed objects that are not the four expected source records."""


@dataclass(frozen=True)
class DockActionPreview:
    """Immutable host-facing result of reconciling the four source decisions."""

    status: str
    reason: str
    action: Optional[str] = None
    target: Optional[str] = None
    pinned_index: Optional[int] = None
    running_pids: Optional[int] = None
    intent_reason: Optional[str] = None
    indicator_sequence: Optional[int] = None
    focus_was_on_target: bool = False

    @property
    def approved(self):
        return self.status == APPROVED

    def to_dict(self):
        """Plain bounded mapping for a trusted host; denials carry no source."""
        return {
            "status": self.status,
            "reason": self.reason,
            "action": self.action,
            "target": self.target,
            "pinned_index": self.pinned_index,
            "running_pids": self.running_pids,
            "intent_reason": self.intent_reason,
            "indicator_sequence": self.indicator_sequence,
            "focus_was_on_target": self.focus_was_on_target,
        }


def _deny(reason):
    return DockActionPreview(DENIED, reason)


def _pinned_position(pinned, target):
    """Index of ``target``, -1 when absent, or None for a malformed record."""
    items = pinned.items
    if type(items) is not tuple or any(type(item) is not str for item in items):
        return None
    # A repeated id names two tiles at once, so no unique pinned_index can be
    # claimed. The source snapshot is malformed; deny with the existing code.
    if len(set(items)) != len(items):
        return None
    return items.index(target) if target in items else -1


def _focus_fields(focus, target):
    """Pair of (target in order, focus was on target), or None if malformed."""
    items = focus.items
    focused = focus.focused_id
    if type(items) is not tuple or any(type(item) is not str for item in items):
        return None
    if focused is not None and type(focused) is not str:
        return None
    return (target in items, focused == target)


def _running_pid_count(indicators, target):
    """Count of live PIDs owned by ``target``, or None if malformed."""
    sequence = indicators.sequence
    owners = indicators.owners
    # bool is an int subclass and is never a valid sequence stamp.
    if type(sequence) is not int or type(owners) is not tuple:
        return None
    for pair in owners:
        if type(pair) is not tuple or len(pair) != 2:
            return None
        pid, app_id = pair
        if type(pid) is not int or type(app_id) is not str:
            return None
    return sum(1 for _, app_id in owners if app_id == target)


def _launch_blocked_by_missing_app(availability, target):
    """True when an explicit availability record forbids this dock launch.

    ``availability`` is either one ``AppAvailability`` record or a mapping from
    approved dock labels to those records. An absent entry supplies no negative
    information and preserves the existing four-source decision. A malformed
    entry is treated as unavailable: it must never authorize a phantom launch.
    """
    if availability is None:
        return False
    if isinstance(availability, AppAvailability):
        return not availability.launch_permitted
    if not isinstance(availability, Mapping):
        raise PreviewInputError("expected an availability record or mapping")
    try:
        if target not in availability:
            return False
        state = availability[target]
    except Exception:
        return True
    return not (isinstance(state, AppAvailability) and state.launch_permitted)


def compose_dock_action_preview(
    intent, pinned, indicators, focus, target, *, availability=None,
):
    """Reconcile four immutable dock source records into one host decision.

    Wrong source-record types raise ``PreviewInputError``: that is a host
    programming error, not a user-facing dock rejection. Every other bad input
    or disagreement returns a DENIED record with a stable reason code. An
    optional availability record denies a launch of an application the catalog
    has marked unavailable; focus actions are unaffected.
    """
    if not isinstance(intent, ClickIntent):
        raise PreviewInputError("expected a ClickIntent source record")
    if not isinstance(pinned, PinnedItems):
        raise PreviewInputError("expected a PinnedItems source record")
    if not isinstance(indicators, IndicatorState):
        raise PreviewInputError("expected an IndicatorState source record")
    if not isinstance(focus, DockFocusOrder):
        raise PreviewInputError("expected a DockFocusOrder source record")
    if type(target) is not str:
        raise PreviewInputError("target must be an approved dock label string")

    if target not in APPROVED_DOCK_NAMES:
        return _deny(REASON_INVALID_TARGET)

    if intent.kind is IntentKind.REJECT:
        return _deny(REASON_INTENT_REJECTED)
    if intent.kind is IntentKind.IGNORE:
        return _deny(REASON_INTENT_IGNORED)
    if intent.kind is IntentKind.LAUNCH:
        expected_reason = _LAUNCH_REASON
    elif intent.kind is IntentKind.FOCUS:
        expected_reason = _FOCUS_REASON
    else:
        return _deny(REASON_INVALID_INPUT)
    if intent.name != target:
        return _deny(REASON_TARGET_MISMATCH)
    if intent.reason != expected_reason:
        return _deny(REASON_INVALID_INPUT)
    if intent.kind is IntentKind.LAUNCH and _launch_blocked_by_missing_app(
            availability, target):
        return _deny(REASON_APP_UNAVAILABLE)

    position = _pinned_position(pinned, target)
    if position is None:
        return _deny(REASON_INVALID_PINNED)
    if position < 0:
        return _deny(REASON_NOT_PINNED)

    focus_fields = _focus_fields(focus, target)
    if focus_fields is None:
        return _deny(REASON_NOT_IN_FOCUS_ORDER)
    in_order, was_focused = focus_fields
    if not in_order:
        return _deny(REASON_NOT_IN_FOCUS_ORDER)
    if focus.focused_id is not None and not was_focused:
        return _deny(REASON_FOCUS_MISMATCH)

    running = _running_pid_count(indicators, target)
    if running is None:
        return _deny(REASON_INVALID_INDICATORS)
    if intent.kind is IntentKind.LAUNCH and running:
        return _deny(REASON_ALREADY_RUNNING)
    if intent.kind is IntentKind.FOCUS and not running:
        return _deny(REASON_NOT_RUNNING)

    return DockActionPreview(
        status=APPROVED,
        reason=REASON_OK,
        action=intent.kind.value,
        target=target,
        pinned_index=position,
        running_pids=running,
        intent_reason=intent.reason,
        indicator_sequence=indicators.sequence,
        focus_was_on_target=was_focused,
    )
