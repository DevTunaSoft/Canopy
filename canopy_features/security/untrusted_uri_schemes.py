"""Fail-closed scheme gate for URI launch intents from untrusted UI.

This is a pure, offline validator: it parses a single string, compares the
scheme against a host-owned allowlist, and returns. It performs no I/O, opens
no process, loads no QML, polls nothing and keeps no state. The compiled Qt
launcher must call ``validate_uri_intent`` at the trust boundary before any
GIO/Qt open call; this module itself never launches anything and is NOT
evidence of a wired desktop.
"""
import re
import unicodedata
from collections.abc import Mapping

# RFC 3986 scheme: ALPHA *( ALPHA / DIGIT / "+" / "-" / "." ).
# The fullmatch plus the leading-alpha rule stops "java script:", "1http:"
# and colon-lookalike tricks from ever yielding a scheme.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\Z")

DEFAULT_ALLOWED_SCHEMES = frozenset({"http", "https", "mailto"})
MAX_URI_CHARS = 2048

# Every Unicode "Other" category (Cc/Cf/Cs/Co/Cn) plus line/paragraph and
# space separators carries injection payloads or cannot be encoded safely.
# Omitting Cs/Co/Cn let lone surrogates, noncharacters and private-use code
# points pass the gate and raise a raw UnicodeEncodeError downstream.
_UNSAFE_CATEGORIES = frozenset({
    "Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs",
})


class UntrustedUriError(ValueError):
    """URI is not a well-formed intent with a permitted scheme."""


def _normalise_allowed(allowed):
    if allowed is None:
        allowed = DEFAULT_ALLOWED_SCHEMES
    if isinstance(allowed, (str, bytes, Mapping)):
        # A mapping is a wrong type for an allowlist: tuple(mapping) yields
        # only its KEYS and silently discards the values. A scheme listed with
        # a value of False (disabled) would be promoted into the allowlist and
        # produce a false "permitted"/"safe" claim. Fail closed instead.
        raise UntrustedUriError("allowlist must be a set of scheme strings")
    try:
        entries = tuple(allowed)
    except Exception as exc:
        # Any failure to materialise the untrusted config container is a
        # wrong-type input. Translate it to the domain error so neither the
        # validator nor the boolean wrapper leaks a raw built-in exception.
        raise UntrustedUriError("allowlist must be iterable") from exc
    if len(entries) > 64:
        raise UntrustedUriError("allowlist exceeds bound")
    normalised = set()
    for entry in entries:
        if type(entry) is not str or not _SCHEME.fullmatch(entry):
            raise UntrustedUriError("invalid scheme in allowlist")
        normalised.add(entry.casefold())
    return frozenset(normalised)


def validate_uri_intent(uri, *, allowed=DEFAULT_ALLOWED_SCHEMES):
    """Return the lowercase scheme of a permitted URI, else fail closed.

    ``allowed`` is host-owned configuration; callers cannot widen it through
    the URI string. Error messages never echo the rejected input.
    """
    permitted = _normalise_allowed(allowed)
    if type(uri) is not str:
        raise UntrustedUriError("URI intent must be a string")
    if not uri or len(uri) > MAX_URI_CHARS:
        raise UntrustedUriError("URI intent length is invalid")
    if any(unicodedata.category(ch) in _UNSAFE_CATEGORIES for ch in uri):
        raise UntrustedUriError("URI intent contains control or whitespace")

    separator = uri.find(":")
    if separator <= 0:
        raise UntrustedUriError("URI intent has no scheme")
    raw_scheme = uri[:separator]
    if not _SCHEME.fullmatch(raw_scheme):
        raise UntrustedUriError("URI scheme is malformed")

    scheme = raw_scheme.casefold()
    if scheme not in permitted:
        raise UntrustedUriError("URI scheme is not permitted")
    return scheme


def is_permitted_uri(uri, *, allowed=DEFAULT_ALLOWED_SCHEMES):
    """Boolean convenience wrapper around :func:`validate_uri_intent`."""
    try:
        validate_uri_intent(uri, allowed=allowed)
    except UntrustedUriError:
        return False
    return True
