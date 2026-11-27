"""Source-contract tests for bounded forward navigation in Classic Files.

No Qt runtime is needed. These tests pin the compiled model's redo contract:
a QML-visible forward action, bounded history, a new branch clearing redo,
and fail-closed refusals that never carry a path into a log or QML binding.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"


class ClassicFilesForwardNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = (SOURCE / "FileModel.h").read_text(encoding="utf-8")
        cls.model = (SOURCE / "FileModel.cpp").read_text(encoding="utf-8")

    def test_forward_state_is_exposed_to_qml(self):
        self.assertIn(
            "Q_PROPERTY(bool canGoForward READ canGoForward NOTIFY navigationChanged)",
            self.header)
        self.assertIn(
            "bool canGoForward() const { return !m_forwardStack.isEmpty(); }",
            self.header)
        self.assertIn("Q_INVOKABLE bool goForward();", self.header)
        self.assertIn("QStringList m_forwardStack;", self.header)
        self.assertIn("bool FileModel::goForward()", self.model)

    def test_forward_history_is_bounded(self):
        self.assertIn("static constexpr int kMaxHistory = 64;", self.header)
        self.assertIn(
            "void pushBounded(QStringList &stack, const QString &path)", self.header)
        self.assertRegex(
            self.model, r"if \(stack\.size\(\) >= kMaxHistory\)\s*stack\.removeFirst\(\);")
        self.assertIn("stack.append(path);", self.model)

    def test_new_navigation_clears_forward_history(self):
        self.assertIn("m_forwardStack.clear();", self.model)
        # Both a fresh navigate() and an Up navigation start a new branch;
        # only Back/Forward may populate the redo stack.
        self.assertGreaterEqual(self.model.count("m_forwardStack.clear();"), 2)

    def test_back_and_forward_are_reversible(self):
        self.assertIn("pushBounded(m_forwardStack, m_currentPath);", self.model)
        self.assertIn("pushBounded(m_backStack, m_currentPath);", self.model)
        self.assertRegex(self.model, r"m_forwardStack\.(?:takeLast|removeLast)\(\)")
        self.assertIn("m_backStack.takeLast()", self.model)

    def test_forward_refusal_is_fixed_and_path_free(self):
        self.assertIn('navigationRejected(QStringLiteral("forward target unavailable"))',
                      self.model)
        for hostile in (".arg(", "%1", "m_currentPath)", "entry.path"):
            self.assertNotIn(hostile, self.model.split("bool FileModel::goForward()")[1]
                             .split("}")[0])

    def test_stale_forward_refresh_notifies_qml(self):
        body = self.model.split("bool FileModel::goForward()")[1].split("\n}")[0]
        refusal = body.split("m_forwardStack.clear();")[1]
        self.assertIn("emit navigationChanged();", refusal)
        self.assertIn("emit navigationRejected(", refusal)

    def test_no_timers_or_process_api_in_forward_wiring(self):
        for forbidden in ("QTimer", "Qt.callLater", "QProcess", "std::system",
                          "::system(", "popen(", "QDesktopServices"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.header)
                self.assertNotIn(forbidden, self.model)


if __name__ == "__main__":
    unittest.main()
