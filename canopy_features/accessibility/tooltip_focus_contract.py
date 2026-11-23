"""Offline tooltip-focus contract for Canopy Classic accessibility.

The compiled Classic Qt controls bind ``ToolTip.visible: hovered`` in
DockTile.qml, LauncherOverlay.qml and PreviewWindow.qml. A pointer-only binding
hides tooltip text from keyboard users. This module states the intended
contract as pure decision logic: a tooltip is visible on pointer hover OR
active keyboard focus, and disappears once both are gone. Accessible name and
description stay available to screen readers even when no tooltip shows.

This is a specification model. It imports no Qt, opens no window, polls
nothing, and proves no compiled-Qt or Linux Mint behavior. Changing the QML
bindings to INTENDED_QML_BINDING is a separate integration task.
"""
from dataclasses import dataclass

CONTRACT_VERSION = 1

# Hover alone excludes keyboard users; focus alone covers them.
INTENDED_QML_BINDING = "ToolTip.visible: hovered || activeFocus"

MODELLED_QML_BINDINGS = (
    ("DockTile.qml", "ToolTip.visible: hovered"),
    ("LauncherOverlay.qml", "ToolTip.visible: hovered"),
    ("PreviewWindow.qml", "ToolTip.visible: hovered"),
)

MAX_NAME_LENGTH = 256
MAX_DESCRIPTION_LENGTH = 512
MAX_ROLE_LENGTH = 64

ROLE_BUTTON = "button"


def _require_text(field, value, limit):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + " must be a non-empty string")
    if len(value) > limit:
        raise ValueError(field + " exceeds " + str(limit) + " characters")
    return value


@dataclass(frozen=True)
class TooltipInput:
    """One control's event state. Holds no history between calls."""

    hovered: bool
    active_focus: bool
    enabled: bool = True
    has_text: bool = True

    def __post_init__(self):
        for field in ("hovered", "active_focus", "enabled", "has_text"):
            if type(getattr(self, field)) is not bool:
                raise TypeError(field + " must be a bool")


@dataclass(frozen=True)
class TooltipSemantics:
    """Result of applying the contract to one control state."""

    visible: bool
    via_pointer: bool
    via_keyboard: bool
    role: str
    accessible_name: str
    accessible_description: str

    @property
    def screen_reader_label(self):
        """Accessible label; independent of visual tooltip visibility."""
        return "; ".join(
            part for part in (self.accessible_name, self.accessible_description)
            if part
        )


def tooltip_visible(state):
    """Return True only when a tooltip should be shown for this state."""
    if not isinstance(state, TooltipInput):
        raise TypeError("state must be a TooltipInput")
    return state.enabled and state.has_text and (state.hovered or state.active_focus)


def describe_tooltip(state, *, accessible_name, accessible_description="",
                     role=ROLE_BUTTON):
    """Describe visibility and accessible semantics for one control state."""
    if not isinstance(state, TooltipInput):
        raise TypeError("state must be a TooltipInput")
    _require_text("accessible_name", accessible_name, MAX_NAME_LENGTH)
    if not isinstance(accessible_description, str):
        raise ValueError("accessible_description must be a string")
    if len(accessible_description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError("accessible_description exceeds limit")
    _require_text("role", role, MAX_ROLE_LENGTH)
    visible = tooltip_visible(state)
    return TooltipSemantics(
        visible=visible,
        via_pointer=visible and state.hovered,
        via_keyboard=visible and state.active_focus,
        role=role,
        accessible_name=accessible_name,
        accessible_description=accessible_description,
    )
