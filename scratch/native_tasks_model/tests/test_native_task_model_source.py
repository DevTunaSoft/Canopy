"""Offline source-contract gates for the bounded native TasksModel port.

These tests never claim desktop acceptance. They pin the PR #730 single-model
rule, the byte-frozen Classic visual/state files and the read-only event-driven
shape of the native adapter. Runtime evidence is recorded separately in
``evidence/`` by ``scripts/guest_runtime.py``.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import unittest
from pathlib import Path

NATIVE = Path(__file__).resolve().parents[1]
ROOT = NATIVE.parents[1]
CLASSIC = ROOT / "prototype" / "classic"
PKG = NATIVE / "package" / "contents" / "ui" / "main.qml"
HARNESS = NATIVE / "harness" / "NativeTaskHarness.qml"
BOARD_H = NATIVE / "src" / "NativeTaskBoard.h"
BOARD_CPP = NATIVE / "src" / "NativeTaskBoard.cpp"


def code_only(text: str) -> str:
    """Drop // comments so prose about forbidden APIs is not code."""
    return "\n".join(line.split("//", 1)[0] for line in
                     re.sub(r"/\*.*?\*/", "", text, flags=re.S).splitlines())


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def committed(relative: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:" + relative])


class NativeTaskModelSourceTests(unittest.TestCase):
    def test_frozen_product_files_are_byte_identical(self):
        for relative in ("prototype/classic/DockTile.qml",
                         "prototype/classic/WindowActivationState.h",
                         "prototype/classic/WindowActivationState.cpp"):
            with self.subTest(path=relative):
                self.assertEqual(committed(relative), (ROOT / relative).read_bytes())
        self.assertEqual((NATIVE / "harness" / "DockTile.qml").read_bytes(),
                         committed("prototype/classic/DockTile.qml"))

    def test_one_authoritative_tasksmodel_in_each_consumer(self):
        for path in (PKG, HARNESS):
            with self.subTest(path=path.name):
                text = code_only(path.read_text(encoding="utf-8"))
                self.assertEqual(text.count("TaskManager.TasksModel {"), 1)
                self.assertIn("org.kde.taskmanager as TaskManager", text)
                self.assertNotIn("ListModel", text)
                self.assertNotIn("TasksModel {", text.replace(
                    "TaskManager.TasksModel {", ""))
        tile = (NATIVE / "harness" / "DockTile.qml").read_text(encoding="utf-8")
        self.assertNotIn("TaskManager", tile)
        self.assertNotIn("ListModel", tile)

    def test_activation_uses_upstream_request_only(self):
        harness = code_only(HARNESS.read_text(encoding="utf-8"))
        package = code_only(PKG.read_text(encoding="utf-8"))
        for text in (harness, package):
            self.assertIn("requestActivate", text)
            self.assertNotIn("QProcess", text)
            self.assertNotIn("Qt.openUrlExternally", text)
        self.assertIn("attachModel(upstreamTasks)", harness)
        self.assertIn("root.activateTile(root.terminalId)", harness)

    def test_adapter_is_read_only_bounded_and_event_driven(self):
        source = code_only(BOARD_H.read_text(encoding="utf-8")
                           + BOARD_CPP.read_text(encoding="utf-8"))
        self.assertIn("attachModel(QObject *modelObject)", source)
        self.assertIn("REFUSE second authoritative model", source)
        self.assertIn("resolveRoles", source)
        self.assertIn("kMaxRows", source)
        self.assertIn("clearFailClosed", source)
        for forbidden in ("QTimer", "QProcess", "socket", "sleep(", "QThread",
                          "while (true)", "while(true)", "TasksModel {"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)

    def test_approved_icon_bytes_are_unchanged_copies(self):
        for name in ("browser", "files", "photos", "settings", "terminal", "trash"):
            with self.subTest(icon=name):
                original = (CLASSIC / "assets" / "icons" / (name + ".svg")).read_bytes()
                copied = (NATIVE / "icons" / (name + ".svg")).read_bytes()
                self.assertEqual(original, copied)

    def test_package_identity_and_port_provenance(self):
        import json
        meta = json.loads((NATIVE / "package" / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["KPlugin"]["Id"],
                         "org.kde.plasma.canopyclassic.nativetasks")
        self.assertEqual(meta["KPackageStructure"], "Plasma/Applet")
        self.assertIn("53a22fe96259c49e339e6d03ea844936cb99fb10",
                      meta["X-Canopy-Ported-From"])


if __name__ == "__main__":
    unittest.main()
