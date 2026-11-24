"""Compose three tested host-surface decisions into one shell action record.

Pure data only: the host supplies the immutable outputs of
``dock_action_preview``, ``launcher_search_view`` and ``files_intent_preview``.
This module arbitrates them into ONE bounded decision answering "which single
surface may the shell act on now?". It starts no process, performs no
filesystem or network work, owns no timers or threads, and reads no geometry,
artwork or GUI state.

With no explicit pin, exactly one actionable surface is required: zero means
IDLE, two or more means DENIED as ``ambiguous_surface`` rather than guessing.
A host may pass ``active_surface`` to pin the surface it owns; a pin to a
non-actionable surface is denied. Every denial carries no surface, action or
target text, so untrusted strings cannot reach a log or a QML bridge through
this record. An approved source whose own fields disagree fails closed with
``source_disagreement``. Wrong source-record types raise
``ShellActionCompositionError`` because that is a host programming error.
"""
from dataclasses import dataclass
import unicodedata
from typing import Optional

from canopy_features.apps.file_manager_intent import LAUNCH_ACTION
from canopy_features.apps.files_intent_preview import (
    APPROVED as FILES_APPROVED,
    REASON_OK as FILES_REASON_OK,
    FilesIntentPreview,
)
from canopy_features.dock.dock_action_preview import (
    APPROVED as DOCK_APPROVED,
    REASON_OK as DOCK_REASON_OK,
    DockActionPreview,
)
from canopy_features.launcher.app_search_casefold import Match
from canopy_features.launcher.launcher_search_view import (
    STATUS_READY as SEARCH_READY,
    SearchView,
)

STATUS_READY = "READY"
STATUS_IDLE = "IDLE"
STATUS_DENIED = "DENIED"

REASON_OK = "ok"
REASON_NO_ACTION = "no_action"
REASON_AMBIGUOUS = "ambiguous_surface"
REASON_SURFACE_NOT_ACTIONABLE = "surface_not_actionable"
REASON_SOURCE_DISAGREEMENT = "source_disagreement"

SURFACE_DOCK = "dock"
SURFACE_LAUNCHER = "launcher"
SURFACE_FILES = "files"
SURFACES = (SURFACE_DOCK, SURFACE_LAUNCHER, SURFACE_FILES)

MAX_TARGET_CHARS = 512

# Length alone does not make text safe to hand to a host bridge. Reject every
# non-printing Unicode category: C1/C0 controls (Cc), bidi/zero-width format
# characters (Cf), surrogates (Cs), private-use scalars (Co), unassigned or
# noncharacters (Cn), and line/paragraph separators (Zl, Zp). Zs (including the
# ordinary space) stays printable and is intentionally allowed.
_UNSAFE_TEXT_CATEGORIES = frozenset(("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"))

_DOCK_ACTIONS = frozenset(("launch", "focus"))

__all__ = [
    "MAX_TARGET_CHARS",
    "REASON_AMBIGUOUS",
    "REASON_NO_ACTION",
    "REASON_OK",
    "REASON_SOURCE_DISAGREEMENT",
    "REASON_SURFACE_NOT_ACTIONABLE",
    "STATUS_DENIED",
    "STATUS_IDLE",
    "STATUS_READY",
    "SURFACES",
    "SURFACE_DOCK",
    "SURFACE_FILES",
    "SURFACE_LAUNCHER",
    "ShellActionCompositionError",
    "ShellActionDecision",
    "compose_shell_action_decision",
]


class ShellActionCompositionError(ValueError):
    """Caller passed objects that are not the expected source records."""


class _SourceDisagreement(Exception):
    """Internal: an approved source record contradicts its own fields."""


@dataclass(frozen=True)
class ShellActionDecision:
    """One immutable, bounded shell decision for a trusted host.

    ``surface``, ``action`` and ``target`` are set only when ``status`` is
    ``READY``; every other status leaves them as ``None``.
    """

    status: str
    reason: str
    surface: Optional[str] = None
    action: Optional[str] = None
    target: Optional[str] = None

    @property
    def ready(self):
        return self.status == STATUS_READY

    def to_dict(self):
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "status": self.status,
            "reason": self.reason,
            "surface": self.surface,
            "action": self.action,
            "target": self.target,
        }


def _deny(reason):
    return ShellActionDecision(STATUS_DENIED, reason)


def _text_ok(value, limit=MAX_TARGET_CHARS):
    """Bounded printable Unicode, free of controls and non-printing scalars."""
    return (type(value) is str and 0 < len(value) <= limit
            and all(char >= " " and char != "\x7f"
                    and unicodedata.category(char) not in _UNSAFE_TEXT_CATEGORIES
                    for char in value))


def _dock_candidate(preview):
    """Return (action, target) for an approved, self-consistent dock record."""
    if not preview.approved:
        return None
    if (preview.status != DOCK_APPROVED
            or preview.reason != DOCK_REASON_OK
            or preview.action not in _DOCK_ACTIONS
            or not _text_ok(preview.target)
            or type(preview.pinned_index) is not int
            or preview.pinned_index < 0
            or type(preview.running_pids) is not int
            or preview.running_pids < 0):
        raise _SourceDisagreement
    return (preview.action, preview.target)


def _launcher_candidate(view):
    """Return ("select", name) for a ready, self-consistent search view."""
    if view.status != SEARCH_READY:
        return None
    index = view.selected_index
    results = view.results
    if (type(index) is not int or isinstance(index, bool)
            or type(results) is not tuple or not results
            or not 0 <= index < len(results)
            or not all(isinstance(match, Match) for match in results)
            or not _text_ok(view.selected_name)
            or view.selected_name != results[index].name):
        raise _SourceDisagreement
    return ("select", view.selected_name)


def _files_candidate(preview):
    """Return (action, uri) for an approved, self-consistent files preview."""
    if not preview.approved:
        return None
    if (preview.status != FILES_APPROVED
            or preview.reason != FILES_REASON_OK
            or preview.action != LAUNCH_ACTION
            or type(preview.uri) is not str
            or not preview.uri.startswith("file:")
            or not _text_ok(preview.uri)):
        raise _SourceDisagreement
    return (preview.action, preview.uri)


def compose_shell_action_decision(
    dock_preview, search_view, files_preview, *, active_surface=None,
):
    """Arbitrate three surface previews into one host-facing decision.

    Wrong source types raise ``ShellActionCompositionError``. Internal source
    disagreements and ambiguity deny without carrying any target text. A host
    pin must name one of ``SURFACES``. Nothing is launched or mutated.
    """
    if not isinstance(dock_preview, DockActionPreview):
        raise ShellActionCompositionError("expected a DockActionPreview")
    if not isinstance(search_view, SearchView):
        raise ShellActionCompositionError("expected a SearchView")
    if not isinstance(files_preview, FilesIntentPreview):
        raise ShellActionCompositionError("expected a FilesIntentPreview")
    if active_surface is not None and (
            type(active_surface) is not str or active_surface not in SURFACES):
        raise ShellActionCompositionError("invalid active surface")

    try:
        candidates = {
            SURFACE_DOCK: _dock_candidate(dock_preview),
            SURFACE_LAUNCHER: _launcher_candidate(search_view),
            SURFACE_FILES: _files_candidate(files_preview),
        }
    except _SourceDisagreement:
        return _deny(REASON_SOURCE_DISAGREEMENT)

    if active_surface is not None:
        candidate = candidates[active_surface]
        if candidate is None:
            return _deny(REASON_SURFACE_NOT_ACTIONABLE)
        action, target = candidate
        return ShellActionDecision(
            STATUS_READY, REASON_OK, active_surface, action, target)

    ready = [surface for surface in SURFACES if candidates[surface] is not None]
    if not ready:
        return ShellActionDecision(STATUS_IDLE, REASON_NO_ACTION)
    if len(ready) > 1:
        return _deny(REASON_AMBIGUOUS)
    surface = ready[0]
    action, target = candidates[surface]
    return ShellActionDecision(STATUS_READY, REASON_OK, surface, action, target)
