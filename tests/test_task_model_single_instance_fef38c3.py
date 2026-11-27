"""Source-contract regression for the single upstream TasksModel (fef38c3).

Static source assertions only. No compile, runtime, visual or asset acceptance
is claimed here.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "native_plasma_classic_package" / "contents" / "ui"
PKG = ROOT / "native_plasma_classic_package"
FALSE_CLAIMS = (
    "Running indicators and grouping all project",
    "the same TaskManager::TasksModel (A03, A04, A19).",
    "Task data comes only from the single upstream TaskManager::TasksModel (A04).",
    "One upstream model feeds both panel and dock; never a second task source.",
)


def read(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


class SingleTasksModelSourceTests(unittest.TestCase):
    def test_r1_exactly_one_declaration_in_panel(self) -> None:
        hits = [line for qml in UI.glob("*.qml")
                for line in qml.read_text(encoding="utf-8").splitlines()
                if "TaskManager.TasksModel {" in line]
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("id: upstreamTasks", read("CanopyPanel.qml"))

    def test_dock_accepts_injected_model_without_local_import(self) -> None:
        dock = read("CanopyDock.qml")
        self.assertIn("property var tasksModel: null", dock)
        self.assertNotIn("TaskManager", dock)
        self.assertNotIn("property alias tasksModel", dock)

    def test_containment_injects_panel_model_into_dock(self) -> None:
        main = read("main.qml")
        self.assertIn("tasksModel: canopyTopPanel.tasksModel", main)
        self.assertLess(main.index("id: canopyTopPanel"),
                        main.index("tasksModel: canopyTopPanel.tasksModel"))
        self.assertIn("model: canopyDock.tasksModel", read("CanopyDock.qml"))
        self.assertIn("tasksModel: canopyDock.tasksModel", read("CanopyDock.qml"))

    def test_false_shared_model_comments_removed(self) -> None:
        for qml in UI.glob("*.qml"):
            text = qml.read_text(encoding="utf-8")
            for claim in FALSE_CLAIMS:
                self.assertNotIn(claim, text, (qml.name, claim))

    def test_visual_and_layout_lines_unchanged(self) -> None:
        dock, panel, main = read("CanopyDock.qml"), read("CanopyPanel.qml"), read("main.qml")
        for line in (
            'text: "Canopy Classic dock"',
            'text: "Canopy Classic"',
            "fullRepresentation: RowLayout {",
            "model: canopyDock.tasksModel",
            "model: canopyPanel.tasksModel",
            "tasksModel: canopyDock.tasksModel",
            "tasksModel: canopyPanel.tasksModel",
            "screenGeometryFilter: true",
            "left: parent.left",
            "right: parent.right",
            "top: parent.top",
            "anchors.horizontalCenter: parent.horizontalCenter",
            "anchors.bottom: parent.bottom",
        ):
            self.assertIn(line, dock + panel + main, line)

    def test_asset_bindings_remain_hash_only_pin(self) -> None:
        raw = (PKG / "ASSET_BINDINGS.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "daed3d2498940471b2adab1bec262c0ef180ba66bd185a8d53f7435e57ed27ee",
        )
        bindings = json.loads(raw)["bindings"]
        self.assertEqual(len(bindings), 11)
        self.assertTrue(all(b["local_copy"] is None for b in bindings))


if __name__ == "__main__":
    unittest.main()
