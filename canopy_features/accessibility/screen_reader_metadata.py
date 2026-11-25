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
                      interactive_roles=INTERACTIVE_ROLES):
    """Return a list of :class:`Issue` for invalid accessible metadata.

    ``label`` is accepted as an alias for ``name``. A record needs a non-empty
    string name only when its role is interactive. Validation is pure: no
    global state, no I/O and no allocation beyond the returned issue list.
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
                                "unsupported role: " + role))
            requires_name = False
        else:
            requires_name = role in interactive_roles

        key, name = _name_field(element)
        if key is None or name is None:
            if requires_name:
                issues.append(Issue(where, MISSING_LABEL,
                                    "interactive element has no accessible name"))
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
