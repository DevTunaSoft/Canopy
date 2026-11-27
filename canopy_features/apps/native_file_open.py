"""Build shell-free argv for native default-app opening of a local item.

Pure and offline: this module never spawns a process, interpolates a shell
command, mutates a file, uses the network or keeps state between calls. A
trusted host validates the caller's path here and hands the returned immutable
argv to its own spawn API with shell execution disabled. No desktop, Mint or
runtime behavior is claimed by this module.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import unicodedata
from typing import Optional

__all__ = [
    "APPROVED",
    "DEFAULT_HANDLERS",
    "DENIED",
    "HANDLER_GIO",
    "HANDLER_XDG_OPEN",
    "MAX_PATH_BYTES",
    "MAX_PATH_CHARS",
    "NativeOpenDecision",
    "build_native_open",
    "failure_feedback",
]

APPROVED = "APPROVED"
DENIED = "DENIED"

HANDLER_GIO = "gio"
HANDLER_XDG_OPEN = "xdg-open"
DEFAULT_HANDLER = HANDLER_GIO
DEFAULT_HANDLERS = (HANDLER_GIO, HANDLER_XDG_OPEN)

# "--" stops option parsing before the validated absolute path. xdg-open has
# no equivalent separator, but an absolute path cannot be read as an option.
_HANDLER_ARGV = {
    HANDLER_GIO: ("gio", "open", "--"),
    HANDLER_XDG_OPEN: ("xdg-open",),
}

REASON_OK = "ok"
REASON_HOME_UNAVAILABLE = "home_unavailable"
REASON_INVALID_PATH = "invalid_path"
REASON_EMPTY_PATH = "empty_path"
REASON_TOO_LONG = "too_long"
REASON_MISSING_TARGET = "missing_target"
REASON_UNSUPPORTED_TYPE = "unsupported_type"
REASON_OUTSIDE_HOME = "outside_home"
REASON_HANDLER_UNAVAILABLE = "handler_unavailable"

MAX_PATH_CHARS = 4096
MAX_PATH_BYTES = 8192

# Control, format, surrogate, private-use and unassigned scalars cannot be
# safely passed to a native handler; ordinary spaces in filenames are legal.
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

_FEEDBACK = {
    REASON_HOME_UNAVAILABLE: "Your home folder is unavailable; nothing was opened.",
    REASON_INVALID_PATH: "That item has an invalid path; nothing was opened.",
    REASON_EMPTY_PATH: "No file or folder was selected; nothing was opened.",
    REASON_TOO_LONG: "That item's path is too long; nothing was opened.",
    REASON_MISSING_TARGET: "That file or folder no longer exists; nothing was opened.",
    REASON_UNSUPPORTED_TYPE: "Only files and folders can be opened; nothing was opened.",
    REASON_OUTSIDE_HOME: "Only items in your home folder can be opened here.",
    REASON_HANDLER_UNAVAILABLE: "No supported default-app handler is available.",
}

# Host-side spawn failures use the same fixed, path-free message vocabulary.
_RUNTIME_FEEDBACK = {
    "handler_missing": "The default application handler is not installed.",
    "no_default_app": "No default application is configured for this item.",
    "permission_denied": "Permission was denied; nothing was opened.",
    "open_failed": "The system could not open this item.",
    "cancelled": "Opening this item was cancelled.",
    "unknown": "The item could not be opened for an unknown reason.",
}
_INVALID_REPORT_FEEDBACK = "The open failure report was not valid."
_UNRECOGNIZED_FEEDBACK = "The system reported an unrecognized open failure."


def failure_feedback(reason: object) -> str:
    """Return fixed user-facing text for a validation or spawn failure code.

    Untrusted text is never echoed: a wrong type or an unknown code gets its
    own generic message, so a hostile path cannot become a status string.
    """
    if type(reason) is not str:
        return _INVALID_REPORT_FEEDBACK
    if reason in _FEEDBACK:
        return _FEEDBACK[reason]
    if reason in _RUNTIME_FEEDBACK:
        return _RUNTIME_FEEDBACK[reason]
    return _UNRECOGNIZED_FEEDBACK


def _allowed_handlers(value) -> Optional[frozenset]:
    """Validate the host-owned handler allowlist, never echoing its entries."""
    if isinstance(value, (str, bytes, bytearray, dict, Mapping)):
        return None
    try:
        entries = tuple(value)
    except Exception:
        return None
    if not entries or len(entries) > len(_HANDLER_ARGV):
        return None
    if any(type(entry) is not str or entry not in _HANDLER_ARGV for entry in entries):
        return None
    return frozenset(entries)


@dataclass(frozen=True, slots=True)
class NativeOpenDecision:
    """Immutable host-facing result; argv exists only for an approval."""

    status: str
    reason: str
    handler: Optional[str] = None
    argv: Optional[tuple] = None
    target: Optional[str] = None
    kind: Optional[str] = None
    feedback: str = ""

    @property
    def approved(self):
        return self.status == APPROVED

    def to_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "handler": self.handler,
            "argv": None if self.argv is None else list(self.argv),
            "target": self.target,
            "kind": self.kind,
            "feedback": self.feedback,
        }


def _deny(reason: str) -> NativeOpenDecision:
    return NativeOpenDecision(DENIED, reason, feedback=_FEEDBACK[reason])


def _canonical_home(home) -> Optional[Path]:
    try:
        raw = Path.home() if home is None else Path(home).expanduser()
        root = raw.resolve(strict=True)
    except Exception:
        return None
    return root if root.is_dir() else None


def _candidate_text(path) -> Optional[str]:
    """Read caller input without letting hostile objects leak exceptions."""
    try:
        if type(path) is str:
            raw = path.strip()
        elif isinstance(path, os.PathLike):
            value = os.fspath(path)
            if type(value) is not str:
                return None
            raw = value.strip()
        else:
            return None
    except Exception:
        return None
    if not raw or len(raw) > MAX_PATH_CHARS:
        return None
    if any(unicodedata.category(ch) in _UNSAFE_CATEGORIES for ch in raw):
        return None
    try:
        encoded = raw.encode("utf-8", "strict")
    except UnicodeError:
        return None
    return raw if len(encoded) <= MAX_PATH_BYTES else None


def build_native_open(
    path: object,
    *,
    home: object = None,
    handler: str = DEFAULT_HANDLER,
    available_handlers=DEFAULT_HANDLERS,
) -> NativeOpenDecision:
    """Return a shell-free default-app argv for one existing local item."""
    root = _canonical_home(home)
    if root is None:
        return _deny(REASON_HOME_UNAVAILABLE)

    raw = _candidate_text(path)
    if raw is None:
        # Distinguish empty and oversized inputs from hostile/unsafe text so
        # the host can show a precise, actionable failure message.
        try:
            fspath = getattr(path, "__fspath__", None)
            value = path if type(path) is str else (
                fspath() if callable(fspath) else None)
        except Exception:
            value = None
        if type(value) is not str:
            return _deny(REASON_INVALID_PATH)
        if not value.strip():
            return _deny(REASON_EMPTY_PATH)
        if len(value.strip()) > MAX_PATH_CHARS:
            return _deny(REASON_TOO_LONG)
        return _deny(REASON_INVALID_PATH)

    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
    except (OSError, ValueError):
        return _deny(REASON_INVALID_PATH)
    try:
        resolved = candidate.resolve(strict=True)
    except RuntimeError:
        return _deny(REASON_INVALID_PATH)
    except (OSError, ValueError):
        return _deny(REASON_MISSING_TARGET)

    try:
        resolved.relative_to(root)
    except ValueError:
        return _deny(REASON_OUTSIDE_HOME)

    try:
        if resolved.is_dir():
            kind = "directory"
        elif resolved.is_file():
            kind = "file"
        else:
            return _deny(REASON_UNSUPPORTED_TYPE)
    except OSError:
        return _deny(REASON_MISSING_TARGET)

    allowed = _allowed_handlers(available_handlers)
    if allowed is None or type(handler) is not str or handler not in allowed:
        return _deny(REASON_HANDLER_UNAVAILABLE)

    # Plain tuple of separate tokens: no shell join, no interpolation. GIO's
    # "--" also prevents an absolute path from being read as an option.
    argv = _HANDLER_ARGV[handler] + (str(resolved),)
    return NativeOpenDecision(
        status=APPROVED,
        reason=REASON_OK,
        handler=handler,
        argv=argv,
        target=str(resolved),
        kind=kind,
    )
