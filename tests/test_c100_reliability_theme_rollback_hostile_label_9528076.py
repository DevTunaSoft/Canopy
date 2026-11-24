"""RED regression: hostile-but-bounded theme labels must fail closed.

The theme rollback ledger treats every non-empty ``str`` theme label as a
valid candidate identity.  Two bounded hostile labels break that claim:

  * a short label carrying a control, format, surrogate, private-use,
    unassigned or line/paragraph separator scalar is accepted and then
    projected as a clean, rollback-ready snapshot even though it cannot be
    displayed or encoded safely;
  * a ``str`` subclass whose ``__bool__``/``__iter__`` raises leaks that raw
    exception out of ``prepare`` instead of the documented ``INVALID_THEME``.

No Qt, compositor, Mint session, filesystem, process or compiled binary is
involved.  Every probe is finite and short.
"""

import unittest

from canopy_features.reliability.theme_transition_rollback import (
    IDLE,
    ThemeTransitionRollback,
)

_UNSAFE_LABELS = (
    "Ga\x1bme",      # Cc: escape control
    "Ga\x85me",      # Cc: C1 NEL
    "Ga\u200bme",    # Cf: zero-width space
    "Ga\u202eme",    # Cf: right-to-left override
    "Ga\ue000me",    # Co: private use
    "Ga\u2028me",    # Zl: line separator
    "Ga\u2029me",    # Zp: paragraph separator
    "Ga\u0378me",    # Cn: unassigned
    "Ga\ud800me",    # Cs: lone surrogate
)


class HostileBool(str):
    """Bounded string-like label with a hostile truthiness override."""

    def __bool__(self):
        raise RuntimeError("hostile bool")


class HostileIter(str):
    """Bounded string-like label with a hostile iteration override."""

    def __iter__(self):
        raise RuntimeError("hostile iter")


def make_ledger():
    return ThemeTransitionRollback("classic", ("theme.qml",))


class ThemeRollbackHostileLabelTests(unittest.TestCase):
    def test_unsafe_theme_label_is_refused_without_claiming_prepared(self):
        for label in _UNSAFE_LABELS:
            with self.subTest(label=ascii(label)):
                ledger = make_ledger()
                self.assertEqual(ledger.prepare(label, ("modern.qml",)),
                                 "INVALID_THEME")
                snap = ledger.snapshot()
                self.assertEqual(snap.state, IDLE)
                self.assertIsNone(snap.candidate)
                self.assertEqual(snap.live_resources, frozenset({"theme.qml"}))
                self.assertEqual(snap.abandoned_resources, frozenset())

    def test_unsafe_initial_theme_is_refused(self):
        for label in _UNSAFE_LABELS:
            with self.subTest(label=ascii(label)):
                with self.assertRaises(ValueError):
                    ThemeTransitionRollback(label, ("theme.qml",))

    def test_hostile_string_subclass_label_fails_closed(self):
        for label in (HostileBool("modern"), HostileIter("modern")):
            with self.subTest(label=type(label).__name__):
                ledger = make_ledger()
                self.assertEqual(ledger.prepare(label, ("modern.qml",)),
                                 "INVALID_THEME")
                self.assertEqual(ledger.snapshot().state, IDLE)

    def test_hostile_initial_theme_subclass_fails_closed(self):
        with self.assertRaises(ValueError):
            ThemeTransitionRollback(HostileBool("classic"), ("theme.qml",))
        with self.assertRaises(ValueError):
            ThemeTransitionRollback(HostileIter("classic"), ("theme.qml",))

    def test_rejected_label_leaves_ledger_retryable(self):
        ledger = make_ledger()
        self.assertEqual(ledger.prepare("Ga\u202eme", ("modern.qml",)),
                         "INVALID_THEME")
        self.assertEqual(ledger.prepare("modern", ("modern.qml",)), "PREPARED")
        self.assertEqual(ledger.commit(), "COMMITTED")
        self.assertEqual(ledger.snapshot().active, "modern")

    def test_legitimate_unicode_and_long_labels_still_work(self):
        for label in ("Caf\u00e9 / \u65e5\u672c\u8a9e", "x" * 500):
            with self.subTest(label=ascii(label[:16])):
                ledger = make_ledger()
                self.assertEqual(ledger.prepare(label, ("modern.qml",)),
                                 "PREPARED")
                self.assertEqual(ledger.snapshot().candidate, label)
                self.assertEqual(ledger.commit(), "COMMITTED")
                self.assertEqual(ledger.snapshot().active, label)


if __name__ == "__main__":
    unittest.main()
