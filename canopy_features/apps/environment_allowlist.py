"""Build minimal subprocess environments that cannot carry credentials.

Pure-Python, offline, host-owned helper. It does NOT start processes, poll,
open sockets, load QML, read files or touch the compiled Classic Qt prototype.
A trusted caller supplies an allowlist of variable names; this module copies
only those names from a source mapping (``os.environ`` by default) into a new
dict suitable for ``subprocess.Popen(env=...)``.

Credential-shaped names are refused even when they appear in the allowlist, so
a wide or mistaken allowlist cannot leak tokens, keys or passwords into a
child. Filtering is name-based: callers must not place secret VALUES inside an
otherwise ordinary variable name. This is distinct from
``canopy_core.host_events``, which filters event payload fields, not process
environments, and from the compiled GIO launcher, which inherits the full
parent environment today.

Limits are fixed and small: no polling, no background work, bounded memory.
"""
from collections.abc import Mapping
import os
import re

__all__ = [
    "CORE_ENV",
    "LINUX_GUI_ENV",
    "WINDOWS_GUI_ENV",
    "MAX_VARIABLES",
    "MAX_NAME_BYTES",
    "MAX_VALUE_BYTES",
    "EnvironmentAllowlistError",
    "build_environment",
]

MAX_VARIABLES = 64
MAX_NAME_BYTES = 128
MAX_VALUE_BYTES = 8192

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_()]*")
_SPLIT = re.compile(r"[^A-Za-z0-9]+")

# Substring matches catch concatenated forms such as GITHUBTOKEN and MYSECRET.
_STRONG_WORDS = frozenset({
    "token", "secret", "password", "passwd", "credential", "credentials",
    "apikey", "privatekey", "accesstoken", "refreshtoken", "passphrase",
})
# Exact word matches after splitting on non-alphanumeric separators.
# Short aliases matter as much as their long forms: a wide or mistaken
# allowlist must not copy DB_PASS, DB_PW or AWS_CRED into a child process.
_WORDS = _STRONG_WORDS | frozenset({
    "key", "api", "auth", "authorization", "cookie", "bearer", "pwd",
    "pass", "pw", "cred",
    "private", "signature", "cert", "certificate", "accesskey",
})

# Credential handles that are safe-looking names but grant access to secrets.
_NEVER_ALLOW = frozenset({
    "XAUTHORITY", "SSH_AUTH_SOCK", "SSH_AGENT_PID", "GPG_AGENT_INFO",
    "KRB5CCNAME",
})
# Match these handles case-insensitively. On Windows the process environment
# is case-insensitive, so a caller-supplied lowercase/title spelling resolves
# the very same value; a canonical-only check would copy the handle into the
# child and defeat this denylist. Fold once at import, then compare folded.
_NEVER_ALLOW_FOLDED = frozenset(name.casefold() for name in _NEVER_ALLOW)

# Trusted, conservative baselines. They contain no credential-shaped names.
CORE_ENV = frozenset({"PATH", "LANG", "LC_ALL", "TERM"})
LINUX_GUI_ENV = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "LC_ALL",
    "TERM", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "XDG_DATA_HOME",
    "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "QT_QPA_PLATFORMTHEME", "GDK_BACKEND",
})
WINDOWS_GUI_ENV = frozenset({
    "PATH", "SystemRoot", "SystemDrive", "ComSpec", "PATHEXT", "TEMP", "TMP",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
})


class EnvironmentAllowlistError(ValueError):
    """Invalid allowlist, source mapping or environment value."""


def _looks_sensitive(name):
    for part in _SPLIT.split(name):
        if not part:
            continue
        folded = part.casefold()
        if folded in _WORDS or any(word in folded for word in _STRONG_WORDS):
            return True
    return False


def _check_name(name):
    if type(name) is not str or not _NAME.fullmatch(name):
        raise EnvironmentAllowlistError("invalid environment variable name")
    if len(name) > MAX_NAME_BYTES:
        raise EnvironmentAllowlistError("environment variable name exceeds bound")
    if name.casefold() in _NEVER_ALLOW_FOLDED or _looks_sensitive(name):
        raise EnvironmentAllowlistError(
            "credential-shaped environment variable name refused")


def _check_value(value):
    if type(value) is not str:
        raise EnvironmentAllowlistError("environment value must be a string")
    if "\x00" in value:
        raise EnvironmentAllowlistError("environment value contains a NUL byte")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise EnvironmentAllowlistError("environment value is not valid UTF-8") from exc
    if len(encoded) > MAX_VALUE_BYTES:
        raise EnvironmentAllowlistError("environment value exceeds bound")


def build_environment(allow, source=None):
    """Return a new minimal env dict containing only allowlisted names.

    ``allow`` is a bounded iterable of trusted names. ``source`` is any mapping
    (``os.environ`` by default) and is never mutated. Sensitive names raise
    :class:`EnvironmentAllowlistError` instead of being silently copied.
    """
    if isinstance(allow, (str, bytes)) or not hasattr(allow, "__iter__"):
        raise EnvironmentAllowlistError("allowlist must be an iterable of names")
    names = tuple(allow)
    if len(names) > MAX_VARIABLES:
        raise EnvironmentAllowlistError("environment allowlist exceeds bound")
    unique = []
    seen = set()
    for name in names:
        _check_name(name)
        if name not in seen:
            seen.add(name)
            unique.append(name)

    if source is None:
        source = os.environ
    if not isinstance(source, Mapping):
        raise EnvironmentAllowlistError("source must be a mapping of variables")

    result = {}
    for name in unique:
        if name not in source:
            continue
        value = source[name]
        _check_value(value)
        result[name] = value
    return result
