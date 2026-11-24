"""Data-only handling for untrusted Canopy Shell Pack metadata.

This module turns an already-parsed, untrusted metadata mapping into an
immutable, display-safe value. It never executes, imports, opens, resolves,
downloads or runs anything named in the metadata. Its output keeps no
filesystem path, command, URI or callable: only scalar display strings.

It is a defense-in-depth boundary for metadata shown in settings, written to
logs or cached for later display. It is NOT a pack schema validator, installer,
signature check, sandbox, runtime loader or trust decision. The full v1 schema
check lives in ``tools.check_shell_pack.validate_pack``; the helper
:func:`safe_metadata_from_pack` runs that first, then projects the result here.

No background work, polling, file discovery or privileged action is performed.
"""


from dataclasses import dataclass
import re
import unicodedata
from typing import Any, FrozenSet, Mapping

from tools.check_shell_pack import (
    CAPABILITIES,
    NAME_CONTROL,
    PACK_ID,
    PackValidationError,
    validate_pack,
)


# Bounds keep a hostile mapping from growing memory or hiding payloads in
# deep nesting. They are intentionally small: display metadata needs little.
MAX_FIELDS = 64
MAX_DEPTH = 4
MAX_STRING_CHARS = 2_048
MAX_TOTAL_CHARS = 16_384
MAX_ID_CHARS = 128
MAX_NAME_CHARS = 80
MAX_DESCRIPTION_CHARS = 240

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# The ASCII-only control check misses bounded, hostile Unicode strings whose
# code points cannot be encoded (Cs surrogates), are undefined (Cn
# noncharacters), are private use (Co) or inject a line/paragraph break
# (Zl/Zp). Such a string passes the gate, survives into the projected display
# value and later raises a raw UnicodeEncodeError when written to a log or
# shown in settings. Fail closed at the boundary instead.
# Format characters (Cf) and ordinary spaces (Zs) are deliberately allowed:
# ZWJ/ZWNJ are legitimate in many scripts and spaces are valid display text.
_UNSAFE_UNICODE_CATEGORIES = frozenset({"Cs", "Co", "Cn", "Zl", "Zp"})


def _has_unsafe_unicode(value: str) -> bool:
    return any(unicodedata.category(char) in _UNSAFE_UNICODE_CATEGORIES
               for char in value)

# Executable-looking field names are rejected as keys, before any value is
# read. An exact token between separators avoids false positives on valid
# manifest keys such as "shell_api" or "entrypoint". The key is first folded
# to a canonical underscore form (see _normalize_key) so a hostile manifest
# cannot hide the same token behind a hyphen, a dot or camelCase.
_EXECUTABLE_KEY = re.compile(
    r"(?:^|_)(?:"
    r"exec|executable|command|cmd|script|run|hook|callback|spawn|launch|"
    r"process|binary|program|eval|code|module|import|subprocess|payload|"
    r"path|file|url|uri|argv|load"
    r")(?:$|_)",
    re.IGNORECASE,
)

_KEY_SEPARATOR = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")
_CAMEL_ACRONYM = re.compile(r"([A-Z])([A-Z][a-z])")


def _normalize_key(key: str) -> str:
    """Fold alternate key separators to the underscore form the rule expects.

    ``exec-path``, ``exec.path``, ``execPath`` and ``EXEC-PATH`` all become
    ``exec_path``. Non-separator spellings such as ``filepath`` are left as
    one token, keeping the rule's original no-false-positive behaviour.
    """
    folded = _CAMEL_LOWER_UPPER.sub(r"\1_\2", key)
    folded = _CAMEL_ACRONYM.sub(r"\1_\2", folded)
    return _KEY_SEPARATOR.sub("_", folded).strip("_").lower()

_URI = re.compile(
    r"^(?:[A-Za-z][A-Za-z0-9+.-]*://|(?:file|data|javascript|mailto):)",
    re.IGNORECASE,
)
_TRAVERSAL = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_UNC = re.compile(r"^\\\\")
_POSIX_ABSOLUTE = re.compile(r"^/")

# Prose-safe executable detection. Plain ';' or '&' are allowed in labels
# ("Files; Folders"), but command substitution, piping to a shell, chained
# commands, interpreter flags and command verbs are not.
_EXECUTABLE_VALUE = re.compile(
    r"(?:"
    r"`|\$\(|"
    r"&&|\|\||"
    r"\|\s*(?:sh|bash|cmd|powershell)\b|"
    r";\s*(?:rm|sh|bash|curl|wget|sudo|cat|touch|chmod|echo|python3?|powershell)\b|"
    r"\b(?:sh|bash|cmd|powershell|pwsh|python3?|perl|ruby|node)\s+-c\b|"
    r"\b(?:subprocess|os\.system|os\.popen|eval|exec)\b|"
    r"\b(?:rm|curl|wget|chmod|chown|sudo|mkfs|nc|ncat)\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SafePackMetadata:
    """Immutable, display-only projection of untrusted pack metadata.

    Holds only strings and a frozenset. No path, command, URI, callback or
    mutable container survives here. This is not an execution approval.
    """

    pack_id: str
    name: str
    description: str
    capabilities: FrozenSet[str]


def _check_string(value: str) -> None:
    if _CONTROL.search(value):
        raise PackValidationError("control character in metadata value")
    if _has_unsafe_unicode(value):
        raise PackValidationError("unsafe unicode character in metadata value")
    if _URI.match(value):
        raise PackValidationError("URI in metadata value")
    if _TRAVERSAL.search(value):
        raise PackValidationError("path traversal in metadata value")
    if _WINDOWS_ABSOLUTE.match(value) or _UNC.match(value) or _POSIX_ABSOLUTE.match(value):
        raise PackValidationError("absolute path in metadata value")
    if _EXECUTABLE_VALUE.search(value):
        raise PackValidationError("executable-looking metadata value")


def _scan(value: Any, depth: int, used: list) -> None:
    if depth > MAX_DEPTH:
        raise PackValidationError("metadata nesting is too deep")
    if isinstance(value, Mapping):
        if len(value) > MAX_FIELDS:
            raise PackValidationError("metadata has too many fields")
        for key, child in value.items():
            if not isinstance(key, str):
                raise PackValidationError("metadata keys must be strings")
            if _EXECUTABLE_KEY.search(_normalize_key(key)):
                raise PackValidationError(f"executable-looking metadata field: {key}")
            _scan(child, depth + 1, used)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_FIELDS:
            raise PackValidationError("metadata list is too long")
        for child in value:
            _scan(child, depth + 1, used)
        return
    if isinstance(value, str):
        used[0] += len(value)
        if used[0] > MAX_TOTAL_CHARS:
            raise PackValidationError("metadata content is too large")
        if len(value) > MAX_STRING_CHARS:
            raise PackValidationError("metadata string too long")
        _check_string(value)
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise PackValidationError("unsupported metadata value type")


def to_safe_metadata(manifest: Mapping[str, Any]) -> SafePackMetadata:
    """Project an untrusted metadata mapping into an immutable data-only value.

    The whole mapping is scanned first: any executable-looking field name or
    value, path traversal, absolute path, URI or control character anywhere
    fails closed. Only then are the four display fields extracted with strict
    types. No value is resolved as a path or interpreted as code.
    """
    if not isinstance(manifest, Mapping):
        raise PackValidationError("metadata must be a mapping")
    data = dict(manifest)
    _scan(data, 0, [0])

    pack_id = data.get("id")
    if (not isinstance(pack_id, str) or len(pack_id) > MAX_ID_CHARS
            or not PACK_ID.fullmatch(pack_id)
            or pack_id.startswith("org.canopy.")):
        raise PackValidationError("invalid or reserved pack id")

    strings = {}
    for key, maximum in (("name", MAX_NAME_CHARS),
                         ("description", MAX_DESCRIPTION_CHARS)):
        value = data.get(key)
        if (not isinstance(value, str) or not value or len(value) > maximum
                or value != value.strip() or NAME_CONTROL.search(value)):
            raise PackValidationError(f"invalid {key}")
        strings[key] = value

    capabilities = data.get("capabilities")
    # Require the exact ``str`` type, not just an ``isinstance`` match: a str
    # subclass may override __hash__/__eq__ (e.g. set __hash__ to None), so a
    # bare subclass instance can raise a raw TypeError at the ``in`` lookup or
    # while building the duplicate-detection set. Exact str is always
    # hashable, keeping hostile-but-bounded capability values on the domain
    # fail-closed path. This also covers duplicate IDs carried by such a
    # subclass: they must be rejected as invalid, not explode.
    if (not isinstance(capabilities, (list, tuple)) or not capabilities
            or any(type(cap) is not str or cap not in CAPABILITIES
                   for cap in capabilities)
            or len(set(capabilities)) != len(capabilities)):
        raise PackValidationError("invalid capabilities")

    return SafePackMetadata(
        pack_id=pack_id,
        name=strings["name"],
        description=strings["description"],
        capabilities=frozenset(capabilities),
    )


def safe_metadata_from_pack(pack_root) -> SafePackMetadata:
    """Validate a local pack directory with the v1 checker, then project it.

    Reuses ``tools.check_shell_pack.validate_pack`` so schema duplicates,
    malformed JSON, bad entrypoints and unknown fields are rejected before the
    data-only projection runs. Returns metadata only; never loads UI code.
    """
    return to_safe_metadata(validate_pack(pack_root))
