"""One immutable, no-echo dock presentation intent snapshot for a host.

Pure state module: it composes the already-tested ``dock_running_indicators``,
``notification_badges`` and ``click_intents`` surfaces into one bounded
fail-closed presentation record. It never reads geometry, QML or artwork, never
enumerates windows itself, and never launches a process.

Unlike ``dock_action_preview`` (which decides a click action from pinned items
and keyboard focus), this record answers only "how many trusted tiles should
present a running indicator or a badge, and is the current click intent
consistent with that presentation?". Counts and fixed negative claims are the
only output fields: no PID, app id, label or intent text is copied through.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Tuple

from canopy_features.dock.click_intents import (
    APPROVED_DOCK_NAMES,
    ClickIntent,
    IntentKind,
)
from canopy_features.dock.dock_running_indicators import (
    IndicatorState,
    indicator_ids,
    running_pid_count,
)
from canopy_features.dock.notification_badges import NotificationBadges

STATUS_READY = "READY"
STATUS_DENIED = "DENIED"

REASON_OK = "ok"
REASON_INVALID_INPUT = "invalid_input"
REASON_UNTRUSTED_SURFACE = "untrusted_surface"
REASON_INTENT_DISAGREEMENT = "intent_disagreement"

CLAIM_NO_PIDS_ECHOED = "no_pids_echoed"
CLAIM_NO_APP_IDS_ECHOED = "no_app_ids_echoed"
CLAIM_NO_LABELS_ECHOED = "no_labels_echoed"
CLAIM_NO_GEOMETRY_READ = "no_geometry_read"
CLAIM_NO_PROCESS_LAUNCHED = "no_process_launched"
CLAIM_NO_VALUE_ECHO = "no_value_echo"

FIXED_CLAIMS = (
    CLAIM_NO_APP_IDS_ECHOED,
    CLAIM_NO_GEOMETRY_READ,
    CLAIM_NO_LABELS_ECHOED,
    CLAIM_NO_PIDS_ECHOED,
    CLAIM_NO_PROCESS_LAUNCHED,
    CLAIM_NO_VALUE_ECHO,
)

__all__ = [
    "CLAIM_NO_APP_IDS_ECHOED",
    "CLAIM_NO_GEOMETRY_READ",
    "CLAIM_NO_LABELS_ECHOED",
    "CLAIM_NO_PIDS_ECHOED",
    "CLAIM_NO_PROCESS_LAUNCHED",
    "CLAIM_NO_VALUE_ECHO",
    "FIXED_CLAIMS",
    "REASON_INTENT_DISAGREEMENT",
    "REASON_INVALID_INPUT",
    "REASON_OK",
    "REASON_UNTRUSTED_SURFACE",
    "STATUS_DENIED",
    "STATUS_READY",
    "DockPresentationIntent",
    "compose_dock_presentation_intent",
]


@dataclass(frozen=True)
class DockPresentationIntent:
    """One bounded host preview; denials carry no source material.

    ``claims`` is the fixed tuple of negative claims only on a READY preview.
    Every count is a number, never a copied id or label.
    """

    status: str
    reason: str
    running_tiles: int = 0
    badge_tiles: int = 0
    total_pids: int = 0
    claims: Tuple[str, ...] = ()

    @property
    def ready(self):
        return self.status == STATUS_READY

    def to_dict(self):
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "status": self.status,
            "reason": self.reason,
            "running_tiles": self.running_tiles,
            "badge_tiles": self.badge_tiles,
            "total_pids": self.total_pids,
            "claims": list(self.claims),
        }


def _deny(reason):
    return DockPresentationIntent(STATUS_DENIED, reason)


def _ids(value):
    """Validate an id collection without echoing any member."""
    if type(value) is not tuple or not all(type(item) is str for item in value):
        return None
    return frozenset(value)


def compose_dock_presentation_intent(intent, indicators, badges):
    """Compose one no-echo presentation snapshot; launch nothing.

    Wrong source types deny with ``invalid_input``. Running and badged app ids
    must all belong to the trusted ``click_intents`` allowlist. An actionable
    click intent must agree with the running snapshot (FOCUS means running,
    LAUNCH means not running); REJECT and IGNORE intents impose no requirement.
    """
    if not isinstance(intent, ClickIntent):
        return _deny(REASON_INVALID_INPUT)
    if not isinstance(indicators, IndicatorState):
        return _deny(REASON_INVALID_INPUT)
    if not isinstance(badges, NotificationBadges):
        return _deny(REASON_INVALID_INPUT)
    if intent.kind not in (IntentKind.LAUNCH, IntentKind.FOCUS,
                           IntentKind.REJECT, IntentKind.IGNORE):
        return _deny(REASON_INVALID_INPUT)
    # ClickIntent is frozen but its fields are not validated at construction.
    # A bounded non-str label would either raise a raw TypeError at the set
    # membership tests below or be silently accepted as an inert READY intent.
    if type(intent.name) is not str:
        return _deny(REASON_INVALID_INPUT)

    running = _ids(indicator_ids(indicators))
    snapshot = badges.snapshot()
    badged = _ids(tuple(snapshot.keys())) if isinstance(snapshot, Mapping) else None
    if running is None or badged is None:
        return _deny(REASON_INVALID_INPUT)

    if not running <= APPROVED_DOCK_NAMES or not badged <= APPROVED_DOCK_NAMES:
        return _deny(REASON_UNTRUSTED_SURFACE)

    if intent.kind is IntentKind.FOCUS and intent.name not in running:
        return _deny(REASON_INTENT_DISAGREEMENT)
    if intent.kind is IntentKind.LAUNCH and intent.name in running:
        return _deny(REASON_INTENT_DISAGREEMENT)
    if (intent.kind in (IntentKind.FOCUS, IntentKind.LAUNCH)
            and intent.name not in APPROVED_DOCK_NAMES):
        return _deny(REASON_UNTRUSTED_SURFACE)

    try:
        total_pids = sum(running_pid_count(indicators, app_id)
                         for app_id in running)
    except (TypeError, ValueError):
        return _deny(REASON_INVALID_INPUT)

    return DockPresentationIntent(
        status=STATUS_READY,
        reason=REASON_OK,
        running_tiles=len(running),
        badge_tiles=len(badged),
        total_pids=total_pids,
        claims=FIXED_CLAIMS,
    )
