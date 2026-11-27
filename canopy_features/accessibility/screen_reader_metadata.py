"""Offline validation of accessible roles, labels and names in UI metadata.

The input is a plain list of metadata records, normally produced by a
UI-framework adapter. This module does not parse QML, start Qt, call AT-SPI or
touch the network. Clean metadata means the records are internally consistent;
it is not proof that a screen reader can navigate a running application.

Caller-supplied ``objectName`` and ``role`` are untrusted display text. They are
projected through :func:`_bounded_projection` before entering an :class:`Issue`,
so reports stay bounded and printable without changing validation semantics.
"""

from collections.abc import Mapping
from dataclasses import dataclass

MISSING_LABEL = "missing-label"
EMPTY_NAME = "empty-name"
INVALID_NAME = "invalid-name"
INVALID_DESCRIPTION = "invalid-description"
INVALID_ROLE = "invalid-role"
INVALID_ELEMENT = "invalid-element"
INVALID_IGNORED = "invalid-ignored"
IGNORED_INTERACTIVE = "ignored-interactive"

# PE-119: caller-controlled objectName/role are untrusted report text. Keep a
# bounded printable prefix and replace every nonprintable scalar (Cc/Cf/Cs/
# Co/Cn/Zl/Zp, i.e. anything for which str.isprintable() is false) with a fixed
# token. Printable Unicode is retained so ordinary accessible metadata keeps
# its exact meaning; only hostile length/control characters are projected.
MAX_PROJECTION_CHARS = 120
UNPRINTABLE_TOKEN = "?"
PROJECTION_TRUNCATION_MARKER = "...[truncated]"

# Role vocabulary follows the names used by the Classic Qt/QML source: buttons,
# menu items, text fields and the non-interactive decorations around them.
KNOWN_ROLES = frozenset({
    "alert", "button", "checkBox", "comboBox", "container", "dialog",
    "group", "image", "label", "link", "list", "listItem", "menu",
    "menuItem", "menuSeparator", "progressBar", "radioButton", "row",
    "scrollBar", "slider", "spinBox", "staticText", "switch", "tab",
    "tabItem", "table", "textField", "toolButton", "window",
})

# Roles that convey an action or accept input. A screen reader cannot announce
# one of these without a usable accessible name.
INTERACTIVE_ROLES = frozenset({
    "button", "checkBox", "comboBox", "link", "listItem", "menuItem",
    "radioButton", "slider", "spinBox", "switch", "tab", "tabItem",
    "textField", "toolButton",
})

# Non-interactive roles that still convey information a screen reader must be
# able to announce (QA-005-005). They need an accessible name too. Purely
# decorative artwork is excluded explicitly with ``ignored: true``, the
# metadata equivalent of Accessible.ignored; it is never exempted by inference.
INFORMATIVE_ROLES = frozenset({
    "alert", "image", "staticText",
})

# Every role whose metadata is incomplete without a non-empty accessible name.
NAMED_ROLES = INTERACTIVE_ROLES | INFORMATIVE_ROLES


@dataclass(frozen=True)
class Issue:
    """One metadata defect. ``element`` is objectName or an elements[i] path."""

    element: str
    code: str
    message: str


def _bounded_projection(value):
    """Return a bounded printable projection of caller-controlled text.

    ``value`` must be a ``str``; both call sites gate the type first. Only the
    first ``MAX_PROJECTION_CHARS`` characters are retained, each nonprintable
    character becomes ``UNPRINTABLE_TOKEN``, and truncation is marked. The
    result is capped at ``MAX_PROJECTION_CHARS + len(marker)`` characters.
    """
    projected = "".join(
        char if char.isprintable() else UNPRINTABLE_TOKEN
        for char in value[:MAX_PROJECTION_CHARS]
    )
    if len(value) > MAX_PROJECTION_CHARS:
        projected += PROJECTION_TRUNCATION_MARKER
    return projected


def _identifier(element, index):
    if isinstance(element, Mapping):
        name = element.get("objectName")
        if isinstance(name, str) and name.strip():
            return _bounded_projection(name)
    return "elements[{}]".format(index)


def _name_field(element):
    for key in ("name", "label"):
        if key in element:
            return key, element[key]
    return None, None


def validate_metadata(elements, *, known_roles=KNOWN_ROLES,
                      interactive_roles=INTERACTIVE_ROLES,
                      informative_roles=INFORMATIVE_ROLES):
    """Return a list of :class:`Issue` for invalid accessible metadata.

    ``label`` is accepted as an alias for ``name``. A record needs a non-empty
    string name when its role is interactive *or* informative. Decorative art
    is excluded only by an explicit boolean ``ignored: true`` (Accessible.ignored);
    a non-boolean value fails closed and never grants the exemption. An
    interactive element marked ignored is reported as contradictory, so the
    gate cannot be cleared by blanket ignoring. Validation is pure: no global
    state, no I/O and no allocation beyond the returned issue list.

    This checks record consistency only. It does not read QML, start Qt, query
    AT-SPI or observe a screen reader, and a clean result is not an announcement
    or Linux Mint acceptance claim.
    """
    issues = []
    for index, element in enumerate(elements):
        where = _identifier(element, index)
        if not isinstance(element, Mapping):
            issues.append(Issue(where, INVALID_ELEMENT,
                                "element must be a mapping of metadata fields"))
            continue

        role = element.get("role")
        if not isinstance(role, str) or not role.strip():
            issues.append(Issue(where, INVALID_ROLE,
                                "role must be a non-empty string"))
            requires_name = False
        elif role not in known_roles:
            issues.append(Issue(where, INVALID_ROLE,
                                "unsupported role: "
                                + _bounded_projection(role)))
            requires_name = False
        else:
            requires_name = role in interactive_roles or role in informative_roles

        ignored = element.get("ignored", False)
        if "ignored" in element and not isinstance(ignored, bool):
            issues.append(Issue(where, INVALID_IGNORED,
                                "ignored must be an explicit boolean"))
        elif ignored:
            requires_name = False
            if role in interactive_roles:
                issues.append(Issue(where, IGNORED_INTERACTIVE,
                                    "interactive element must not be ignored"))

        key, name = _name_field(element)
        if key is None or name is None:
            if requires_name:
                issues.append(Issue(where, MISSING_LABEL,
                                    "element requires an accessible name"))
        elif not isinstance(name, str):
            issues.append(Issue(where, INVALID_NAME,
                                "accessible name must be a string"))
        elif not name.strip():
            if requires_name:
                issues.append(Issue(where, EMPTY_NAME,
                                    "accessible name is empty or whitespace"))

        if "description" in element and element["description"] is not None:
            if not isinstance(element["description"], str):
                issues.append(Issue(where, INVALID_DESCRIPTION,
                                    "accessible description must be a string"))

    return issues
