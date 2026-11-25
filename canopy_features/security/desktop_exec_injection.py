"""Reject unsafe executable field expansion and shell calls before launch.

Pure, offline validation of a desktop-entry style ``Exec`` string. It returns
an immutable argv tuple only for a conservative printable-ASCII subset. It
never starts a process, opens a shell, expands variables or field codes,
resolves paths, reads files or changes the environment.

Scope: a boundary check for a future host-side launcher. A passing result
does not prove that the executable exists, is trustworthy or will start.
"""
import re

MAX_FIELD_CHARS = 1024
MAX_TOKENS = 64
MAX_TOKEN_CHARS = 256

_ARGUMENT = re.compile(r"[A-Za-z0-9_@+=:,./-]+\Z")

# Checked in order so every rejected field has one deterministic reason.
_UNSAFE = (
    ("'", "quote"),
    ('"', "quote"),
    ("`", "substitution"),
    ("$", "substitution"),
    ("%", "field code expansion"),
    (">", "redirect"),
    ("<", "redirect"),
    ("|", "pipe"),
    (";", "command chaining"),
    ("&", "command chaining"),
    ("*", "glob expansion"),
    ("?", "glob expansion"),
    ("[", "glob expansion"),
    ("]", "glob expansion"),
    ("{", "brace expansion"),
    ("}", "brace expansion"),
    ("~", "tilde expansion"),
    ("\\", "escape sequence"),
    ("(", "shell grouping"),
    (")", "shell grouping"),
    ("!", "history expansion"),
    ("#", "comment"),
)

# Shells, interpreters and exec wrappers are never a trusted final executable.
_DENIED_EXECUTABLES = frozenset({
    "sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh", "fish",
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh",
    "python", "python3", "perl", "ruby", "node", "lua", "php",
    "env", "xargs", "sudo", "nohup", "nice", "timeout", "exec",
})


class UnsafeExecError(ValueError):
    """Exec field rejected before launch; ``reason`` names the category."""

    def __init__(self, reason):
        self.reason = reason
        # Message carries only the category, never the rejected field.
        super().__init__("unsafe exec field: " + reason)


def validate_exec(field):
    """Return an immutable argv tuple, or raise ``UnsafeExecError``.

    Splitting is on ASCII spaces only; no quote or escape parsing occurs.
    """
    if type(field) is not str:
        raise UnsafeExecError("field must be a string")
    if not field or len(field) > MAX_FIELD_CHARS:
        raise UnsafeExecError("empty or oversized field")
    # shortcut: printable ASCII only; add an explicit locale policy before
    # accepting non-ASCII desktop entries.
    if any(ord(char) < 0x21 or ord(char) > 0x7E
           for char in field.replace(" ", "")):
        raise UnsafeExecError("control or non-ASCII character")
    for chars, reason in _UNSAFE:
        if any(char in field for char in chars):
            raise UnsafeExecError(reason)
    tokens = tuple(token for token in field.split(" ") if token)
    if not tokens or len(tokens) > MAX_TOKENS:
        raise UnsafeExecError("invalid token count")
    if any(len(token) > MAX_TOKEN_CHARS or not _ARGUMENT.fullmatch(token)
           for token in tokens):
        raise UnsafeExecError("unsupported argument token")
    executable = tokens[0].rsplit("/", 1)[-1].lower()
    if executable in _DENIED_EXECUTABLES:
        raise UnsafeExecError("shell or interpreter call")
    return tokens


def is_safe_exec(field):
    """Boolean form of ``validate_exec`` for callers that need no argv."""
    try:
        validate_exec(field)
    except UnsafeExecError:
        return False
    return True
