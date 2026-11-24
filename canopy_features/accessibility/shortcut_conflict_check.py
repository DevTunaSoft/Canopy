"""Offline, bounded shortcut collision detection for Canopy accessibility.

Consumes shortcut bindings supplied by a trusted host as ``(action, sequence)``
pairs. Does not read QML, Qt, the compositor, the OS key map or any desktop
service. Opens no sockets, starts no threads, polls nothing and keeps no state
between calls. Use it to surface accessibility regressions (gate R043) before
a binding reaches the shell; it does not prove a working desktop.
"""
from dataclasses import dataclass

SOURCE_SHELL = "shell"
SOURCE_USER = "user"

KIND_RESERVED = "reserved"
KIND_COLLISION = "collision"
KIND_DUPLICATE = "duplicate"

MAX_SEQUENCE_LENGTH = 64
MAX_TOKENS = 6
MAX_ACTION_LENGTH = 64
MAX_REGISTRATIONS = 256

_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl",
    "alt": "alt", "option": "alt",
    "shift": "shift",
    "meta": "meta", "super": "meta", "win": "meta", "cmd": "meta",
}
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "meta")

# Window-manager, Cinnamon and accessibility keys the shell and users must not
# take. Callers may pass a narrower or wider set via ``reserved=``.
RESERVED_COMBOS = frozenset({
    "alt+tab",              # window switching (WM)
    "alt+f2",               # run dialog (Cinnamon)
    "alt+f7",               # move window (WM)
    "alt+f8",               # resize window (WM)
    "alt+f10",              # maximize window (WM)
    "ctrl+alt+delete",      # session / logout
    "ctrl+alt+backspace",   # legacy X reset
    "meta",                 # Super / overview
    "meta+d",               # show desktop
    "print",                # screenshot
    "ctrl+alt+t",           # terminal (common global)
})


class ShortcutConflictError(ValueError):
    """Invalid registration, reserved set, or exceeded bound (fail closed)."""


def normalize_sequence(sequence):
    """Return a canonical lowercase key sequence or raise ShortcutConflictError.

    Modifiers are aliased and emitted in a fixed order; keys are lowercased.
    A single modifier token such as ``Super`` is a valid key of its own.
    Chords with more than one non-modifier key are not supported.
    """
    if type(sequence) is not str:
        raise ShortcutConflictError("sequence must be a string")
    if not sequence.strip() or len(sequence) > MAX_SEQUENCE_LENGTH:
        raise ShortcutConflictError("invalid or oversized sequence")
    # Control/format characters are not key identifiers. Left in place they
    # change the canonical sequence without changing its visible spelling,
    # which can bypass reserved-combo checks and hide real collisions. Check
    # before whitespace folding: some C0 controls count as whitespace and are
    # otherwise silently removed by str.split().
    if any(not char.isprintable() for char in sequence):
        raise ShortcutConflictError("non-printable character in sequence")
    tokens = [part.strip() for part in sequence.split("+")]
    if any(not part for part in tokens):
        raise ShortcutConflictError("empty sequence token")
    if len(tokens) > MAX_TOKENS:
        raise ShortcutConflictError("too many sequence tokens")
    tokens = ["".join(part.split()).casefold() for part in tokens]
    if any(not part for part in tokens):
        raise ShortcutConflictError("empty sequence token")
    modifiers = [_MODIFIER_ALIASES.get(part) for part in tokens]
    keys = [tokens[i] for i, mod in enumerate(modifiers) if mod is None]
    if not keys:
        if len(tokens) == 1 and modifiers[0] is not None:
            return modifiers[0]
        raise ShortcutConflictError("sequence has no non-modifier key")
    if len(keys) != 1:
        raise ShortcutConflictError("multiple non-modifier keys are unsupported")

    mods = [modifiers[i] for i, mod in enumerate(modifiers) if mod is not None]
    if len(set(mods)) != len(mods):
        raise ShortcutConflictError("duplicate modifier")
    ordered = [mod for mod in _MODIFIER_ORDER if mod in mods]
    return "+".join(ordered + keys)


@dataclass(frozen=True)
class Conflict:
    """One detected problem: reserved use, cross-registration collision, or dup."""

    kind: str
    sequence: str
    actions: tuple
    sources: tuple
    count: int


@dataclass(frozen=True)
class ConflictReport:
    """Immutable, deterministically ordered result of a single check."""

    conflicts: tuple

    @property
    def ok(self):
        """True only when no conflict was found."""
        return not self.conflicts

    def of_kind(self, kind):
        """Return conflicts matching ``kind`` as a tuple."""
        return tuple(c for c in self.conflicts if c.kind == kind)


def _normalized_reserved(reserved):
    if isinstance(reserved, (str, bytes)):
        raise ShortcutConflictError("reserved must be an iterable of sequences")
    try:
        items = frozenset(reserved)
    except TypeError as exc:
        raise ShortcutConflictError("reserved must be iterable") from exc
    if len(items) > MAX_REGISTRATIONS:
        raise ShortcutConflictError("reserved set is oversized")
    return frozenset(normalize_sequence(item) for item in items)


def _validate_registrations(items, source):
    if isinstance(items, (str, bytes)):
        raise ShortcutConflictError("registrations must be iterable of pairs")
    try:
        iterable = iter(items)
    except TypeError as exc:
        # Non-iterable callers (None, ints, floats, ...) must fail closed with
        # the documented domain error, not leak a bare TypeError from `for`.
        raise ShortcutConflictError("registrations must be iterable of pairs") from exc
    result = []
    for item in iterable:
        if len(result) >= MAX_REGISTRATIONS:
            raise ShortcutConflictError("too many registrations")
        if not isinstance(item, (tuple, list)):
            raise ShortcutConflictError("registration must be an (action, sequence) pair")
        # A hostile-but-bounded pair can lie about len() while yielding a
        # different number of elements. Materialize the actual elements and
        # check their count before unpacking: otherwise the gate leaks a raw
        # ValueError instead of its documented domain error.
        try:
            pair = tuple(item)
        except (TypeError, ValueError) as exc:
            raise ShortcutConflictError(
                "registration must be an (action, sequence) pair") from exc
        if len(pair) != 2:
            raise ShortcutConflictError("registration must be an (action, sequence) pair")
        action, sequence = pair
        if type(action) is not str or not action.strip() or len(action) > MAX_ACTION_LENGTH:
            raise ShortcutConflictError("invalid or oversized action")
        result.append((source, action.strip(), normalize_sequence(sequence)))
    return result


def detect_shortcut_conflicts(shell=(), user=(), reserved=RESERVED_COMBOS):
    """Check shell and user ``(action, sequence)`` registrations for conflicts.

    Reports reserved-key use, one combo claimed by multiple distinct actions,
    and registrations repeated verbatim. Raises ShortcutConflictError on bad
    input rather than silently ignoring it.
    """
    registrations = _validate_registrations(shell, SOURCE_SHELL)
    registrations += _validate_registrations(user, SOURCE_USER)
    if len(registrations) > MAX_REGISTRATIONS:
        raise ShortcutConflictError("too many registrations")
    reserved_set = _normalized_reserved(reserved)

    conflicts = []
    for source, action, sequence in registrations:
        if sequence in reserved_set:
            conflicts.append(Conflict(
                KIND_RESERVED, sequence, (action,), (source,), 1))

    by_sequence = {}
    for registration in registrations:
        by_sequence.setdefault(registration[2], []).append(registration)
    for sequence, group in by_sequence.items():
        pairs = {(source, action) for source, action, _ in group}
        if len(pairs) > 1:
            conflicts.append(Conflict(
                KIND_COLLISION, sequence,
                tuple(sorted({action for _, action in pairs})),
                tuple(sorted({source for source, _ in pairs})),
                len(pairs),
            ))

    counts = {}
    for registration in registrations:
        counts[registration] = counts.get(registration, 0) + 1
    for (source, action, sequence), total in counts.items():
        if total > 1:
            conflicts.append(Conflict(
                KIND_DUPLICATE, sequence, (action,), (source,), total))

    conflicts.sort(key=lambda c: (c.kind, c.sequence, c.sources, c.actions, c.count))
    return ConflictReport(tuple(conflicts))
