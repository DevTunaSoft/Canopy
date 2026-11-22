"""Offline deterministic focus-navigation contract for Classic menus/launcher.

Pure-Python model of the keyboard focus declarations in
``prototype/classic/{Main,ShellMenuBar,LauncherOverlay}.qml``. It lets tests
verify focus order, modal focus traps and empty views without a display, Qt
runtime, polling or background services.

This is a verification model, not compiled Qt: it does not prove a running
desktop. Wire the same contract into the compiled application for runtime use.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple

MENU_NAMES: Tuple[str, ...] = ("File", "Edit", "View", "Go", "Window", "Help")
APPROVED_APPS: Tuple[str, ...] = (
    "Browser", "Mail", "Files", "Calendar",
    "Photos", "Music", "Terminal", "Settings",
)

# A focus state is (view name, target name) or None when nothing has focus.
FocusState = Optional[Tuple[str, str]]


class FocusContractError(ValueError):
    """Raised when a focus contract or a modal-trap rule is violated."""


@dataclass(frozen=True)
class FocusTarget:
    """One focusable element. ``name`` is unique inside its view."""

    name: str
    accessible_name: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class FocusView:
    """An ordered focus ring: menu bar, open menu, launcher overlay or grid."""

    name: str
    targets: Tuple[FocusTarget, ...] = ()
    initial: Optional[str] = None
    wraps: bool = True
    modal: bool = False

    def enabled_targets(self) -> Tuple[FocusTarget, ...]:
        return tuple(t for t in self.targets if t.enabled)


class FocusNavigator:
    """Deterministic focus traversal over a stack of :class:`FocusView` rings.

    Navigation always acts on the top view only. While a modal view is open a
    background view is neither navigable nor re-baseable, which is the trap.
    """

    def __init__(self, views: Mapping[str, FocusView]):
        self._views: Dict[str, FocusView] = dict(views)
        self._stack: list[str] = []
        self._cursor: Dict[str, Optional[int]] = {}
        self._trace: list[FocusState] = []
        for view_name, view in self._views.items():
            names = [t.name for t in view.targets]
            if len(names) != len(set(names)):
                raise FocusContractError(
                    "duplicate focus target in view %r" % view_name)

    @property
    def active_view(self) -> Optional[FocusView]:
        return self._views[self._stack[-1]] if self._stack else None

    @property
    def current(self) -> FocusState:
        if not self._stack:
            return None
        view = self.active_view
        enabled = view.enabled_targets()
        index = self._cursor.get(view.name)
        if index is None or not enabled or not 0 <= index < len(enabled):
            return None
        return (view.name, enabled[index].name)

    def trace(self) -> Tuple[FocusState, ...]:
        """Focus state after every operation, for determinism checks."""
        return tuple(self._trace)

    def set_base(self, name: str) -> FocusState:
        """Set the non-modal root view. Blocked while any modal is open."""
        if self._has_modal():
            raise FocusContractError("cannot replace base while a modal is open")
        self._require(name)
        self._stack = [name]
        self._cursor.setdefault(name, None)
        state = self.focus_initial()
        return state

    def push(self, name: str) -> FocusState:
        """Open an overlay view on top and focus its initial target."""
        self._require(name)
        self._stack.append(name)
        self._cursor.setdefault(name, None)
        return self.focus_initial()

    def pop(self) -> FocusState:
        """Close the top view. Restores the cursor below it."""
        if not self._stack:
            return None
        self._stack.pop()
        self._record()
        return self.current

    def escape(self) -> FocusState:
        """Escape closes the top overlay (Keys.onEscapePressed in QML)."""
        return self.pop()

    def focus_initial(self) -> FocusState:
        view = self.active_view
        if view is None:
            return None
        enabled = view.enabled_targets()
        if not enabled:
            self._cursor[view.name] = None
        else:
            names = [t.name for t in enabled]
            self._cursor[view.name] = (
                names.index(view.initial) if view.initial in names else 0)
        return self._record()

    def focus_next(self) -> FocusState:
        return self._step(1)

    def focus_previous(self) -> FocusState:
        return self._step(-1)

    def _step(self, delta: int) -> FocusState:
        view = self.active_view
        if view is None:
            return None
        enabled = view.enabled_targets()
        if not enabled:
            self._cursor[view.name] = None
            return self._record()
        index = self._cursor.get(view.name)
        if index is None:
            index = 0 if delta > 0 else len(enabled) - 1
        else:
            index += delta
            if index < 0 or index >= len(enabled):
                if view.wraps:
                    index %= len(enabled)
                else:
                    index = 0 if delta > 0 else len(enabled) - 1
        self._cursor[view.name] = index
        return self._record()

    def _record(self) -> FocusState:
        state = self.current
        self._trace.append(state)
        return state

    def _require(self, name: str) -> None:
        if name not in self._views:
            raise KeyError("unknown focus view %r" % name)

    def _has_modal(self) -> bool:
        return any(self._views[n].modal for n in self._stack)


def verify_focus_order(view: FocusView) -> Tuple[str, ...]:
    """Return sorted contract problems for one focus ring. Empty means valid."""
    problems = []
    names = [t.name for t in view.targets]
    if len(names) != len(set(names)):
        problems.append("duplicate target names")
    enabled = [t.name for t in view.enabled_targets()]
    if view.initial is not None:
        if view.initial not in names:
            problems.append("initial target missing")
        elif view.initial not in enabled:
            problems.append("initial target disabled")
    if view.wraps and len(enabled) > 1:
        start = enabled.index(view.initial) if view.initial in enabled else 0
        reached = set()
        index = start
        for _ in range(len(enabled)):
            reached.add(enabled[index])
            index = (index + 1) % len(enabled)
        if len(reached) != len(enabled):
            problems.append("focus order not fully reachable")
    return tuple(sorted(problems))


def classic_focus_views(
    filtered_apps: Sequence[str] = APPROVED_APPS,
) -> Dict[str, FocusView]:
    """Declared focus rings matched to the Classic QML object/accessible names.

    ``filtered_apps`` is the launcher's visible catalogue; pass an empty
    sequence to model the "No matching applications" view.
    """
    views: Dict[str, FocusView] = {
        "menu_bar": FocusView(
            "menu_bar",
            tuple(FocusTarget("%s menu" % name) for name in MENU_NAMES),
            wraps=True,
        ),
        "launcher": FocusView(
            "launcher",
            (FocusTarget("canopyLauncherSearch", "Search available preview applications"),
             FocusTarget("canopyLauncherGrid", "Application grid")),
            initial="canopyLauncherSearch",
            wraps=True,
            modal=True,
        ),
        "launcher_grid": FocusView(
            "launcher_grid",
            tuple(FocusTarget("Select " + app, "Select " + app)
                  for app in filtered_apps),
            wraps=True,
        ),
    }
    # Each open menu is its own modal ring of enabled items; separators and
    # the disabled "Current Files location" item are not focus targets.
    menu_items = {
        "File": ("canopyMenuFileOpen", "canopyMenuFileClose", "canopyMenuFileHome"),
        "Edit": ("canopyMenuEditFind", "canopyMenuEditClear"),
        "View": ("canopyMenuViewToggle", "canopyMenuViewFocusSearch"),
        "Go": ("canopyMenuGoBack", "canopyMenuGoUp", "canopyMenuGoHome"),
        "Window": ("canopyMenuWindowFiles", "canopyMenuWindowClose"),
        "Help": ("canopyMenuHelpApplications", "canopyMenuHelpAbout"),
    }
    for name, items in menu_items.items():
        views["menu_" + name.lower()] = FocusView(
            "menu_" + name.lower(),
            tuple(FocusTarget(item) for item in items),
            initial=items[0],
            wraps=True,
            modal=True,
        )
    return views


def deterministic_trace(
    views: Mapping[str, FocusView],
    commands: Sequence[object],
) -> Tuple[FocusState, ...]:
    """Replay commands on a fresh navigator and return its focus trace.

    Commands: ``'next'``, ``'previous'``, ``'initial'``, ``'pop'``,
    ``('set_base', name)`` or ``('push', name)``. Identical commands always
    produce an identical trace.
    """
    navigator = FocusNavigator(views)
    for command in commands:
        if command == "next":
            navigator.focus_next()
        elif command == "previous":
            navigator.focus_previous()
        elif command == "initial":
            navigator.focus_initial()
        elif command == "pop":
            navigator.pop()
        elif isinstance(command, tuple) and command[0] == "set_base":
            navigator.set_base(command[1])
        elif isinstance(command, tuple) and command[0] == "push":
            navigator.push(command[1])
        else:
            raise FocusContractError("unknown command %r" % (command,))
    return navigator.trace()
