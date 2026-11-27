"""ND-039 regression lock for the compiled Classic host-event bridge.

The production wiring lives entirely in ``prototype/classic/main.cpp``: one
bounded, event-driven dispatcher routes the four reviewed protocol-v2 host
event tokens to the already-merged compiled bridges. These checks lock that
wiring in the repository (topic set, routing targets, fail-closed order, hard
caps and the absence of polling/transport/visual edits). They are source
contracts only: no Qt instance, desktop, Mint guest or visual acceptance is
claimed by them. The compiled self-test flag is recorded separately in the
build-local doc next to the source.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from canopy_core.host_events import TOPICS

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "prototype" / "classic"
MAIN = PROTO / "main.cpp"
CMAKE = PROTO / "CMakeLists.txt"
DOC = PROTO / "HOST_EVENT_BRIDGE.md"


def main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


def class_block(source: str, name: str) -> str:
    start = source.index("class %s final : public QObject" % name)
    return source[start:source.index("\n};", start)]


class CompiledBridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = main_source()
        cls.bridge = class_block(cls.cpp, "ClassicHostEventBridge")
        cls.literals = set(re.findall(
            r'QStringLiteral\("([^"]+)"\)', cls.bridge))

    def test_bridge_is_a_host_side_dispatcher_not_a_transport(self):
        for marker in (
                "class ClassicHostEventBridge final : public QObject",
                "Q_OBJECT",
                "Q_INVOKABLE bool dispatch(",
                "QStringList allowedTopics() const",
                "emit catalogRefreshRequested();",
                "signals:",
                "void catalogRefreshRequested();",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.bridge)
        for forbidden in (
                "QTimer", "QThread", "QProcess", "QTcpSocket", "QUdpSocket",
                "QLocalSocket", "QDBus", "QNetworkAccessManager", "QFile",
                "QDirIterator", "std::system", "pkexec", "sudo ",
                "while (", "for (;;)", "msleep", "sleep(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.bridge)

    def test_topic_set_is_exactly_the_reviewed_protocol_v2_contract(self):
        block = re.search(
            r"QStringList allowedTopics\(\) const \{(.*?)\n    \}",
            self.bridge, re.S)
        self.assertIsNotNone(block)
        topics = set(re.findall(r'QStringLiteral\("([^"]+)"\)', block.group(1)))
        self.assertEqual(topics, set(TOPICS))
        self.assertEqual(len(topics), 4)
        # No dynamic registration or fifth topic anywhere in the dispatcher.
        self.assertNotIn("registerTopic", self.bridge)
        self.assertNotIn("dynamicTopic", self.bridge)

    def test_each_token_reaches_its_merged_bridge(self):
        for marker in (
                'topic == QStringLiteral("capabilities.report")',
                'topic == QStringLiteral("session.state.changed")',
                'topic == QStringLiteral("window.state.changed")',
                'm_quickControls->applyHostEvent(topic, payload)',
                'm_activation->applySnapshot(payload)',
                'emit catalogRefreshRequested();',
                'record(QStringLiteral("catalog-refresh-requested"));',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.bridge)
        # The compiled shell does not re-produce the catalog or add a second
        # read-only model load: that stays with the merged Python bridge.
        self.assertEqual(self.cpp.count("launcherCatalog.loadFromFile("), 1)
        self.assertNotIn("QDirIterator", self.bridge)

    def test_window_snapshot_is_shape_guarded_before_delegation(self):
        self.assertIn("snapshotKeys()", self.bridge)
        self.assertIn("if (!payload.contains(key))", self.bridge)
        self.assertLess(self.bridge.index("if (!payload.contains(key))"),
                        self.bridge.index("m_activation->applySnapshot(payload)"))
        for key in ("schema", "backend", "negotiation", "sequence",
                    "installed", "owners", "grants", "launcherEnabled"):
            with self.subTest(key=key):
                self.assertIn('QStringLiteral("%s")' % key, self.bridge)

    def test_fail_closed_order_and_fixed_outcomes(self):
        idx_unknown = self.bridge.index(
            'if (!allowedTopics().contains(topic) || payload.isEmpty())')
        idx_route = self.bridge.index(
            'm_quickControls->applyHostEvent(topic, payload)')
        self.assertLess(idx_unknown, idx_route)
        self.assertIn('if (m_total >= kMaxEvents)', self.bridge)
        for token in ("rejected", "window-rejected", "refresh-limit",
                      "quick-controls-applied", "session-observed",
                      "window-applied", "catalog-refresh-requested"):
            with self.subTest(token=token):
                self.assertIn('QStringLiteral("%s")' % token, self.bridge)
        # A session observation must not manufacture a privileged status.
        self.assertNotIn('QStringLiteral("Active")', self.bridge)
        self.assertNotIn('QStringLiteral("Locked")', self.bridge)

    def test_bounds_are_hard_ceiling_constants(self):
        self.assertIn("static constexpr int kMaxEvents = 64;", self.bridge)
        self.assertIn("static constexpr int kMaxHistory = 16;", self.bridge)
        self.assertIn("if (m_history.size() == kMaxHistory)", self.bridge)
        self.assertIn("m_history.removeFirst();", self.bridge)
        self.assertIn("Q_INVOKABLE QStringList outcomeHistory() const", self.bridge)
        self.assertIn("Q_INVOKABLE bool frozen() const", self.bridge)

    def test_main_wiring_has_no_new_source_or_visual_change(self):
        self.assertIn(
            "ClassicHostEventBridge hostEventBridge(hostStateController, "
            "activationState);", self.cpp)
        bridge_at = self.cpp.index("ClassicHostEventBridge hostEventBridge")
        engine_at = self.cpp.index("QQmlApplicationEngine engine;")
        self.assertLess(bridge_at, engine_at)
        self.assertIn("&ClassicHostEventBridge::catalogRefreshRequested", self.cpp)
        self.assertIn('args.contains(QStringLiteral("--self-test-host-event-bridge"))',
                      self.cpp)
        self.assertIn("HOST_EVENT_BRIDGE_SELF_TEST_PASS", self.cpp)
        # No extra compiled translation unit: the seam stays inside main.cpp.
        self.assertNotIn("ClassicHostEventBridge.cpp", CMAKE.read_text(encoding="utf-8"))
        self.assertIn("qt_add_executable(canopy-classic-spike main.cpp ",
                      CMAKE.read_text(encoding="utf-8"))

    def test_build_local_doc_records_bounds_labels_and_blocker(self):
        text = DOC.read_text(encoding="utf-8")
        for marker in ("Current head", "SYNTHETIC", "NOT_RUN", "screen-reader",
                       "AWAITING_CHATGPT_VISUAL_APPROVAL", "--self-test-host-event-bridge",
                       "window.state.changed", "app.catalog.changed"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
