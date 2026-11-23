"""Offline detection of collisions between user and shell shortcut registration.

Pure Python and side-effect free: no polling, background services, OS hooks,
privileged calls or network access. Callers feed registrations in and read
conflicts out; this module never grabs keys or changes any binding.

The reserved combos below mirror the Shortcut declarations in the compiled
Classic Qt source (prototype/classic/Main.qml). They are metadata, not runtime
enforcement. A future Qt Shell Host must call detect_conflicts() at its own
registration boundary; this module alone does not prove a working desktop.
"""

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Optional, Tuple

SHELL_SOURCE = "shell"
USER_SOURCE = "user"

CONFLICT_RESERVED_COMBO = "reserved_combo"
CONFLICT_DUPLICATE_SEQUENCE = "duplicate_sequence"
CONFLICT_DUPLICATE_ACTION = "duplicate_action"

MAX_REGISTRATIONS = 128
MAX_SEQUENCE_LENGTH = 64

# Mirrors the Shortcut declarations in prototype/classic/Main.qml.
SHELL_RESERVED_SEQUENCES: FrozenSet[str] = frozenset({
    "Ctrl+Space",    # toggle application launcher
    "Ctrl+W",        # close Files preview
    "Ctrl+Shift+F",  # reopen Files preview
})

_MODIFIER_ALIASES = {
    "ctrl": "Ctrl", "control": "Ctrl",
    "shift": "Shift",
    "alt": "Alt", "option": "Alt",
    "meta": "Meta", "super": "Meta", "win": "Meta", "cmd": "Meta",
}
_KEY_ALIASES = {
    "space": "Space", "spacebar": "Space",
    "esc": "Escape", "return": "Enter", "del": "Delete",
}
_KEY_NAMES = {
    "escape": "Escape", "enter": "Enter", "delete": "Delete",
    "tab": "Tab", "backspace": "Backspace", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
}
for _index in range(1, 13):
    _KEY_NAMES["f%d" % _index] = "F%d" % _index
_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Meta")


def _canonical_tokens(sequence: str) -> Tuple[str, ...]:
    if not isinstance(sequence, str):
        raise TypeError("sequence must be a string")
    if not sequence.strip():
        raise ValueError("sequence must not be empty")
    if len(sequence) > MAX_SEQUENCE_LENGTH:
        raise ValueError("sequence exceeds %d characters" % MAX_SEQUENCE_LENGTH)

    raw_tokens = [token.strip() for token in sequence.split("+")]
    if any(not token or any(char.isspace() for char in token) for token in raw_tokens):
        raise ValueError("malformed sequence: %r" % sequence)

    modifiers = set()
    for token in raw_tokens[:-1]:
        modifier = _MODIFIER_ALIASES.get(token.lower())
        if modifier is None:
            raise ValueError("unknown modifier in sequence: %r" % sequence)
        modifiers.add(modifier)

    key_token = raw_tokens[-1]
    lowered = key_token.lower()
    if lowered in _KEY_ALIASES:
        key = _KEY_ALIASES[lowered]
    elif len(key_token) == 1 and key_token.isalnum():
        key = key_token.upper()
    elif key_token[0].isalpha() and all(char.isalnum() for char in key_token):
        key = _KEY_NAMES.get(lowered, key_token)
    else:
        raise ValueError("unknown key in sequence: %r" % sequence)

    ordered = tuple(name for name in _MODIFIER_ORDER if name in modifiers)
    return ordered + (key,)


def canonicalize_sequence(sequence: str) -> str:
    """Return a stable Qt-style combo, e.g. 'ctrl+shift+f' -> 'Ctrl+Shift+F'."""
    return "+".join(_canonical_tokens(sequence))


def _reserved_sequences(reserved: Optional[Iterable[str]]) -> FrozenSet[str]:
    if reserved is None:
        return SHELL_RESERVED_SEQUENCES
    return frozenset(canonicalize_sequence(sequence) for sequence in reserved)


@dataclass(frozen=True)
class ShortcutRegistration:
    """One requested binding. action is a stable id, not a display label."""

    action: str
    sequence: str
    source: str = USER_SOURCE
    enabled: bool = True


@dataclass(frozen=True)
class Conflict:
    """A detected collision. Fields are values for callers, not UI text."""

    kind: str
    message: str
    sequence: str = ""
    action: str = ""
    sources: Tuple[str, ...] = ()


def detect_conflicts(registrations: Iterable[ShortcutRegistration],
                     reserved: Optional[Iterable[str]] = None) -> Tuple[Conflict, ...]:
    """Return deterministic collisions for the supplied registrations.

    Disabled registrations are not active and are skipped. Invalid input is
    rejected instead of being silently ignored. No state is kept by this call.
    """
    registrations = tuple(registrations)
    if len(registrations) > MAX_REGISTRATIONS:
        raise ValueError("too many shortcut registrations (limit %d)" % MAX_REGISTRATIONS)

    reserved_set = _reserved_sequences(reserved)
    for registration in registrations:
        if not isinstance(registration, ShortcutRegistration):
            raise TypeError("registrations must contain ShortcutRegistration values")
        if not isinstance(registration.action, str) or not registration.action.strip():
            raise ValueError("registration action must be a non-empty string")
        if registration.source not in (SHELL_SOURCE, USER_SOURCE):
            raise ValueError("unknown shortcut source: %r" % registration.source)

    conflicts = []
    by_sequence = {}
    by_action = {}
    for registration in registrations:
        canonical = canonicalize_sequence(registration.sequence)
        if not registration.enabled:
            continue
        if registration.source == USER_SOURCE and canonical in reserved_set:
            conflicts.append(Conflict(
                kind=CONFLICT_RESERVED_COMBO,
                message="user action %r uses shell-reserved combo %s"
                        % (registration.action, canonical),
                sequence=canonical,
                action=registration.action,
                sources=(USER_SOURCE,),
            ))
        by_sequence.setdefault(canonical, []).append(registration)
        by_action.setdefault(registration.action, []).append(registration)

    for canonical, group in by_sequence.items():
        if len(group) > 1:
            conflicts.append(Conflict(
                kind=CONFLICT_DUPLICATE_SEQUENCE,
                message="combo %s registered %d times" % (canonical, len(group)),
                sequence=canonical,
                sources=tuple(sorted({item.source for item in group})),
            ))

    for action, group in by_action.items():
        if len(group) > 1:
            combos = ", ".join(sorted(canonicalize_sequence(item.sequence) for item in group))
            conflicts.append(Conflict(
                kind=CONFLICT_DUPLICATE_ACTION,
                message="action %r registered with combos %s" % (action, combos),
                action=action,
                sources=tuple(sorted({item.source for item in group})),
            ))

    return tuple(sorted(conflicts, key=lambda item: (item.kind, item.sequence, item.action)))


class ShortcutRegistry:
    """Bounded in-memory registration set with immediate collision reporting."""

    def __init__(self, reserved: Optional[Iterable[str]] = None):
        self._reserved = reserved
        self._registrations = []

    def register(self, registration: ShortcutRegistration) -> Tuple[Conflict, ...]:
        """Add one registration and return current conflicts; reject overflow."""
        if not isinstance(registration, ShortcutRegistration):
            raise TypeError("registration must be a ShortcutRegistration")
        if len(self._registrations) >= MAX_REGISTRATIONS:
            raise ValueError("registry is full (limit %d)" % MAX_REGISTRATIONS)
        self._registrations.append(registration)
        return self.conflicts()

    def unregister(self, action: str, source: Optional[str] = None) -> bool:
        """Remove matching registrations; return True if anything was removed."""
        before = len(self._registrations)
        self._registrations = [
            item for item in self._registrations
            if not (item.action == action and (source is None or item.source == source))
        ]
        return len(self._registrations) != before

    def conflicts(self) -> Tuple[Conflict, ...]:
        return detect_conflicts(self._registrations, self._reserved)

    @property
    def registrations(self) -> Tuple[ShortcutRegistration, ...]:
        return tuple(self._registrations)
