"""Offline no-duplication state model for theme switching rollback.

The model tracks ownership of presentation resources across a theme switch
so that an interrupted switch rolls back cleanly: one active theme, at most
one in-flight candidate, and no resource handle owned twice.

It is a pure in-memory ledger. It performs no I/O, Qt or compositor work,
threading, timers or polling, and starts no background service. It never
disposes real resources itself: callers dispose the handles returned by
:meth:`ThemeTransitionRollback.reclaim_abandoned`. Wiring this ledger into
the compiled Qt Shell Host is future work and is not proven here.

This complements (and does not duplicate) ``canopy_core.shell_host.ShellHost``:
that class orchestrates trusted presenter callbacks, while this module is a
small ownership ledger used to reason about rollback state and abandoned
resources without executing a presenter.
"""

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Optional

IDLE = "IDLE"
PREPARED = "PREPARED"


@dataclass(frozen=True)
class Snapshot:
    """Immutable view of ledger state for tests and reliability checks."""

    state: str
    active: Optional[str]
    candidate: Optional[str]
    live_resources: FrozenSet[str]
    abandoned_resources: FrozenSet[str]

    @property
    def single_owner(self) -> bool:
        """True when no resource is both live and awaiting disposal."""
        return not (self.live_resources & self.abandoned_resources)


class ThemeTransitionRollback:
    """Single-active theme transition ledger with explicit rollback.

    Resource names are opaque non-empty strings supplied by the host. A name
    is owned by exactly one place at a time: the active theme, the in-flight
    candidate, or the abandoned set. A switch interrupted before commit
    abandons the candidate and leaves the active theme and its resources
    untouched.
    """

    MAX_ABANDONED = 16

    def __init__(
        self,
        initial_theme: Optional[str] = None,
        initial_resources: Iterable[str] = (),
    ):
        if initial_theme is not None and not isinstance(initial_theme, str):
            raise TypeError("initial_theme must be a string or None")
        resources = self._normalize(initial_resources)
        if len(resources) > self.MAX_ABANDONED:
            raise ValueError("initial resources exceed ledger capacity")
        self._active = initial_theme
        self._active_resources = resources
        self._candidate: Optional[str] = None
        self._candidate_resources: FrozenSet[str] = frozenset()
        self._abandoned: FrozenSet[str] = frozenset()
        self._state = IDLE

    @staticmethod
    def _normalize(resources: Iterable[str]) -> FrozenSet[str]:
        names = set()
        for name in resources:
            if not isinstance(name, str) or not name:
                raise ValueError("resource names must be non-empty strings")
            if name in names:
                raise ValueError("duplicate resource name in one batch")
            names.add(name)
        return frozenset(names)

    def _can_abandon(self, resources: FrozenSet[str]) -> bool:
        return len(self._abandoned) + len(resources) <= self.MAX_ABANDONED

    def prepare(self, theme: str, resources: Iterable[str]) -> str:
        """Record one offscreen candidate; return a status string.

        A busy ledger, a duplicate resource name or a full abandoned set
        rejects the request without changing state.
        """
        if self._state != IDLE:
            return "BUSY"
        if not isinstance(theme, str) or not theme:
            return "INVALID_THEME"
        try:
            batch = self._normalize(resources)
        except ValueError:
            return "INVALID_RESOURCES"
        if batch & self._active_resources or batch & self._abandoned:
            return "DUPLICATE_RESOURCE"
        if not self._can_abandon(self._active_resources) or not self._can_abandon(batch):
            return "RECLAIM_REQUIRED"
        self._candidate = theme
        self._candidate_resources = batch
        self._state = PREPARED
        return "PREPARED"

    def commit(self) -> str:
        """Promote candidate to active; old resources become abandoned."""
        if self._state != PREPARED:
            return "NO_CANDIDATE"
        self._abandoned |= self._active_resources
        self._active = self._candidate
        self._active_resources = self._candidate_resources
        self._clear_candidate()
        return "COMMITTED"

    def interrupt(self) -> str:
        """Abort an in-flight switch; old active theme stays authoritative."""
        if self._state != PREPARED:
            return "NO_CANDIDATE"
        self._abandoned |= self._candidate_resources
        self._clear_candidate()
        return "ROLLED_BACK"

    def reclaim_abandoned(self) -> FrozenSet[str]:
        """Return abandoned names for disposal and clear them atomically.

        The set is emptied in the same call, so a handle is handed out at
        most once and cannot be reclaimed twice.
        """
        claimed = self._abandoned
        self._abandoned = frozenset()
        return claimed

    def snapshot(self) -> Snapshot:
        return Snapshot(
            state=self._state,
            active=self._active,
            candidate=self._candidate,
            live_resources=self._active_resources | self._candidate_resources,
            abandoned_resources=self._abandoned,
        )

    def _clear_candidate(self) -> None:
        self._candidate = None
        self._candidate_resources = frozenset()
        self._state = IDLE
