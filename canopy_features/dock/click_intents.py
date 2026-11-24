"""Pure, offline mapping of Classic dock activations to safe intents.

The compiled Qt dock emits ``activated(string applicationName)`` from
DockTile.qml. That string crosses a QML trust boundary: it must never become a
command, path, URL, desktop-file id or argument. This module turns a raw
activation into a small, immutable :class:`ClickIntent` that a host may act on.

It performs no launch, no focus, no OS call and no polling. The host supplies
authoritative ``installed`` / ``running`` snapshots through :meth:`observe`;
this mapper only decides. All held state is bounded by the fixed allowlist, so
repeated or hostile input cannot grow memory.

This is a standalone host-side decision component. It does not wire itself
into the compiled Qt application; that integration is separate future work.
"""

from dataclasses import dataclass
from enum import Enum

# Mirrors the host GIO allowlist in prototype/classic/SystemAppLauncher.cpp.
# Exact, case-sensitive dock labels only; no desktop ids or free-form input.
APPROVED_DOCK_NAMES = frozenset((
    "Browser", "Mail", "Files", "Calendar",
    "Photos", "Music", "Terminal", "Settings",
))


class IntentKind(Enum):
    """The only actions a host is allowed to take from a dock click."""

    LAUNCH = "launch"
    FOCUS = "focus"
    REJECT = "reject"
    IGNORE = "ignore"


@dataclass(frozen=True)
class ClickIntent:
    """Decision payload. Frozen, so no caller can mutate a resolved intent."""

    kind: IntentKind
    name: str
    reason: str

    @property
    def actionable(self):
        return self.kind in (IntentKind.LAUNCH, IntentKind.FOCUS)


def _approved_subset(values):
    """Keep only approved labels; ignore unknown or hostile entries."""
    if values is None or isinstance(values, (str, bytes)):
        return frozenset()
    try:
        return frozenset(v for v in values if type(v) is str and v in APPROVED_DOCK_NAMES)
    except TypeError:
        return frozenset()


class DockClickMapper:
    """Event-driven mapper: host reports state, ``resolve`` returns an intent."""

    def __init__(self, *, installed=(), running=(), launcher_enabled=True):
        self._installed = _approved_subset(installed)
        self._running = _approved_subset(running)
        self._launcher_enabled = bool(launcher_enabled)
        self._pending = frozenset()

    def observe(self, *, installed=None, running=None, launcher_enabled=None):
        """Apply a host state snapshot. No query, no wait, no polling."""
        if installed is not None:
            self._installed = _approved_subset(installed)
        if running is not None:
            self._running = _approved_subset(running)
        if launcher_enabled is not None:
            self._launcher_enabled = bool(launcher_enabled)
        # A name that is now running, or no longer installed, is not pending.
        self._pending = self._pending & (self._installed - self._running)

    def resolve(self, activation):
        """Map one raw dock activation string to an immutable ClickIntent."""
        name = activation
        if type(name) is not str or name not in APPROVED_DOCK_NAMES:
            return ClickIntent(IntentKind.REJECT, "", "untrusted-id")

        if name in self._running:
            self._pending = self._pending - {name}
            if not self._launcher_enabled:
                # A running label must not resurrect a valid click claim once
                # the host has disabled the launcher: FOCUS is actionable, so
                # emitting it would contradict the enabled flag. Fail closed.
                return ClickIntent(IntentKind.IGNORE, name, "launcher-disabled")
            return ClickIntent(IntentKind.FOCUS, name, "running")

        if name in self._pending:
            # Repeated click while a launch is in flight: never launch twice.
            return ClickIntent(IntentKind.IGNORE, name, "launch-pending")

        if name in self._installed and self._launcher_enabled:
            self._pending = self._pending | {name}
            return ClickIntent(IntentKind.LAUNCH, name, "installed")

        return ClickIntent(IntentKind.REJECT, name, "missing-target")

    @property
    def state_size(self):
        """Bounded diagnostic: approved names currently held in state."""
        return len(self._installed | self._running | self._pending)
