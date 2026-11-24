"""One immutable, no-echo desktop-action launch preview for a host.

Pure data only: this composes the already-tested
``desktop_actions.parse_desktop_actions`` and
``launch_argv.build_launch_argv`` into one bounded fail-closed decision. It
never starts a process, opens a shell, reads files, polls or touches a desktop.

The record carries counts and fixed negative claims only. No action id, action
name, icon, Exec line or argv token is copied into it or its ``to_dict`` bridge.
Problem details from the parser are deliberately discarded, since they embed
the very ids a denial must not echo. Desktop Exec field codes (``%``) and shell
metacharacters are refused fail-closed: this preview never interprets an Exec
line as a command.
"""
from dataclasses import dataclass
from typing import Tuple

from canopy_features.apps.desktop_actions import parse_desktop_actions
from canopy_features.apps.launch_argv import (
    SHELL_METACHARACTERS,
    LaunchArgvError,
    build_launch_argv,
)

STATUS_READY = "READY"
STATUS_DENIED = "DENIED"

REASON_OK = "ok"
REASON_INVALID_INPUT = "invalid_input"
REASON_INVALID_ACTIONS = "invalid_actions"
REASON_UNAPPROVED_ACTION = "unapproved_action"
REASON_UNSAFE_EXEC = "unsafe_exec"
REASON_INVALID_ARGV = "invalid_argv"
REASON_SOURCE_DISAGREEMENT = "source_disagreement"

CLAIM_NO_PROCESS_LAUNCHED = "no_process_launched"
CLAIM_NO_VALUE_ECHO = "no_value_echo"
CLAIM_NO_SHELL_METACHARACTERS = "no_shell_metacharacters"
CLAIM_NO_FIELD_CODES = "no_field_codes"
CLAIM_NO_UNAPPROVED_ACTION = "no_unapproved_action"
CLAIM_NO_DESKTOP_CLAIM = "no_desktop_claim"

FIXED_CLAIMS = (
    CLAIM_NO_DESKTOP_CLAIM,
    CLAIM_NO_FIELD_CODES,
    CLAIM_NO_PROCESS_LAUNCHED,
    CLAIM_NO_SHELL_METACHARACTERS,
    CLAIM_NO_UNAPPROVED_ACTION,
    CLAIM_NO_VALUE_ECHO,
)

__all__ = [
    "CLAIM_NO_DESKTOP_CLAIM",
    "CLAIM_NO_FIELD_CODES",
    "CLAIM_NO_PROCESS_LAUNCHED",
    "CLAIM_NO_SHELL_METACHARACTERS",
    "CLAIM_NO_UNAPPROVED_ACTION",
    "CLAIM_NO_VALUE_ECHO",
    "FIXED_CLAIMS",
    "REASON_INVALID_ACTIONS",
    "REASON_INVALID_ARGV",
    "REASON_INVALID_INPUT",
    "REASON_OK",
    "REASON_SOURCE_DISAGREEMENT",
    "REASON_UNAPPROVED_ACTION",
    "REASON_UNSAFE_EXEC",
    "STATUS_DENIED",
    "STATUS_READY",
    "DesktopActionLaunchPreview",
    "compose_desktop_action_launch_preview",
]


@dataclass(frozen=True)
class DesktopActionLaunchPreview:
    """One bounded host decision; denials carry no source material.

    ``claims`` is the fixed tuple of negative claims only on a READY preview.
    Every count is a number, never a copied value.
    """

    status: str
    reason: str
    declared_count: int = 0
    action_count: int = 0
    argv_length: int = 0
    claims: Tuple[str, ...] = ()

    @property
    def ready(self):
        return self.status == STATUS_READY

    def to_dict(self):
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "status": self.status,
            "reason": self.reason,
            "declared_count": self.declared_count,
            "action_count": self.action_count,
            "argv_length": self.argv_length,
            "claims": list(self.claims),
        }


def _deny(reason):
    return DesktopActionLaunchPreview(STATUS_DENIED, reason)


def _allowed_ids(value):
    if isinstance(value, (str, bytes, bytearray, dict)):
        return None
    try:
        return frozenset(value)
    except TypeError:
        return None


def _exec_is_safe(actions):
    """Refuse field codes and shell syntax without echoing any Exec line."""
    for action in actions:
        line = action.exec_line
        if type(line) is not str or "%" in line:
            return False
        if any(char in SHELL_METACHARACTERS for char in line):
            return False
    return True


def compose_desktop_action_launch_preview(
    text, *, allowed_action_ids, executable, allowed_executables=None,
    arguments=(),
):
    """Compose one no-echo desktop-action launch preview; launch nothing.

    ``text`` feeds the tested action parser; ``executable``/``arguments`` feed
    the tested shell-free argv builder. Only ids present in the host allowlist
    may be approved, and every Exec line must be free of field codes and shell
    metacharacters. No caller value is copied into the returned record.
    """
    if type(text) is not str:
        return _deny(REASON_INVALID_INPUT)
    try:
        scan = parse_desktop_actions(text)
    except (TypeError, ValueError):
        return _deny(REASON_INVALID_INPUT)

    # Problem details embed action ids, so they are never carried forward.
    if not scan.ok:
        return _deny(REASON_INVALID_ACTIONS)

    allowed = _allowed_ids(allowed_action_ids)
    if allowed is None or not all(type(value) is str for value in allowed):
        return _deny(REASON_INVALID_INPUT)
    if (any(action_id not in allowed for action_id in scan.declared_ids)
            or any(action.action_id not in allowed for action in scan.actions)):
        return _deny(REASON_UNAPPROVED_ACTION)

    if not _exec_is_safe(scan.actions):
        return _deny(REASON_UNSAFE_EXEC)

    try:
        argv = build_launch_argv(
            executable, arguments, allowed_executables=allowed_executables)
    except (LaunchArgvError, TypeError, ValueError):
        return _deny(REASON_INVALID_ARGV)

    if type(argv) is not tuple or not argv or argv[0] != executable:
        return _deny(REASON_SOURCE_DISAGREEMENT)

    return DesktopActionLaunchPreview(
        status=STATUS_READY,
        reason=REASON_OK,
        declared_count=len(scan.declared_ids),
        action_count=len(scan.actions),
        argv_length=len(argv),
        claims=FIXED_CLAIMS,
    )
