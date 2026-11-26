"""PE-062 regression: bounded Files-preview navigation history.

The Classic Files window keeps a back-stack of visited paths in
``FileModel``. On the audited base it appended on every ``navigate()`` and
``goUp()`` with no cap, so retained history grew linearly with browsing. This
locks the bounded contract: one explicit cap, one guarded write path used by
both mutators, oldest-first invalidation, and preserved recency/goBack
behavior.

Source-contract plus SYNTHETIC mirror: no Qt build, desktop, Mint session or
visual acceptance is claimed here. The compiled bounded synthetic probe lives
in scratch and is recorded separately with SHA-256.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "prototype" / "classic" / "FileModel.cpp"
HDR = ROOT / "prototype" / "classic" / "FileModel.h"


def back_stack_cap():
    match = re.search(
        r"static\s+constexpr\s+int\s+kMaxBackStack\s*=\s*(\d+)\s*;",
        HDR.read_text(encoding="utf-8"))
    return None if match is None else int(match.group(1))


class BoundedBackStackTests(unittest.TestCase):
    def test_cap_is_declared_and_bounded(self):
        cap = back_stack_cap()
        self.assertIsNotNone(cap, "FileModel.h must declare kMaxBackStack")
        self.assertGreater(cap, 0)
        self.assertLessEqual(cap, 64)

    def test_both_mutators_use_the_single_bounded_write_path(self):
        cpp = CPP.read_text(encoding="utf-8")
        self.assertEqual(cpp.count("m_backStack.append("), 1,
                         "only the bounded helper may append to history")
        helper = cpp[cpp.index("void FileModel::pushBackStack("):]
        helper = helper[:helper.index("\n}")]
        self.assertIn("m_backStack.append(path)", helper)
        self.assertIn("while (m_backStack.size() > kMaxBackStack)", helper)
        self.assertIn("m_backStack.removeFirst()", helper)
        # navigate() and goUp() must both route through the guarded helper.
        self.assertEqual(cpp.count("pushBackStack("), 3,
                         "one helper definition plus navigate/goUp call sites")
        callers = cpp.replace(helper, "")
        self.assertEqual(callers.count("pushBackStack(m_currentPath)"), 2)

    def test_synthetic_mirror_caps_history_and_preserves_recency(self):
        cap = back_stack_cap()
        self.assertIsNotNone(cap, "cap must exist before mirror semantics apply")
        history = []

        def push(path):
            history.append(path)
            while len(history) > cap:
                del history[0]  # explicit invalidation of the oldest entry

        for index in range(500):
            push("/home/probe/d{}".format(index))
        self.assertEqual(len(history), cap)
        self.assertEqual(history[-1], "/home/probe/d499")
        self.assertEqual(history[0], "/home/probe/d{}".format(500 - cap))
        drained = []
        while history:
            drained.append(history.pop())
        self.assertEqual(len(drained), cap)
        self.assertEqual(drained[0], "/home/probe/d499")


if __name__ == "__main__":
    unittest.main()
