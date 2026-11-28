"""Offline validation of accessible roles, labels and names in UI metadata.

The input is a plain list of metadata records, normally produced by a
UI-framework adapter. This module does not parse QML, start Qt, call AT-SPI or
touch the network. Clean metadata means the records are internally consistent;
it is not proof that a screen reader can navigate a running application.
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

# Role vocabulary follows the names used by the Classic Qt/QML source: buttons,
# menu items, text fields and the non-interactive decorations around them.
_CLASSIC_ROLES = frozenset({
    "alert", "button", "checkBox", "comboBox", "container", "dialog",
    "group", "image", "label", "link", "list", "listItem", "menu",
    "menuItem", "menuSeparator", "progressBar", "radioButton", "row",
    "scrollBar", "slider", "spinBox", "staticText", "switch", "tab",
    "tabItem", "table", "textField", "toolButton", "window",
})

# The native Qt/AT-SPI bridge in the Plasma session reports a different role
# vocabulary (verified in the captured 1920x1080/1200x750/760x500 AT-SPI trees).
# Rejecting those names as "unsupported" made this gate unable to validate real
# native metadata and hid genuine empty-name defects behind an INVALID_ROLE.
# Keep the Classic names intact and accept the native-only names as aliases.
NATIVE_ATSPI_ROLES = frozenset({
    "application", "check box", "filler", "frame", "label", "text",
})
KNOWN_ROLES = _CLASSIC_ROLES | NATIVE_ATSPI_ROLES

# Roles that convey an action or accept input. A screen reader cannot announce
# one of these without a usable accessible name.
INTERACTIVE_ROLES = frozenset({
    "button", "checkBox", "check box", "comboBox", "link", "listItem",
    "menuItem", "radioButton", "slider", "spinBox", "switch", "tab",
    "tabItem", "textField", "toolButton",
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

# Native AT-SPI publishes ordinary informative text as ``label`` and editable
# text as ``text``; both need names to be announced. They are kept out of
# INFORMATIVE_ROLES (whose exact Classic-only contents are pinned by existing
# tests) and added to the default name requirement here. ``named_roles=`` lets
# a caller replace the whole requirement set explicitly.
NATIVE_INFORMATIVE_ROLES = frozenset({"label", "text"})
DEFAULT_NAMED_ROLES = NAMED_ROLES | NATIVE_INFORMATIVE_ROLES


@dataclass(frozen=True)
class Issue:
    """One metadata defect. ``element`` is objectName or an elements[i] path."""

    element: str
    code: str
    message: str


def _identifier(element, index):
    if isinstance(element, Mapping):
        name = element.get("objectName")
        if isinstance(name, str) and name.strip():
            return name
    return "elements[{}]".format(index)


def _name_field(element):
    for key in ("name", "label"):
        if key in element:
            return key, element[key]
    return None, None


def validate_metadata(elements, *, known_roles=KNOWN_ROLES,
                      interactive_roles=INTERACTIVE_ROLES,
                      informative_roles=INFORMATIVE_ROLES,
                      named_roles=None):
    """Return a list of :class:`Issue` for invalid accessible metadata.

    ``label`` is accepted as an alias for ``name``. A record needs a non-empty
    string name when its role is interactive or informative. Native AT-SPI
    ``label``/``text`` roles are informative too unless ``named_roles`` replaces
    the requirement set. Decorative art is excluded only by an explicit boolean
    ``ignored: true`` (Accessible.ignored); a non-boolean value fails closed and
    never grants the exemption. An interactive element marked ignored is
    reported as contradictory, so the gate cannot be cleared by blanket
    ignoring. Validation is pure: no global state, no I/O and no allocation
    beyond the returned issue list.

    This checks record consistency only. It does not read QML, start Qt, query
    AT-SPI or observe a screen reader, and a clean result is not an announcement
    or Linux Mint acceptance claim.
    """
    issues = []
    if named_roles is None:
        effective_named = (frozenset(interactive_roles)
                           | frozenset(informative_roles)
                           | NATIVE_INFORMATIVE_ROLES)
    else:
        effective_named = frozenset(named_roles)
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
                                "unsupported role: " + role))
            requires_name = False
        else:
            requires_name = role in effective_named

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
