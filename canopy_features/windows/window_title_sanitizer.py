"""Bounded, display-safe labels derived from untrusted external window titles.

Pure, offline, deterministic helper. No Qt, sockets, timers, threads, polling,
services, background work or logging of raw titles. A future Shell Host adapter
can call this before an external title reaches a UI text element; this module
does not observe real desktop windows and is not wired into the Qt prototype.
"""

MAX_LABEL_CHARS = 64
FALLBACK_LABEL = "Untitled window"

# ASCII whitespace controls become word separators. Every other C0 control,
# DEL/C1, lone surrogate half and bidi override/isolate is unsafe in a label.
_ASCII_WHITESPACE = frozenset((0x09, 0x0a, 0x0b, 0x0c, 0x0d))


def _unsafe(codepoint):
    return (
        (codepoint < 0x20 and codepoint not in _ASCII_WHITESPACE)
        or 0x7f <= codepoint <= 0x9f
        or 0xd800 <= codepoint <= 0xdfff
        or 0x202a <= codepoint <= 0x202e
        or 0x2066 <= codepoint <= 0x2069
    )


def sanitize_window_title_label(title):
    """Return a short, safe UI label for an external window title.

    Removes control and bidi-spoofing code points, collapses whitespace and
    truncates to MAX_LABEL_CHARS. Never returns an empty string: malformed or
    fully sanitized-away input yields FALLBACK_LABEL. Output length is bounded
    independently of input size.
    """
    if type(title) is not str:
        return FALLBACK_LABEL
    chars = []
    space_pending = False
    for char in title:
        codepoint = ord(char)
        if _unsafe(codepoint):
            continue
        if char.isspace():
            if chars:
                space_pending = True
            continue
        if space_pending:
            chars.append(" ")
            space_pending = False
        chars.append(char)
        if len(chars) >= MAX_LABEL_CHARS:
            break
    return "".join(chars) or FALLBACK_LABEL
