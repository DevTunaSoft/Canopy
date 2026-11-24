"""Offline parsing and validation of freedesktop Desktop Action entries.

Pure Python: no I/O, no process launch, no polling, no privileged operation.
The caller supplies already-loaded Desktop Entry text; this module only reads
it and reports structural problems with action identifiers.

Scope: the action identifier used in ``Actions=`` and in
``[Desktop Action <id>]`` group headings. It does not validate GIO-qualified
ids such as ``org.example.App.desktop/new-window`` and proves no desktop,
launcher or Qt integration.
"""

import re
from dataclasses import dataclass
from typing import Dict, Tuple

MAX_ACTION_ID_LENGTH = 128
MAX_ACTIONS = 64

_ENTRY_GROUP = "Desktop Entry"
_ACTION_PREFIX = "Desktop Action "

# ASCII letters, digits, '-', '_', '.', '@'. No whitespace, ';', '=', '[',
# ']' or non-ASCII. Keeps ids safe for group headings and semicolon lists.
_VALID_ID = re.compile(r"[A-Za-z0-9._@-]{1,%d}\Z" % MAX_ACTION_ID_LENGTH)


@dataclass(frozen=True)
class DesktopAction:
    """One parsed ``[Desktop Action <id>]`` group."""

    action_id: str
    name: str
    exec_line: str
    icon: str


@dataclass(frozen=True)
class ActionProblem:
    """A structural validation finding. ``code`` is a stable machine value."""

    code: str
    detail: str


@dataclass(frozen=True)
class DesktopActionScan:
    declared_ids: Tuple[str, ...]
    actions: Tuple[DesktopAction, ...]
    problems: Tuple[ActionProblem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def is_valid_action_id(action_id: str) -> bool:
    """True for a non-empty, bounded, ASCII action identifier."""
    if not isinstance(action_id, str):
        return False
    return _VALID_ID.match(action_id) is not None


def parse_desktop_actions(text: str) -> DesktopActionScan:
    """Parse action declarations and groups, then report validation problems.

    ``shortcut:`` desktop-style multi-line continuation values are not joined;
    only single-line ``Actions=`` lists and group keys are considered. Upgrade
    if the caller can load real files with folded values.
    """
    # Require an exact str: a subclass can override splitlines() and either
    # hide declarations (a false action-safe scan) or yield wrong-type lines
    # that leak a raw AttributeError instead of this domain error.
    if type(text) is not str:
        raise TypeError("text must be str")

    declared = []
    groups = {}  # type: Dict[str, Dict[str, str]]
    group_order = []
    group_counts = {}  # type: Dict[str, int]
    section = None
    bounded = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section.startswith(_ACTION_PREFIX):
                action_id = section[len(_ACTION_PREFIX):].strip()
                if action_id in groups:
                    group_counts[action_id] += 1
                elif len(group_order) < MAX_ACTIONS:
                    groups[action_id] = {}
                    group_order.append(action_id)
                    group_counts[action_id] = 1
                else:
                    bounded = True
            continue
        if "=" not in line or section is None:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if section == _ENTRY_GROUP and key == "Actions":
            for item in value.split(";"):
                item = item.strip()
                if not item:
                    continue
                if len(declared) < MAX_ACTIONS:
                    declared.append(item)
                else:
                    bounded = True
        elif section.startswith(_ACTION_PREFIX):
            action_id = section[len(_ACTION_PREFIX):].strip()
            if action_id in groups:
                groups[action_id][key] = value

    problems = []
    if bounded:
        problems.append(ActionProblem(
            "too-many-actions", "limit of %d actions exceeded" % MAX_ACTIONS))

    declared_set = set()
    duplicate_declared = set()
    for action_id in declared:
        if not is_valid_action_id(action_id):
            problems.append(ActionProblem(
                "invalid-id", "declared action %r is not a valid id" % action_id))
        if action_id in declared_set:
            duplicate_declared.add(action_id)
        declared_set.add(action_id)
    for action_id in sorted(duplicate_declared):
        problems.append(ActionProblem(
            "duplicate-action", "Actions= lists %r more than once" % action_id))

    for action_id in group_order:
        if not is_valid_action_id(action_id):
            problems.append(ActionProblem(
                "invalid-id", "group heading %r is not a valid id" % action_id))
    for action_id in sorted(aid for aid, count in group_counts.items() if count > 1):
        problems.append(ActionProblem(
            "duplicate-action",
            "[%s%s] appears more than once" % (_ACTION_PREFIX, action_id)))

    for action_id in dict.fromkeys(declared):
        if action_id not in groups:
            problems.append(ActionProblem(
                "missing-group",
                "Actions= references %r with no [%s%s] group"
                % (action_id, _ACTION_PREFIX, action_id)))
    for action_id in group_order:
        if action_id not in declared_set:
            problems.append(ActionProblem(
                "orphan-group",
                "[%s%s] is not listed in Actions=" % (_ACTION_PREFIX, action_id)))
        if not groups[action_id].get("Exec", ""):
            problems.append(ActionProblem(
                "missing-exec", "action %r has no Exec" % action_id))

    actions = tuple(
        DesktopAction(
            action_id=action_id,
            name=groups[action_id].get("Name", ""),
            exec_line=groups[action_id].get("Exec", ""),
            icon=groups[action_id].get("Icon", ""),
        )
        for action_id in group_order
    )
    return DesktopActionScan(tuple(declared), actions, tuple(problems))
