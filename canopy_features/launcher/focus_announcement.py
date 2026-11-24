"""Pure, bounded, no-echo focus-transition announcement records.

This composes already-tested integration-tree records (a dock
``FocusTransition``, a launcher ``SearchView`` and a ``ShellActionDecision``)
into one immutable host-facing announcement. It emits only fixed tokens and
counts: no window id, application id, label, target text or search string is
copied into the record. It never draws, moves a real focus, launches a process,
reads a file or polls.
"""
from dataclasses import dataclass
from typing import Tuple

from canopy_features.dock.keyboard_navigation import FocusTransition
from canopy_features.launcher.launcher_keyboard_navigation import NO_FOCUS
from canopy_features.launcher.launcher_search_view import (
    STATUS_EMPTY,
    STATUS_READY,
    SearchView,
)
from canopy_features.launcher.shell_action_decision import (
    STATUS_DENIED,
    STATUS_IDLE,
    STATUS_READY as DECISION_READY,
    SURFACE_DOCK,
    SURFACE_FILES,
    SURFACE_LAUNCHER,
    ShellActionDecision,
)

STATUS_ANNOUNCE = "ANNOUNCE"
STATUS_SILENT = "SILENT"

REASON_OK = "ok"
REASON_NO_MOTION = "no_motion"
REASON_NO_FOCUS = "no_focus"

MAX_DURATION_MS = 1000
MAX_RESULTS = 64

TOKEN_FOCUS_MOVED = "focus_moved"
TOKEN_FOCUS_UNCHANGED = "focus_unchanged"
TOKEN_FOCUS_WRAPPED = "focus_wrapped"
TOKEN_REDUCED_MOTION = "reduced_motion"
TOKEN_NO_RESULTS = "no_search_results"
TOKEN_RESULT_FOCUSED = "search_result_focused"
TOKEN_SURFACE_DOCK = "surface_dock"
TOKEN_SURFACE_LAUNCHER = "surface_launcher"
TOKEN_SURFACE_FILES = "surface_files"
TOKEN_NO_SURFACE = "no_surface"
TOKEN_ACTION_READY = "action_ready"

_SURFACE_TOKENS = {
    SURFACE_DOCK: TOKEN_SURFACE_DOCK,
    SURFACE_LAUNCHER: TOKEN_SURFACE_LAUNCHER,
    SURFACE_FILES: TOKEN_SURFACE_FILES,
}

CLAIM_NO_WINDOW_IDS_ECHOED = "no_window_ids_echoed"
CLAIM_NO_APP_IDS_ECHOED = "no_app_ids_echoed"
CLAIM_NO_LABELS_ECHOED = "no_labels_echoed"
CLAIM_NO_TARGET_TEXT_ECHOED = "no_target_text_echoed"
CLAIM_NO_VISUAL_CHANGE = "no_visual_change"
CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"

FIXED_CLAIMS = (
    CLAIM_NO_APP_IDS_ECHOED,
    CLAIM_NO_LABELS_ECHOED,
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_TARGET_TEXT_ECHOED,
    CLAIM_NO_VISUAL_CHANGE,
    CLAIM_NO_WINDOW_IDS_ECHOED,
)

__all__ = [
    "CLAIM_NO_APP_IDS_ECHOED",
    "CLAIM_NO_LABELS_ECHOED",
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_TARGET_TEXT_ECHOED",
    "CLAIM_NO_VISUAL_CHANGE",
    "CLAIM_NO_WINDOW_IDS_ECHOED",
    "FIXED_CLAIMS",
    "MAX_DURATION_MS",
    "MAX_RESULTS",
    "REASON_NO_FOCUS",
    "REASON_NO_MOTION",
    "REASON_OK",
    "STATUS_ANNOUNCE",
    "STATUS_SILENT",
    "TOKEN_ACTION_READY",
    "TOKEN_FOCUS_MOVED",
    "TOKEN_FOCUS_UNCHANGED",
    "TOKEN_FOCUS_WRAPPED",
    "TOKEN_NO_RESULTS",
    "TOKEN_NO_SURFACE",
    "TOKEN_REDUCED_MOTION",
    "TOKEN_RESULT_FOCUSED",
    "TOKEN_SURFACE_DOCK",
    "TOKEN_SURFACE_FILES",
    "TOKEN_SURFACE_LAUNCHER",
    "AnnouncementInputError",
    "FocusAnnouncement",
    "compose_focus_announcement",
]


class AnnouncementInputError(ValueError):
    """Malformed caller-supplied source record."""


@dataclass(frozen=True)
class FocusAnnouncement:
    """One bounded announcement; fixed tokens and counts only."""

    status: str
    reason: str
    tokens: Tuple[str, ...] = ()
    result_count: int = 0
    focus_position: int = NO_FOCUS
    claims: Tuple[str, ...] = ()

    def to_dict(self):
        """Plain bounded mapping for a screen-reader or evidence bridge."""
        return {
            "status": self.status,
            "reason": self.reason,
            "tokens": list(self.tokens),
            "result_count": self.result_count,
            "focus_position": self.focus_position,
            "claims": list(self.claims),
        }


def _check_transition(transition):
    if not isinstance(transition, FocusTransition):
        raise AnnouncementInputError("expected a FocusTransition")
    if type(transition.moved) is not bool or type(transition.wrapped) is not bool:
        raise AnnouncementInputError("transition flags must be bool")
    if (type(transition.duration_ms) is not int
            or not 0 <= transition.duration_ms <= MAX_DURATION_MS):
        raise AnnouncementInputError("invalid transition duration")
    for value in (transition.from_id, transition.to_id):
        if value is not None and type(value) is not str:
            raise AnnouncementInputError("invalid transition id")


def _check_view(view):
    if not isinstance(view, SearchView):
        raise AnnouncementInputError("expected a SearchView")
    if type(view.results) is not tuple or len(view.results) > MAX_RESULTS:
        raise AnnouncementInputError("invalid search results")
    if view.status == STATUS_EMPTY:
        if view.results or view.selected_index != NO_FOCUS:
            raise AnnouncementInputError("empty view has focus state")
    elif view.status == STATUS_READY:
        if not view.results or type(view.selected_index) is not int:
            raise AnnouncementInputError("ready view has no valid focus")
        if not 0 <= view.selected_index < len(view.results):
            raise AnnouncementInputError("view focus out of bounds")
    else:
        raise AnnouncementInputError("unsupported search view status")


def _check_decision(decision):
    if not isinstance(decision, ShellActionDecision):
        raise AnnouncementInputError("expected a ShellActionDecision")
    if decision.status not in (DECISION_READY, STATUS_IDLE, STATUS_DENIED):
        raise AnnouncementInputError("unsupported decision status")
    if decision.surface is not None and decision.surface not in _SURFACE_TOKENS:
        raise AnnouncementInputError("unsupported decision surface")


def compose_focus_announcement(transition, view, decision, *, max_results=MAX_RESULTS):
    """Compose one no-echo announcement record; never change real focus.

    A transition with no motion or no target is silent. Every other transition
    is announced with fixed tokens describing motion, wrapping, reduced motion,
    search result state, owning surface and action readiness. Source strings
    are validated but never copied into the result.
    """
    if type(max_results) is not int or not 1 <= max_results <= MAX_RESULTS:
        raise AnnouncementInputError("invalid result bound")
    _check_transition(transition)
    _check_view(view)
    _check_decision(decision)
    if len(view.results) > max_results:
        raise AnnouncementInputError("too many search results")

    tokens = set()
    tokens.add(TOKEN_FOCUS_MOVED if transition.moved else TOKEN_FOCUS_UNCHANGED)
    if transition.wrapped:
        tokens.add(TOKEN_FOCUS_WRAPPED)
    if transition.duration_ms == 0:
        tokens.add(TOKEN_REDUCED_MOTION)
    tokens.add(TOKEN_NO_RESULTS if view.status == STATUS_EMPTY
               else TOKEN_RESULT_FOCUSED)
    tokens.add(_SURFACE_TOKENS.get(decision.surface, TOKEN_NO_SURFACE))
    if decision.status == DECISION_READY:
        tokens.add(TOKEN_ACTION_READY)

    if not transition.moved:
        status, reason = STATUS_SILENT, REASON_NO_MOTION
    elif transition.to_id is None:
        status, reason = STATUS_SILENT, REASON_NO_FOCUS
    else:
        status, reason = STATUS_ANNOUNCE, REASON_OK

    return FocusAnnouncement(
        status=status,
        reason=reason,
        tokens=tuple(sorted(tokens)),
        result_count=len(view.results),
        focus_position=(NO_FOCUS if view.status == STATUS_EMPTY
                        else view.selected_index),
        claims=FIXED_CLAIMS,
    )
