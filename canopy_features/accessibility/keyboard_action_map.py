"""Screen-independent keyboard action intents for Canopy accessibility.

An intent names what the user wants to do, not which screen, window or widget
performs it. The host binds an intent to a concrete control; this module never
loads QML, opens windows, installs global hooks, polls or observes real keys.

Availability is supplied by the host and explicit. Rebuilding a map is the only
way to change it, so no background state or polling is involved. The default
catalog mirrors the intents already exposed by the Classic Qt preview menus
and shortcuts; it does not replace or modify that source.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Optional

MAX_ACTIONS = 64
MAX_ID_LENGTH = 64
MAX_LABEL_BYTES = 128
MAX_SHORTCUT_TOKENS = 4

_ID = re.compile(r"[a-z][a-z0-9_]{0,31}(\.[a-z][a-z0-9_]{0,31}){0,3}\Z")
_MODIFIERS = ("Ctrl", "Alt", "Shift", "Meta")
_MODIFIER_LOOKUP = {name.casefold(): name for name in _MODIFIERS}
_NAMED_KEYS = frozenset((
    "Escape Space Return Enter Tab Backtab Home End PageUp PageDown "
    "Up Down Left Right Delete Backspace Insert"
).split()) | frozenset("F%d" % number for number in range(1, 13))
_KEY_LOOKUP = {name.casefold(): name for name in _NAMED_KEYS}


class KeyboardActionError(ValueError):
    """Invalid intent, keyboard sequence or catalog definition."""


class DuplicateShortcutError(KeyboardActionError):
    """Two accessible intents claim the same normalized shortcut."""

    def __init__(self, shortcut, first_id, second_id):
        super().__init__(
            "duplicate shortcut %r: %s, %s" % (shortcut, first_id, second_id)
        )
        self.shortcut = shortcut
        self.first_id = first_id
        self.second_id = second_id


class InaccessibleActionError(KeyboardActionError):
    """Intent has no usable accessible name, so it cannot be exposed."""


def normalize_shortcut(sequence):
    """Return canonical 'Ctrl+Shift+F' form for a keyboard sequence."""
    if type(sequence) is not str:
        raise KeyboardActionError("shortcut must be a string")
    tokens = [token.strip() for token in sequence.split("+")]
    if (not 1 <= len(tokens) <= MAX_SHORTCUT_TOKENS
            or any(not token for token in tokens)):
        raise KeyboardActionError("malformed keyboard shortcut")

    modifiers = set()
    for token in tokens[:-1]:
        modifier = _MODIFIER_LOOKUP.get(token.casefold())
        if modifier is None or modifier in modifiers:
            raise KeyboardActionError("unsupported or repeated modifier")
        modifiers.add(modifier)

    key = tokens[-1]
    folded = key.casefold()
    if folded in _MODIFIER_LOOKUP:
        raise KeyboardActionError("shortcut needs a non-modifier key")
    if len(key) == 1 and key.isascii() and (key.isalpha() or key.isdigit()):
        key = key.upper() if key.isalpha() else key
    elif folded in _KEY_LOOKUP:
        key = _KEY_LOOKUP[folded]
    else:
        raise KeyboardActionError("unsupported shortcut key")

    ordered = [name for name in _MODIFIERS if name in modifiers]
    return "+".join(ordered + [key])


@dataclass(frozen=True)
class KeyboardActionIntent:
    """One screen-independent action with an accessible name and shortcut."""

    action_id: str
    label: str
    shortcut: Optional[str] = None
    available: bool = True

    def __post_init__(self):
        if (type(self.action_id) is not str
                or len(self.action_id) > MAX_ID_LENGTH
                or not _ID.fullmatch(self.action_id)):
            raise KeyboardActionError("invalid keyboard action id")
        if type(self.label) is not str or not self.label.strip():
            raise InaccessibleActionError("action needs an accessible name")
        if any(ord(char) < 32 or ord(char) == 127 for char in self.label):
            raise InaccessibleActionError("accessible name has a control character")
        try:
            label_bytes = len(self.label.encode("utf-8", "strict"))
        except UnicodeError as exc:
            raise InaccessibleActionError("invalid accessible name") from exc
        if label_bytes > MAX_LABEL_BYTES:
            raise InaccessibleActionError("accessible name exceeds bound")
        if type(self.available) is not bool:
            raise KeyboardActionError("availability must be a bool")
        if self.shortcut is not None:
            object.__setattr__(self, "shortcut", normalize_shortcut(self.shortcut))


# Intent ids mirror the actions already present in Main.qml and ShellMenuBar.qml.
# No screen, window or widget is named; the host owns that binding.
DEFAULT_ACTIONS = (
    KeyboardActionIntent("launcher.toggle", "Toggle application launcher", "Ctrl+Space"),
    KeyboardActionIntent("launcher.dismiss", "Dismiss application launcher", "Escape"),
    KeyboardActionIntent("files.open", "Open Files", "Ctrl+Shift+F"),
    KeyboardActionIntent("files.close", "Close Files", "Ctrl+W"),
    KeyboardActionIntent("files.find", "Find in Files"),
    KeyboardActionIntent("files.focus_search", "Focus Files search field"),
    KeyboardActionIntent("files.go_home", "Go to Files home"),
    KeyboardActionIntent("files.go_back", "Go back in Files"),
    KeyboardActionIntent("files.go_up", "Go up in Files"),
    KeyboardActionIntent("help.about", "About Canopy Classic"),
    # Disabled in the existing View menu: catalogued but not accessible.
    KeyboardActionIntent("files.location", "Current Files location", available=False),
)


class KeyboardActionMap:
    """Immutable, bounded catalog of screen-independent action intents."""

    def __init__(self, intents=DEFAULT_ACTIONS, *, max_actions=MAX_ACTIONS):
        if type(intents) not in (list, tuple):
            raise KeyboardActionError("intents must be a list or tuple")
        if (type(max_actions) is not int
                or not 1 <= max_actions <= MAX_ACTIONS):
            raise KeyboardActionError("invalid action catalog bound")
        if len(intents) > max_actions:
            raise KeyboardActionError("action catalog exceeds bound")

        by_id = {}
        by_shortcut = {}
        for intent in intents:
            if not isinstance(intent, KeyboardActionIntent):
                raise KeyboardActionError("catalog holds only action intents")
            if intent.action_id in by_id:
                raise KeyboardActionError("duplicate keyboard action id")
            by_id[intent.action_id] = intent
            if intent.available and intent.shortcut is not None:
                if intent.shortcut in by_shortcut:
                    raise DuplicateShortcutError(
                        intent.shortcut,
                        by_shortcut[intent.shortcut].action_id,
                        intent.action_id,
                    )
                by_shortcut[intent.shortcut] = intent

        self._intents = tuple(intents)
        self._by_id = MappingProxyType(by_id)
        self._by_shortcut = MappingProxyType(by_shortcut)
        self._accessible_shortcuts = MappingProxyType(
            {sequence: intent.action_id for sequence, intent in by_shortcut.items()}
        )

    def __len__(self):
        return len(self._intents)

    def __iter__(self):
        return iter(self._intents)

    def get(self, action_id):
        """Return a cataloged intent, accessible or not, or None."""
        if type(action_id) is not str:
            raise KeyboardActionError("action id must be a string")
        return self._by_id.get(action_id)

    def resolve(self, shortcut):
        """Return the available intent bound to a shortcut, or None."""
        return self._by_shortcut.get(normalize_shortcut(shortcut))

    def is_accessible(self, action_id):
        """True only when the cataloged intent is available to the host."""
        intent = self.get(action_id)
        return bool(intent is not None and intent.available)

    def accessible_actions(self):
        """Tuple of available intents, in catalog order."""
        return tuple(intent for intent in self._intents if intent.available)

    def accessible_shortcuts(self):
        """Immutable shortcut-to-id mapping for available intents only."""
        return self._accessible_shortcuts

    def with_availability(self, action_id, available):
        """Return a new map; explicit rebuild replaces host-side state."""
        if type(available) is not bool:
            raise KeyboardActionError("availability must be a bool")
        if self.get(action_id) is None:
            raise KeyboardActionError("unknown keyboard action id")
        updated = [
            KeyboardActionIntent(intent.action_id, intent.label, intent.shortcut,
                                 available)
            if intent.action_id == action_id else intent
            for intent in self._intents
        ]
        return KeyboardActionMap(updated, max_actions=len(self._intents))
