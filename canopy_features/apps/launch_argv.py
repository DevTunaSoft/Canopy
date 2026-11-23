"""Shell-free argv builder for validated application launches.

Pure and offline: returns an immutable argv tuple for a caller to hand to a
process spawner with shell execution disabled. This module never spawns a
process, opens a shell, polls, uses the network or loads Shell Pack code.

Trust boundary: app discovery and the host allowlist belong to the caller.
The compiled Qt Classic launcher already applies a fixed dock-name to
desktop-ID allowlist and uses GIO. This module only guarantees that every
emitted token is a plain, bounded, shell-free string, so a shell command
string or an injected token cannot pass as a validated launch.
"""
from collections.abc import Iterable
import re

MAX_ARGUMENTS = 64
MAX_TOKEN_BYTES = 4096
MAX_ARGV_BYTES = 16384

# Conservative on purpose: a validated launch never needs shell syntax.
# Rejecting these fail-closed catches "app; rm -rf /" and "$(...)" input
# before any argv tuple is produced.
SHELL_METACHARACTERS = frozenset(
    ";&|<>"
    "()$`\\\"'*?[]{}!~#"
    "\n\r\t\x00"
)

DESKTOP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.desktop\Z")


class LaunchArgvError(ValueError):
    """Empty, oversized, shell-shaped or non-plain launch input."""


def _plain_token(value, label):
    if type(value) is not str:
        raise LaunchArgvError(f"{label} must be a string")
    if not value:
        raise LaunchArgvError(f"{label} is empty")
    for ch in value:
        if ch in SHELL_METACHARACTERS:
            raise LaunchArgvError(f"{label} contains a shell metacharacter")
        code = ord(ch)
        if code < 0x20 or code == 0x7f:
            raise LaunchArgvError(f"{label} contains a control character")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError as exc:
        raise LaunchArgvError(f"{label} is not valid Unicode") from exc
    if size > MAX_TOKEN_BYTES:
        raise LaunchArgvError(f"{label} exceeds byte bound")
    return value, size


def _argument_tokens(arguments):
    if isinstance(arguments, (str, bytes, bytearray, dict)) or not isinstance(arguments, Iterable):
        raise LaunchArgvError("arguments must be an iterable of strings")
    tokens = []
    for index, value in enumerate(arguments):
        if index >= MAX_ARGUMENTS:
            raise LaunchArgvError("too many arguments")
        tokens.append(_plain_token(value, f"argument {index}")[0])
    return tokens


def _check_allowlist(value, allowed, label):
    if isinstance(allowed, (str, bytes, bytearray, dict)) or not isinstance(allowed, Iterable):
        raise LaunchArgvError(f"{label} must be a collection of strings")
    if value not in set(allowed):
        raise LaunchArgvError(f"{label} is not approved by the host")


def _assemble(argv):
    total = sum(len(token.encode("utf-8", "strict")) for token in argv)
    if total > MAX_ARGV_BYTES:
        raise LaunchArgvError("argv exceeds total byte bound")
    return tuple(argv)


def build_launch_argv(executable, arguments=(), *, allowed_executables=None):
    """Return a shell-free argv tuple for an already-validated executable."""
    executable, _ = _plain_token(executable, "executable")
    if not executable.strip():
        raise LaunchArgvError("executable is blank")
    if allowed_executables is not None:
        _check_allowlist(executable, allowed_executables, "executable")
    return _assemble([executable, *_argument_tokens(arguments)])


def gio_launch_argv(app_id, arguments=(), *, allowed_app_ids=None):
    """Return a shell-free argv that launches a validated desktop ID via GIO.

    Reuses the GIO launcher mechanism of the compiled Qt Classic port. This
    only builds tokens; it does not execute them and does not claim a desktop.
    """
    app_id, _ = _plain_token(app_id, "app_id")
    if not DESKTOP_ID.fullmatch(app_id):
        raise LaunchArgvError("app_id is not a desktop ID")
    if allowed_app_ids is not None:
        _check_allowlist(app_id, allowed_app_ids, "app_id")
    return _assemble(["gio", "launch", "--", app_id, *_argument_tokens(arguments)])
