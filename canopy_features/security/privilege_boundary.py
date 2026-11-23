"""Offline privilege boundary for Canopy preview and desktop helpers.

Small deny gate used by a caller BEFORE it forwards an action to a helper.
It never spawns processes, changes credentials, polls, or starts services.
It returns stable reason codes; action text is never stored or logged.

Honest limits:
- Denylist, not a sandbox. It refuses known elevation wrappers and known
  system-administration commands, not arbitrary malicious binaries.
- Inherited elevation is detected with ``os.geteuid()`` on POSIX. On hosts
  without ``geteuid`` (Windows), elevation detection is unavailable; the host
  must launch helpers unelevated. Argument-based sudo denial still applies.
- Callers must wire this into the compiled Qt application themselves. This
  module alone does not prove any desktop or Mint behavior.
"""

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional, Union


ALLOWED = "allowed"
DENIED_EMPTY_ACTION = "empty-action"
DENIED_INVALID_ACTION = "invalid-action"
DENIED_OVERSIZED = "oversized-action"
DENIED_INHERITED_ROOT = "inherited-root"
DENIED_ELEVATION = "elevation-command"
DENIED_SYSTEM_COMMAND = "system-command"

# Bounded input: no unbounded allocation from hostile helper requests.
MAX_ARGUMENTS = 64
MAX_ARGUMENT_LENGTH = 4096

# Elevation wrappers, including common POSIX/Windows variants.
_ELEVATION = frozenset({
    "sudo", "sudoedit", "pkexec", "doas", "su", "runuser",
    "gksudo", "gksu", "kdesudo", "runas",
})

# System-level commands a preview/desktop helper must never invoke.
# Names are matched whole after basename normalization, so a harmless word
# such as "--title=mkfs.ext4 guide" is still allowed.
_SYSTEM = frozenset({
    "apt", "apt-get", "dpkg", "snap", "systemctl", "service",
    "mount", "umount", "fdisk", "mkfs", "iptables", "ufw",
    "useradd", "usermod", "userdel", "passwd", "visudo",
    "reboot", "shutdown", "halt", "poweroff", "setcap",
    "insmod", "modprobe",
    # Debian/Ubuntu/Mint account tools. The original list had only the
    # lower-level useradd/userdel forms, so the friendly wrappers and group
    # tools failed open on the distributions Canopy targets.
    "adduser", "addgroup", "deluser", "delgroup",
    "groupadd", "groupmod", "groupdel", "newusers", "chpasswd",
})

# Dispatch utilities are named ``mkfs.<fstype>`` on Linux, not ``mkfs``:
# mkfs.ext4, mkfs.vfat, mkfs.xfs, mkfs.btrfs, ...  A prefix rule covers new
# filesystem types without another denylist update. It is applied to the
# normalized whole word (see _basename), so it cannot match a bare word that
# merely contains "mkfs." mid-token.
_SYSTEM_PREFIXES = frozenset({"mkfs."})

# Split injected shell words so "sh -c 'sudo mount /'" is still caught.
_WORD_SPLIT = re.compile(r"[\s;&|`$()<>\n\r]+")

_AUTO = object()


@dataclass(frozen=True)
class Decision:
    """Result of a check. ``reason`` is a stable code, never action text."""

    allowed: bool
    reason: str

    def __bool__(self) -> bool:
        return self.allowed


class PrivilegeDenied(PermissionError):
    """Raised by :func:`authorize` when an action is refused.

    ``str(exc)`` and ``exc.reason`` contain only a stable reason code.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def current_euid() -> Optional[int]:
    """Effective user id on POSIX; ``None`` where unavailable (Windows)."""
    getter = getattr(os, "geteuid", None)
    return getter() if getter is not None else None


def _basename(word: str) -> str:
    """Normalize one shell word to a lowercase executable basename.

    Every trailing ``.exe`` is removed, not just the last one: normalization
    must be a fixed point, otherwise a decorated spelling such as
    ``sudo.exe.exe`` normalizes to ``sudo.exe`` (not denylisted) while a
    second pass normalizes it to ``sudo`` (denied). The deny decision cannot
    depend on how many times the word has been normalized.
    """
    name = word.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1]
    while name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower()


def _words(argument: str):
    """Yield normalized words from one bounded argument."""
    for piece in _WORD_SPLIT.split(argument):
        name = _basename(piece)
        if name:
            yield name


def _is_system_command(word: str) -> bool:
    """True for a denied system command, exact name or dispatch prefix."""
    return word in _SYSTEM or any(word.startswith(p) for p in _SYSTEM_PREFIXES)


def evaluate(argv: Sequence[str], *, euid: Union[int, None, object] = _AUTO) -> Decision:
    """Decide whether a helper action may proceed. Pure; runs nothing.

    ``argv`` must be a list or tuple of short strings. Pass ``euid`` to make a
    check deterministic or to simulate inherited root on any host; omit it to
    detect the current process.
    """
    if euid is _AUTO:
        euid = current_euid()

    if not isinstance(argv, (list, tuple)):
        return Decision(False, DENIED_INVALID_ACTION)
    if len(argv) > MAX_ARGUMENTS:
        return Decision(False, DENIED_OVERSIZED)
    if not argv:
        return Decision(False, DENIED_EMPTY_ACTION)
    for argument in argv:
        if not isinstance(argument, str):
            return Decision(False, DENIED_INVALID_ACTION)
        if len(argument) > MAX_ARGUMENT_LENGTH:
            return Decision(False, DENIED_OVERSIZED)

    if euid == 0:
        return Decision(False, DENIED_INHERITED_ROOT)

    for argument in argv:
        for word in _words(argument):
            if word in _ELEVATION:
                return Decision(False, DENIED_ELEVATION)
            if _is_system_command(word):
                return Decision(False, DENIED_SYSTEM_COMMAND)
    return Decision(True, ALLOWED)


def authorize(argv: Sequence[str], *, euid: Union[int, None, object] = _AUTO) -> None:
    """Raise :class:`PrivilegeDenied` unless :func:`evaluate` allows ``argv``."""
    decision = evaluate(argv, euid=euid)
    if not decision.allowed:
        raise PrivilegeDenied(decision.reason)
