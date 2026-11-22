"""Parse Desktop Entry ``Exec`` field codes into a safe argv list.

Small, standalone, offline component. It implements the quoting and field-code
rules from the freedesktop.org Desktop Entry Specification *without* invoking a
shell. Shell metacharacters found in an Exec value or in a supplied field value
stay literal data inside argv elements: no command substitution, variable
expansion, globbing, or re-tokenization ever happens.

Scope: this module does not read desktop files, launch programs, or touch the
compiled Classic Qt application. Wiring it into the shell is future work.
"""

# Whitespace that separates Exec arguments (space and tab per the spec).
_WS = " \t"

# Field codes from the Desktop Entry Specification.
# One value -> one argv element.
SINGLE_FIELD_CODES = frozenset("fudnckv")  # %f %u %d %n %c %k %v
# One sequence -> zero or more argv elements.
LIST_FIELD_CODES = frozenset("FUDNm")      # %F %U %D %N %m (m is deprecated)
# %i is special: it expands to two argv elements ("--icon", value), or none.
SUPPORTED_FIELD_CODES = frozenset(SINGLE_FIELD_CODES | LIST_FIELD_CODES | {"i"})


class ExecParseError(ValueError):
    """Malformed Exec value, unsupported field code, or bad field data."""


def _flush(buf, token):
    if buf:
        token.append(("text", "".join(buf)))
        buf.clear()


def _tokenize(exec_value):
    """Split ``exec_value`` into tokens of text / field-code parts.

    Quoting follows the Desktop Entry rules: a whole argument may be wrapped
    in double quotes; inside quotes only ``\\"`` is an escape, any other
    backslash is literal. Outside quotes every backslash is literal.
    """
    if not isinstance(exec_value, str):
        raise ExecParseError("Exec value must be a string")

    tokens = []
    token = []
    buf = []
    in_quotes = False
    token_started = False
    i = 0
    n = len(exec_value)

    while i < n:
        ch = exec_value[i]

        if ch in "\x00\n\r":
            raise ExecParseError("control character in Exec value")

        if ch in _WS and not in_quotes:
            _flush(buf, token)
            if token_started:
                tokens.append(token)
                token = []
                token_started = False
            i += 1
            continue

        if ch == '"':
            in_quotes = not in_quotes
            token_started = True
            i += 1
            continue

        if ch == "\\":
            # Only \" inside a quoted argument is an escape. Every other
            # backslash is a literal character (no shell-style escaping).
            if in_quotes and i + 1 < n and exec_value[i + 1] == '"':
                buf.append('"')
                i += 2
            else:
                buf.append("\\")
                i += 1
            token_started = True
            continue

        if ch == "%":
            if i + 1 >= n:
                raise ExecParseError("truncated field code")
            code = exec_value[i + 1]
            if code == "%":
                buf.append("%")
                i += 2
                token_started = True
                continue
            if code not in SUPPORTED_FIELD_CODES:
                raise ExecParseError("unsupported field code %" + code)
            _flush(buf, token)
            token.append(("field", code))
            token_started = True
            i += 2
            continue

        buf.append(ch)
        token_started = True
        i += 1

    if in_quotes:
        raise ExecParseError("unterminated quoted argument")
    _flush(buf, token)
    if token_started:
        tokens.append(token)

    if not tokens:
        raise ExecParseError("empty Exec value")
    return tokens


def _value(code, supplied):
    if not isinstance(supplied, str):
        raise ExecParseError(f"field %{code} value must be a string")
    if "\x00" in supplied or "\n" in supplied or "\r" in supplied:
        raise ExecParseError(f"control character in field %{code} value")
    return supplied


def _values(code, supplied):
    if isinstance(supplied, str):
        return [supplied]
    try:
        return list(supplied)
    except TypeError:
        raise ExecParseError(
            f"field %{code} value must be a string or a sequence"
        ) from None


def _expand(tokens, fields):
    """Turn parsed tokens into argv, expanding field codes as opaque data."""
    argv = []
    for parts in tokens:
        if len(parts) == 1 and parts[0][0] == "field":
            code = parts[0][1]
            if code == "i":
                icon = fields.get("i")
                if icon is not None and icon != "":
                    argv.extend(("--icon", _value("i", icon)))
                continue
            if code in LIST_FIELD_CODES:
                if code not in fields:
                    raise ExecParseError("missing field value %" + code)
                argv.extend(_value(code, v) for v in _values(code, fields[code]))
                continue
            if code not in fields:
                raise ExecParseError("missing field value %" + code)
            argv.append(_value(code, fields[code]))
            continue

        pieces = []
        for kind, payload in parts:
            if kind == "text":
                pieces.append(payload)
                continue
            code = payload
            if code == "i":
                raise ExecParseError("%i must be a whole argument")
            if code in LIST_FIELD_CODES:
                raise ExecParseError(f"list field %{code} cannot be embedded")
            if code not in fields:
                raise ExecParseError("missing field value %" + code)
            pieces.append(_value(code, fields[code]))
        argv.append("".join(pieces))
    return argv


def parse_exec(exec_value, *, fields=None):
    """Parse a Desktop Entry ``Exec`` value into a list of argv strings.

    ``fields`` maps a field-code letter to its value. Single codes
    (``f u d n c k v``) take a string; list codes (``F U D N m``) take a string
    (treated as one element) or a sequence of strings. The special code ``i``
    takes an icon string and expands to ``--icon <value>`` (or to nothing when
    the value is missing or empty). ``%%`` needs no value and yields ``%``.

    Field values are inserted as opaque data and are never parsed as shell
    input, so metacharacters cannot create new arguments or run commands.
    """
    if fields is None:
        fields = {}
    if not isinstance(fields, dict):
        raise ExecParseError("fields must be a mapping")
    return _expand(_tokenize(exec_value), fields)
