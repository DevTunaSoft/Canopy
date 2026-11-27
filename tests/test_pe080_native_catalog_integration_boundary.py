"""PE-080 integration-boundary regression for the native catalog producer.

QA064 established that ``app.catalog.changed`` is transport only and that the
compiled launcher bridge is single-load/read-only. PE076's refresh contract
lives in an unmerged draft (PR #694), and the compiled reload point is in
owner-protected C++/QML paths. This module pins the *safe* part of the boundary:
the native producer is a stateless, bounded, refresh-ready one-shot producer,
and the compiled bridge still exposes no reload path. It makes no claim that a
running Classic process reflects an install or removal. Source-contract and
synthetic temp-dir tests only: no Qt build, desktop, Mint guest or visual
acceptance is claimed.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from canopy_features.launcher.native_catalog_producer import (
    MAX_DIRECTORY_ENTRIES,
    MAX_ENTRIES,
    MAX_SNAPSHOT_BYTES,
    produce_catalog_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "prototype" / "classic" / "main.cpp"
HEADER = ROOT / "prototype" / "classic" / "LauncherModel.h"


def _applications_dir(root):
    path = Path(root) / "applications"
    path.mkdir()
    return str(path)


def _install(applications_dir, app_id, name):
    (Path(applications_dir) / app_id).write_bytes(
        ("[Desktop Entry]\nType=Application\nName=%s\nExec=/usr/bin/true\n"
         % name).encode("utf-8"))


class ProducerRefreshReadinessTests(unittest.TestCase):
    """The existing producer can be re-invoked; it keeps no stale state."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.applications_dir = _applications_dir(self.tmp.name)
        _install(self.applications_dir, "org.example.One.desktop", "One")

    def test_reproduce_reflects_install_then_removal(self):
        before = produce_catalog_bytes(self.applications_dir)
        self.assertNotIn(b"org.example.Two.desktop", before)
        _install(self.applications_dir, "org.example.Two.desktop", "Two")
        after_install = produce_catalog_bytes(self.applications_dir)
        self.assertIn(b"org.example.Two.desktop\tTwo\n", after_install)
        self.assertNotEqual(after_install, before)
        (Path(self.applications_dir) / "org.example.Two.desktop").unlink()
        after_remove = produce_catalog_bytes(self.applications_dir)
        self.assertEqual(after_remove, before)
        self.assertNotIn(b"org.example.Two.desktop", after_remove)

    def test_reproduction_is_read_only_and_bounded(self):
        app = Path(self.applications_dir) / "org.example.One.desktop"
        original = app.read_bytes()
        first = produce_catalog_bytes(self.applications_dir)
        second = produce_catalog_bytes(self.applications_dir)
        self.assertEqual(first, second)
        self.assertEqual(app.read_bytes(), original)
        source = (ROOT / "canopy_features" / "launcher"
                  / "native_catalog_producer.py").read_text(encoding="utf-8")
        for name in ("MAX_ENTRIES", "MAX_DIRECTORY_ENTRIES",
                     "MAX_SNAPSHOT_BYTES"):
            self.assertIn(name, source)
        self.assertIn("MAX_DIRECTORY_ENTRIES = %d" % MAX_DIRECTORY_ENTRIES,
                      source)
        self.assertIn("MAX_SNAPSHOT_BYTES = %d * 1024"
                      % (MAX_SNAPSHOT_BYTES // 1024), source)
        for forbidden in ("QTimer", "sleep(", "subprocess", "Popen",
                          "socket", "while True"):
            self.assertNotIn(forbidden, source, forbidden)


class CompiledBridgeBoundaryTests(unittest.TestCase):
    """A running compiled launcher has no catalog reload path at this base."""

    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")

    def test_bridge_is_single_load_and_read_only(self):
        self.assertIn("Q_PROPERTY(int rowCount READ rowCount CONSTANT)",
                      self.main)
        self.assertIn("Q_PROPERTY(bool active READ active CONSTANT)",
                      self.main)
        self.assertEqual(self.main.count("launcherCatalog.loadFromFile("), 1)
        start = self.main.index("class LauncherCatalogBridge final : public QObject")
        bridge = self.main[start:self.main.index("\n};", start)]
        for forbidden in ("loadFromFile", "reload", "QTimer", "QNetwork",
                          "QProcess", "setProperty"):
            self.assertNotIn(forbidden, bridge, forbidden)
        self.assertIn("int rowCount() const { return m_model.rowCount(); }",
                      bridge)

    def test_host_event_consumer_never_reloads_the_catalog(self):
        start = self.main.index("Q_INVOKABLE bool applyHostEvent(")
        end = self.main.index("Q_INVOKABLE QVariantMap view(", start)
        consumer = self.main[start:end]
        self.assertIn('QStringLiteral("app.catalog.changed")', consumer)
        self.assertNotIn("launcherCatalog", consumer)
        self.assertNotIn("loadFromFile", consumer)
        self.assertNotIn("rowCount", consumer)

    def test_model_exposes_load_only_once_without_notify(self):
        self.assertIn("bool loadFromFile(const QString &path);", self.header)
        self.assertNotIn("reload", self.header)
        self.assertNotIn("NOTIFY", self.header)
        self.assertIn("int rowCount() const { return m_rows.size(); }",
                      self.header)


if __name__ == "__main__":
    unittest.main()
