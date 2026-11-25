"""Offline validation of portal-backed URI opening requests.

Pure policy gate for one request to open a URI through a desktop portal (for
example the freedesktop OpenURI portal). It never contacts a portal, starts an
app, opens sockets, polls, reads the filesystem or keeps state between calls.
The compiled Classic Qt application does not call this module yet.

Reason codes in ``UriDecision.reason``: empty, invalid_type, too_long,
invalid_encoding, control_character, whitespace, backslash,
invalid_percent_encoding, malformed, missing_scheme, invalid_scheme,
scheme_not_allowed, credentials, invalid_authority, invalid_port,
path_traversal. An allowed decision has reason "".

Script-bearing schemes (javascript, vbscript, data) are refused even if a
caller lists them. ``file`` is refused by default; a caller that adds it has
made a trust decision, but traversal inside its path is still refused.
"""

from dataclasses import dataclass
import re
from typing import FrozenSet
from urllib.parse import unquote, urlsplit

MAX_URI_BYTES = 4096
DEFAULT_ALLOWED_SCHEMES: FrozenSet[str] = frozenset({"http", "https", "mailto"})

_SCRIPT_SCHEMES = frozenset({"javascript", "vbscript", "data"})
_MAX_SCHEMES = 16
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\Z")
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True, slots=True)
class UriDecision:
    """Immutable answer; ``normalized`` is empty for every refusal."""

    allowed: bool
    scheme: str
    normalized: str
    reason: str = ""


def _deny(scheme: str, reason: str) -> UriDecision:
    return UriDecision(False, scheme, "", reason)


def _check_policy(allowed_schemes: FrozenSet[str]) -> FrozenSet[str]:
    if type(allowed_schemes) is not frozenset:
        raise TypeError("allowed_schemes must be a frozenset")
    if not allowed_schemes or len(allowed_schemes) > _MAX_SCHEMES:
        raise ValueError("allowed_schemes must hold 1 to 16 entries")
    for scheme in allowed_schemes:
        if type(scheme) is not str or not _SCHEME.fullmatch(scheme):
            raise ValueError("allowed_schemes entries must be valid scheme names")
    return frozenset(s.casefold() for s in allowed_schemes)


def _has_traversal(path: str) -> bool:
    """Detect parent segments after bounded percent decoding, on any platform."""
    for candidate in (path, unquote(path), unquote(unquote(path))):
        if ".." in candidate.replace("\\", "/").split("/"):
            return True
    return False


def validate_open_uri(
    uri: str,
    allowed_schemes: FrozenSet[str] = DEFAULT_ALLOWED_SCHEMES,
) -> UriDecision:
    """Decide whether one URI may be handed to a portal opener.

    A refusal carries a stable reason code and no URI text, so callers can log
    it without copying attacker-controlled content. Invalid policy arguments
    raise; invalid request URIs return an immutable refusal.
    """
    allowed = _check_policy(allowed_schemes)
    if type(uri) is not str:
        return _deny("", "invalid_type")
    if not uri:
        return _deny("", "empty")
    if len(uri) > MAX_URI_BYTES:
        return _deny("", "too_long")
    try:
        encoded = uri.encode("utf-8", "strict")
    except UnicodeError:
        return _deny("", "invalid_encoding")
    if len(encoded) > MAX_URI_BYTES:
        return _deny("", "too_long")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in uri):
        return _deny("", "control_character")
    if any(ch.isspace() for ch in uri):
        return _deny("", "whitespace")
    if "\\" in uri:
        return _deny("", "backslash")
    if _BAD_PERCENT.search(uri):
        return _deny("", "invalid_percent_encoding")
    try:
        parts = urlsplit(uri)
    except ValueError:
        return _deny("", "malformed")

    scheme = parts.scheme.casefold()
    if not scheme:
        return _deny("", "missing_scheme")
    if not _SCHEME.fullmatch(scheme):
        return _deny(scheme, "invalid_scheme")
    if scheme in _SCRIPT_SCHEMES or scheme not in allowed:
        return _deny(scheme, "scheme_not_allowed")
    if parts.username is not None or parts.password is not None:
        return _deny(scheme, "credentials")
    if scheme in ("http", "https") and (not parts.netloc or not parts.hostname):
        return _deny(scheme, "invalid_authority")
    try:
        parts.port
    except ValueError:
        return _deny(scheme, "invalid_port")
    if _has_traversal(parts.path):
        return _deny(scheme, "path_traversal")

    return UriDecision(True, scheme, scheme + uri[uri.index(":"):])
