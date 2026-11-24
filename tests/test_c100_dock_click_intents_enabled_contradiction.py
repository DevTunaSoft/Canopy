"""Regression tests for the dock click mapper's enabled/actionable contradiction.

Audit slice (tip 3c8ae8e): the mapper gates LAUNCH on the host's
``launcher_enabled`` flag but emits an actionable FOCUS intent for any label in
the ``running`` snapshot without consulting that flag. A host may legitimately
report a contradictory-but-bounded state -- launcher disabled, target running
(and possibly not installed) -- yet the mapper claims a valid click by
returning ``actionable is True``. The mapper must fail closed in that state.

All evidence here is SYNTHETIC: pure in-memory composition of the Python
mapper, no dock click, Qt signal, GIO call, desktop session or Mint guest was
exercised. Real compiled-Qt/Mint click handling remains NOT_RUN. No visual,
CI, docs or merge changes are involved.
"""

import unittest

from canopy_features.dock.click_intents import (
    APPROVED_DOCK_NAMES,
    ClickIntent,
    DockClickMapper,
    IntentKind,
)

FILES = "Files"
BROWSER = "Browser"


class DisabledLauncherContradictionTests(unittest.TestCase):
    def assert_no_valid_click(self, intent):
        self.assertIsInstance(intent, ClickIntent)
        self.assertFalse(intent.actionable,
                         "disabled launcher must not yield an actionable click")
        self.assertNotIn(intent.kind, (IntentKind.LAUNCH, IntentKind.FOCUS))

    def test_running_only_with_disabled_launcher_is_not_actionable(self):
        mapper = DockClickMapper(installed=(), running=(FILES,),
                                 launcher_enabled=False)
        intent = mapper.resolve(FILES)
        self.assert_no_valid_click(intent)
        self.assertEqual(intent.name, FILES)
        self.assertEqual(intent.reason, "launcher-disabled")

    def test_installed_and_running_with_disabled_launcher_not_actionable(self):
        mapper = DockClickMapper(installed=APPROVED_DOCK_NAMES,
                                 running=(FILES,), launcher_enabled=False)
        intent = mapper.resolve(FILES)
        self.assert_no_valid_click(intent)
        self.assertEqual(intent.reason, "launcher-disabled")

    def test_hostile_bounded_running_snapshot_still_not_actionable(self):
        # Duplicates, unknown labels and wrong types are bounded hostile input:
        # they are filtered, but must not re-enable a valid-click claim.
        mapper = DockClickMapper(installed=(BROWSER,),
                                 running=(FILES, FILES, "nope", 42, None, b"Files"),
                                 launcher_enabled=False)
        for _ in range(3):
            self.assert_no_valid_click(mapper.resolve(FILES))
        self.assertLessEqual(mapper.state_size, len(APPROVED_DOCK_NAMES))

    def test_observe_disabled_after_pending_launch_removes_focus_claim(self):
        mapper = DockClickMapper(installed=(FILES,), launcher_enabled=True)
        first = mapper.resolve(FILES)
        self.assertEqual(first.kind, IntentKind.LAUNCH)
        self.assertTrue(first.actionable)
        mapper.observe(launcher_enabled=False, running=(FILES,))
        self.assert_no_valid_click(mapper.resolve(FILES))


class DisabledLauncherPreservedBehaviorTests(unittest.TestCase):
    def test_enabled_launcher_focus_is_still_actionable(self):
        mapper = DockClickMapper(installed=(FILES,), running=(FILES,),
                                 launcher_enabled=True)
        intent = mapper.resolve(FILES)
        self.assertEqual(intent.kind, IntentKind.FOCUS)
        self.assertEqual(intent.reason, "running")
        self.assertTrue(intent.actionable)

    def test_disabled_installed_not_running_keeps_missing_target(self):
        mapper = DockClickMapper(installed=(FILES,), launcher_enabled=False)
        intent = mapper.resolve(FILES)
        self.assertEqual(intent.kind, IntentKind.REJECT)
        self.assertEqual(intent.reason, "missing-target")
        self.assertFalse(intent.actionable)

    def test_untrusted_id_still_rejected_under_disabled_launcher(self):
        mapper = DockClickMapper(installed=(FILES,), running=(FILES,),
                                 launcher_enabled=False)
        for hostile in (None, 123, "nope", "files", "Files;rm -rf /"):
            with self.subTest(hostile=repr(hostile)):
                intent = mapper.resolve(hostile)
                self.assertEqual(intent.kind, IntentKind.REJECT)
                self.assertEqual(intent.reason, "untrusted-id")
                self.assertEqual(intent.name, "")
                self.assertFalse(intent.actionable)


if __name__ == "__main__":
    unittest.main()
