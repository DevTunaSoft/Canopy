"""Residual: hostile-but-bounded string labels must not be valid switcher ids.

``_valid_id`` accepted every nonempty string of at most MAX_ID_LENGTH chars,
including controls, format characters, unpaired surrogates, private-use code
points, noncharacters and line/paragraph separators. Such a label cannot be
displayed or UTF-8 round-tripped, yet ``SwitcherState`` reported it as a
tracked, selectable window id -- a false switcher-valid claim.

Pure Python only; no Qt, window manager, desktop or visual behavior is claimed.
"""
import unicodedata
import unittest

from canopy_features.windows.switcher_state import SwitcherError, SwitcherState

# One non-printing scalar embedded in an otherwise ordinary, short label.
# Every label is far below MAX_ID_LENGTH; rejection must come from the
# character gate, not from the length bound.
HOSTILE_LABELS = {
    "Cc_escape": "Dev\x1bOps",
    "Cc_nul": "Dev\x00Ops",
    "Cf_zero_width_space": "Dev\u200bOps",
    "Cs_unpaired_surrogate": "Dev\ud800Ops",
    "Co_private_use": "Dev\ue000Ops",
    "Cn_noncharacter_bmp": "Dev\uffffOps",
    "Cn_noncharacter_astral": "Dev\U0001fffeOps",
    "Zl_line_separator": "Dev\u2028Ops",
    "Zp_paragraph_separator": "Dev\u2029Ops",
}

SAFE_LABELS = ("files.win", "Caf\u00e9", "\u7f51\u9875", "Terminal \u2192 1",
               "A" * 128, "My Window")


class HostileSwitcherLabelTests(unittest.TestCase):
    def test_hostile_bounded_labels_are_rejected_as_window_ids(self):
        for name, label in HOSTILE_LABELS.items():
            with self.subTest(name=name, category=unicodedata.category(label[3])):
                with self.assertRaises(SwitcherError):
                    SwitcherState([label], current=label)

    def test_hostile_label_never_becomes_an_active_selection(self):
        for name, label in HOSTILE_LABELS.items():
            with self.subTest(name=name):
                with self.assertRaises(SwitcherError):
                    state = SwitcherState([label, "safe"], current=label)
                    state.begin()
                    state.select(label)

    def test_unencodable_label_is_refused_at_the_boundary(self):
        label = "Dev\ud800Ops"
        with self.assertRaises(UnicodeEncodeError):
            label.encode("utf-8", "strict")  # precondition: not round-trippable
        with self.assertRaises(SwitcherError):
            SwitcherState([label])

    def test_plain_and_printable_international_labels_still_work(self):
        for label in SAFE_LABELS:
            with self.subTest(label=label[:16]):
                state = SwitcherState([label], current=label)
                self.assertEqual(state.begin(), label)
                self.assertTrue(state.active)
                self.assertIs(state.confirm(), label)
                self.assertEqual(state.current, label)

    def test_int_ids_and_exact_duplicate_detection_unchanged(self):
        state = SwitcherState([1, 2, 3], current=1)
        self.assertEqual(state.begin(), 1)
        self.assertEqual(state.select(3), 3)
        self.assertIs(state.confirm(), 3)
        with self.assertRaises(SwitcherError):
            SwitcherState([1, 1])
        with self.assertRaises(SwitcherError):
            SwitcherState(["a", "a"])


if __name__ == "__main__":
    unittest.main()
