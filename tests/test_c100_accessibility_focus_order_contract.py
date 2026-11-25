"""Unit tests for the offline Classic focus-order contract.

Pure-Python, offline. No Qt runtime, display or Mint claim is made here.
"""
import unittest
from pathlib import Path

from canopy_features.accessibility import focus_order_contract as foc

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"
MAIN_QML = (ROOT / "Main.qml").read_text(encoding="utf-8")
MENU_QML = (ROOT / "ShellMenuBar.qml").read_text(encoding="utf-8")
LAUNCHER_QML = (ROOT / "LauncherOverlay.qml").read_text(encoding="utf-8")


class FocusOrderContractTests(unittest.TestCase):
    def setUp(self):
        self.views = foc.classic_focus_views()
        self.nav = foc.FocusNavigator(self.views)

    # ---- grounding: the model matches the real compiled QML declarations ----
    def test_contract_names_exist_in_qml_source(self):
        self.assertIn('model: ["File", "Edit", "View", "Go", "Window", "Help"]',
                      MAIN_QML)
        self.assertIn('Accessible.name: modelData + " menu"', MAIN_QML)
        for name in foc.MENU_NAMES:
            with self.subTest(menu=name):
                self.assertIn('case "%s": return %sMenu' % (name, name.lower()),
                              MENU_QML)
        for name in ("canopyLauncherSearch", "canopyLauncherGrid"):
            with self.subTest(objectName=name):
                self.assertIn('objectName: "%s"' % name, LAUNCHER_QML)
        self.assertIn('Accessible.name: "Select " + modelData.title', LAUNCHER_QML)
        self.assertIn("forceActiveFocus()", LAUNCHER_QML)
        self.assertIn("keyNavigationWraps: true", LAUNCHER_QML)
        self.assertIn("Keys.onBacktabPressed: searchField.forceActiveFocus()",
                      LAUNCHER_QML)

    def test_all_declared_contracts_are_valid(self):
        for name, view in self.views.items():
            with self.subTest(view=name):
                self.assertEqual(foc.verify_focus_order(view), ())

    # ---- deterministic menu navigation ----
    def test_menu_bar_tab_order_is_deterministic(self):
        commands = [("set_base", "menu_bar")] + ["next"] * len(foc.MENU_NAMES)
        trace = foc.deterministic_trace(self.views, commands)
        self.assertEqual(trace, foc.deterministic_trace(self.views, commands))
        focused = [state[1] for state in trace[1:]]
        self.assertEqual(focused, ["Edit menu", "View menu", "Go menu",
                                   "Window menu", "Help menu", "File menu"])
        # wraps back to the first menu after the last
        self.assertEqual(trace[-1], ("menu_bar", "File menu"))

    def test_open_menu_starts_at_first_item_and_skips_disabled(self):
        self.nav.set_base("menu_bar")
        self.nav.push("menu_view")
        self.assertEqual(self.nav.current, ("menu_view", "canopyMenuViewToggle"))
        self.nav.focus_next()
        self.assertEqual(self.nav.current,
                         ("menu_view", "canopyMenuViewFocusSearch"))
        self.nav.focus_next()  # wraps, never reaches disabled location item
        self.assertEqual(self.nav.current,
                         ("menu_view", "canopyMenuViewToggle"))
        names = [t.name for t in self.views["menu_view"].targets]
        self.assertNotIn("canopyMenuViewPath", names)

    def test_backward_navigation_wraps_to_last(self):
        commands = [("set_base", "menu_bar"), "previous", "previous"]
        self.assertEqual(
            foc.deterministic_trace(self.views, commands)[-1],
            ("menu_bar", "Window menu"))

    # ---- launcher focus order ----
    def test_launcher_opens_on_search_field(self):
        self.nav.set_base("menu_bar")
        self.assertEqual(self.nav.push("launcher"),
                         ("launcher", "canopyLauncherSearch"))
        self.nav.focus_next()
        self.assertEqual(self.nav.current, ("launcher", "canopyLauncherGrid"))
        self.nav.focus_next()  # wraps back to search, does not leave launcher
        self.assertEqual(self.nav.current, ("launcher", "canopyLauncherSearch"))

    def test_launcher_grid_uses_accessible_names_and_wraps(self):
        self.nav.set_base("menu_bar")
        self.nav.push("launcher")
        self.nav.push("launcher_grid")
        self.assertEqual(self.nav.current, ("launcher_grid", "Select Browser"))
        for _ in range(len(foc.APPROVED_APPS) - 1):
            self.nav.focus_next()
        self.assertEqual(self.nav.current, ("launcher_grid", "Select Settings"))
        self.nav.focus_next()
        self.assertEqual(self.nav.current, ("launcher_grid", "Select Browser"))

    # ---- modal traps (explicit) ----
    def test_modal_trap_keeps_focus_inside_launcher(self):
        self.nav.set_base("menu_bar")
        self.nav.push("launcher")
        for _ in range(40):
            self.nav.focus_next()
            self.assertEqual(self.nav.active_view.name, "launcher")
        with self.assertRaises(foc.FocusContractError):
            self.nav.set_base("menu_bar")
        self.assertEqual(self.nav.active_view.name, "launcher")

    def test_escape_closes_modal_and_restores_background_focus(self):
        self.nav.set_base("menu_bar")
        self.nav.focus_next()  # Edit menu focused in background
        background = self.nav.current
        self.nav.push("menu_file")
        self.assertEqual(self.nav.active_view.name, "menu_file")
        self.nav.escape()
        self.assertEqual(self.nav.current, background)
        self.assertEqual(self.nav.active_view.name, "menu_bar")

    def test_empty_modal_traps_without_focus_leak(self):
        empty_views = foc.classic_focus_views(filtered_apps=[])
        nav = foc.FocusNavigator(empty_views)
        nav.set_base("menu_bar")
        nav.focus_next()
        nav.push("launcher")
        nav.push("launcher_grid")  # zero visible applications
        self.assertEqual(nav.current, None)
        for _ in range(10):
            nav.focus_next()
            nav.focus_previous()
            self.assertEqual(nav.current, None)
            self.assertEqual(nav.active_view.name, "launcher_grid")
        nav.escape()  # back to launcher, still trapped
        self.assertEqual(nav.active_view.name, "launcher")
        self.assertEqual(nav.current, ("launcher", "canopyLauncherSearch"))

    # ---- empty views (explicit) ----
    def test_empty_view_navigation_is_noop(self):
        empty = foc.FocusView("empty", (), modal=True)
        nav = foc.FocusNavigator({"empty": empty})
        self.assertIsNone(nav.set_base("empty"))
        self.assertIsNone(nav.focus_next())
        self.assertIsNone(nav.focus_previous())
        self.assertIsNone(nav.focus_initial())
        self.assertEqual(foc.verify_focus_order(empty), ())
        self.assertEqual(nav.current, None)

    def test_empty_launcher_filter_produces_no_delegates(self):
        grid = foc.classic_focus_views(filtered_apps=[])["launcher_grid"]
        self.assertEqual(grid.targets, ())
        self.assertEqual(grid.enabled_targets(), ())
        self.assertIn("No matching applications", LAUNCHER_QML)

    # ---- verifier negative controls ----
    def test_verifier_rejects_broken_contracts(self):
        duplicate = foc.FocusView(
            "dup", (foc.FocusTarget("a"), foc.FocusTarget("a")))
        self.assertIn("duplicate target names", foc.verify_focus_order(duplicate))
        missing_initial = foc.FocusView(
            "init", (foc.FocusTarget("a"),), initial="b")
        self.assertIn("initial target missing",
                      foc.verify_focus_order(missing_initial))
        disabled_initial = foc.FocusView(
            "dis", (foc.FocusTarget("a", enabled=False),), initial="a")
        self.assertIn("initial target disabled",
                      foc.verify_focus_order(disabled_initial))
        with self.assertRaises(foc.FocusContractError):
            foc.FocusNavigator({"dup": duplicate})


if __name__ == "__main__":
    unittest.main()
