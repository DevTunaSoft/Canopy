"""Prepare explicit terminal app intents without implicit elevated execution.

This is an inert, offline preparation component. It resolves an untrusted
terminal request into a frozen, explicit intent that names a known-good
terminal desktop application by its desktop-entry ID. It never starts a
process, never interprets a shell command, and never grants elevation.

The terminal desktop-ID allowlist mirrors the compiled Classic Qt launcher
(prototype/classic/SystemAppLauncher.cpp, "Terminal" candidates). Execution
stays in that host-owned, opt-in GIO bridge; this module only prepares the
data such a bridge would consume. Future integration must wire the prepared
intent into the compiled Qt application. This module alone is not a working
desktop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Keep in sync with the "Terminal" candidates in SystemAppLauncher.cpp.
# Order is launch priority; the compiled bridge uses the same ordering.
TERMINAL_DESKTOP_IDS = (
    "gnome-terminal.desktop",
    "org.gnome.Terminal.desktop",
    "mate-terminal.desktop",
    "xfce4-terminal.desktop",
)

_DOCK_LABEL = "Terminal"
_LAUNCH_SURFACE = "gio-desktop-app-info"

# Anything outside [A-Za-z0-9.-] is refused at this boundary. Includes shell
# operators, quotes, paths, URLs, newlines, NUL, and Windows expansion tokens.
_UNSAFE_CHARS = frozenset(";&|$`\\\n\r\t\0(){}[]<>!*?#!/='\":%^~")

# Explicit elevation or shell-wrapper words, even without shell operators.
_ELEVATION_TOKENS = re.compile(
    r"(?i)\b(sudo|pkexec|doas|gksu|gksudo|runuser|su|"
    r"sh|bash|zsh|fish|cmd|powershell|pwsh|eval|exec)\b"
)


@dataclass(frozen=True)
class TerminalIntent:
    """Explicit, non-elevated instruction to launch a terminal by desktop ID."""

    desktop_id: str
    candidates: tuple[str, ...]
    launch_surface: str = _LAUNCH_SURFACE
    elevated: bool = False
    argv: tuple[str, ...] = ()

    def to_mapping(self) -> dict:
        """Plain-data form for a future host bridge; no handles or callables."""
        return {
            "desktop_id": self.desktop_id,
            "candidates": list(self.candidates),
            "launch_surface": self.launch_surface,
            "elevated": self.elevated,
            "argv": list(self.argv),
        }


@dataclass(frozen=True)
class TerminalIntentResult:
    """Outcome: PREPARED, UNAVAILABLE (no terminal) or REJECTED (unsafe)."""

    status: str
    reason: str = ""
    intent: TerminalIntent | None = None

    @property
    def success(self) -> bool:
        return self.status == "PREPARED"


def _reject(reason: str) -> TerminalIntentResult:
    return TerminalIntentResult(status="REJECTED", reason=reason)


def prepare_terminal_intent(
    request: str, *, installed=None, elevated: bool = False
) -> TerminalIntentResult:
    """Resolve an untrusted terminal request into an explicit inert intent.

    ``request`` is either the dock label ``"Terminal"`` or one exact terminal
    desktop ID. Arguments, paths, URLs, shell text and extra desktop IDs are
    refused. ``installed`` is an optional iterable of desktop IDs reported
    available by the host (for example via GIO). When supplied but empty of
    known terminals the result is UNAVAILABLE. ``elevated`` asks for privileged
    execution, which this component always refuses.
    """
    if elevated:
        return _reject("elevated execution is never prepared")
    if not isinstance(request, str):
        return _reject("request must be a string")
    if not request or request != request.strip():
        return _reject("request must be an exact token")
    if any(char in request for char in _UNSAFE_CHARS):
        return _reject("request contains unsafe characters")
    if _ELEVATION_TOKENS.search(request):
        return _reject("elevation or shell wrapper not permitted")
    if any(char.isspace() for char in request):
        return _reject("arguments are not accepted")
    if request != _DOCK_LABEL and request not in TERMINAL_DESKTOP_IDS:
        return _reject("unknown terminal application")

    if installed is None:
        chosen = TERMINAL_DESKTOP_IDS[0]
    else:
        available = frozenset(installed)
        chosen = next((item for item in TERMINAL_DESKTOP_IDS if item in available), None)
        if chosen is None:
            return TerminalIntentResult(
                status="UNAVAILABLE", reason="no terminal application available"
            )

    return TerminalIntentResult(
        status="PREPARED",
        intent=TerminalIntent(desktop_id=chosen, candidates=TERMINAL_DESKTOP_IDS),
    )
