"""Prototype transactional presentation lifecycle for explicitly trusted host adapters.

Important limits:
- Factories are registered *in host code*. NEVER import or instantiate
  classes/QML from Shell Pack metadata, paths, archives or downloaded plugins.
- This is an in-process orchestration primitive tested with dummy adapters.
  It does NOT integrate with Qt, compositor/window state, Mint sessions,
  signatures, sandboxing, or a live desktop switcher.
"""

from dataclasses import dataclass
from threading import Lock
from typing import Callable, FrozenSet, Mapping, Optional, Protocol

from .capabilities import (
    CapabilityError, describe as _describe_capability,
    load as _load_capability, names as _capability_names,
)
from .registry import PackScan


class Presentation(Protocol):
    """Methods implemented by the host's reviewed, trusted UI adapter."""

    def prepare(self) -> None: ...
    def activate(self) -> None: ...
    def deactivate(self) -> None: ...
    def dispose(self) -> None: ...


class SwitchBusy(RuntimeError):
    """A transition or shutdown is already in progress."""


@dataclass(frozen=True)
class SwitchResult:
    from_id: Optional[str]
    to_id: Optional[str]
    status: str
    active_id: Optional[str]
    recovered: bool
    note: str = ""

    @property
    def success(self) -> bool:
        return self.status in ("SWITCHED", "ALREADY_ACTIVE", "STOPPED")


class ShellHost:
    """Single-active-presentation state coordinator (not a Qt runtime loader).

    The factory map is explicitly supplied by trusted application code.
    Every target must also exist in the validated, metadata-only PackScan and
    request no host capabilities outside the provided allowlist.
    """

    def __init__(
        self,
        catalog: PackScan,
        factories: Mapping[str, Callable[[], Presentation]],
        host_capabilities: FrozenSet[str],
    ):
        if not isinstance(host_capabilities, frozenset):
            raise TypeError("host_capabilities must be a frozenset")
        if not isinstance(catalog, PackScan):
            raise TypeError("catalog must be a validated PackScan")
        for pack_id, factory in factories.items():
            if not isinstance(pack_id, str) or not callable(factory):
                raise TypeError("trusted factories need string IDs and callables")
        self._catalog = catalog
        self._factories = dict(factories)
        self._capabilities = host_capabilities
        self._lock = Lock()
        self._active_id: Optional[str] = None
        self._active_view: Optional[Presentation] = None
        self._needs_recovery = False

    @property
    def active_id(self) -> Optional[str]:
        return self._active_id

    @property
    def needs_recovery(self) -> bool:
        return self._needs_recovery

    def available_capabilities(self) -> tuple:
        """Static catalog names explicitly allowed by this host.

        The host capability allowlist supplied at construction gates every
        return value. Discovery imports no feature module and changes no
        presentation state.
        """
        return tuple(name for name in _capability_names()
                     if name in self._capabilities)

    def describe_capability(self, name: str):
        """Return the immutable descriptor for one host-allowed capability."""
        if not isinstance(name, str) or name not in self._capabilities:
            raise CapabilityError("capability not allowed by this host")
        return _describe_capability(name)

    def load_capability(self, name: str):
        """Lazily load one host-allowed pure capability callable."""
        descriptor = self.describe_capability(name)
        if descriptor.visual:
            raise CapabilityError("visual capabilities are not loadable here")
        return _load_capability(name)

    @staticmethod
    def _attempt(view: Presentation, method: str) -> Optional[str]:
        try:
            getattr(view, method)()
            return None
        except Exception as exc:
            # Do not leak exception messages; callbacks may carry secrets.
            return type(exc).__name__

    def _check_target(self, pack_id: str) -> Optional[str]:
        if not isinstance(pack_id, str):
            return "invalid pack ID"
        entry = self._catalog.get(pack_id)
        if entry is None:
            return "pack ID not in validated metadata catalog"
        if not entry.capabilities.issubset(self._capabilities):
            return "capability requirements unsupported"
        if pack_id not in self._factories:
            return "no explicitly trusted host adapter registered"
        return None

    def switch(self, pack_id: str) -> SwitchResult:
        if not self._lock.acquire(blocking=False):
            raise SwitchBusy("another presentation transition is running")
        try:
            return self._switch_locked(pack_id)
        finally:
            self._lock.release()

    def _switch_locked(self, pack_id: str) -> SwitchResult:
        previous_id = self._active_id
        if self._needs_recovery:
            return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                previous_id, False)
        reason = self._check_target(pack_id)
        if reason:
            return SwitchResult(previous_id, pack_id, "REJECTED",
                                previous_id, bool(previous_id), reason)
        if previous_id == pack_id:
            return SwitchResult(previous_id, pack_id, "ALREADY_ACTIVE",
                                previous_id, True)

        # Factory is invoked only from an explicit, trusted host-side map.
        try:
            candidate = self._factories[pack_id]()
            if candidate is None:
                raise ValueError("factory returned no adapter")
        except Exception as exc:
            return SwitchResult(previous_id, pack_id, "FACTORY_FAILED",
                                previous_id, bool(previous_id), type(exc).__name__)

        if candidate is self._active_view:
            return SwitchResult(previous_id, pack_id, "FACTORY_FAILED",
                                previous_id, True,
                                "trusted adapter factory reused the active instance")

        prepared_error = self._attempt(candidate, "prepare")
        if prepared_error:
            cleanup_error = self._attempt(candidate, "dispose")
            note = f"prepare: {prepared_error}"
            if cleanup_error:
                # Candidate cleanup did not complete. An old presentation may
                # still be active, but a second presenter could hold resources.
                # Do not allow more switches before an out-of-band recovery.
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                    previous_id, False,
                                    note + f"; cleanup: {cleanup_error}")
            return SwitchResult(previous_id, pack_id, "PREPARE_FAILED",
                                previous_id, bool(previous_id), note)

        old_view = self._active_view
        if old_view is not None:
            error = self._attempt(old_view, "deactivate")
            if error:
                cleanup_error = self._attempt(candidate, "dispose")
                recovered_error = self._attempt(old_view, "activate")
                if recovered_error or cleanup_error:
                    # A failed dispose cannot be interpreted as rollback,
                    # even when the old presentation was reactivated.
                    self._needs_recovery = True
                    return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                        previous_id, False,
                                        "deactivation, cleanup or restoration incomplete")
                return SwitchResult(previous_id, pack_id, "DEACTIVATE_FAILED",
                                    previous_id, True, error)

        activated_error = self._attempt(candidate, "activate")
        if activated_error:
            # Candidate activation may have partially completed. Never
            # reactivate the old view until candidate deactivation succeeded.
            candidate_off_error = self._attempt(candidate, "deactivate")
            if candidate_off_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                    previous_id, False,
                                    "candidate activation and deactivation failed")
            cleanup_error = self._attempt(candidate, "dispose")
            if old_view is not None:
                old_restore_error = self._attempt(old_view, "activate")
                if old_restore_error:
                    self._needs_recovery = True
                    return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                        previous_id, False,
                                        "old presentation restore failed")
            if cleanup_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                    previous_id, False,
                                    "candidate activation failed and cleanup incomplete")
            return SwitchResult(previous_id, pack_id, "ACTIVATE_FAILED",
                                previous_id, True, activated_error)

        self._active_view = candidate
        self._active_id = pack_id
        if old_view is not None:
            dispose_error = self._attempt(old_view, "dispose")
            if dispose_error:
                # New presentation is active, but old resources might remain.
                # Freeze further transitions rather than accumulate leaks.
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "CLEANUP_FAILED",
                                    pack_id, False, "old adapter dispose failed")
        return SwitchResult(previous_id, pack_id, "SWITCHED", pack_id, True)

    def stop(self) -> SwitchResult:
        if not self._lock.acquire(blocking=False):
            raise SwitchBusy("another presentation transition is running")
        try:
            previous_id = self._active_id
            if self._needs_recovery:
                return SwitchResult(previous_id, None, "RECOVERY_REQUIRED",
                                    previous_id, False)
            if self._active_view is None:
                return SwitchResult(None, None, "STOPPED", None, True)
            off_error = self._attempt(self._active_view, "deactivate")
            if off_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, None, "RECOVERY_REQUIRED",
                                    previous_id, False, "could not deactivate active UI")
            old_view = self._active_view
            self._active_view = None
            self._active_id = None
            dispose_error = self._attempt(old_view, "dispose")
            if dispose_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, None, "CLEANUP_FAILED", None,
                                    False, "adapter dispose failed")
            return SwitchResult(previous_id, None, "STOPPED", None, True)
        finally:
            self._lock.release()
