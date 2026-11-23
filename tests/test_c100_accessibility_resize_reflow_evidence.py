"""Offline unit tests for the Classic QML resize/reflow contract checker.

These tests read source bindings only. They do not compile Qt, launch a
window, or verify Linux Mint behaviour.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from canopy_features.accessibility import resize_reflow_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"
WIDTH, HEIGHT = 760, 500


def copy_source(destination: Path) -> Path:
    for name in evidence._QML_FILES:
        shutil.copy(SOURCE / name, destination / name)
    return destination


class ResizeReflowEvidenceTests(unittest.TestCase):
    def test_compact_760x500_source_has_no_clipping_or_overflow(self):
        report = evidence.check_layout(SOURCE, WIDTH, HEIGHT)
        self.assertTrue(report.ok, [f.as_dict() for f in report.findings])
        self.assertEqual(report.size, (WIDTH, HEIGHT))
        self.assertTrue(report.metrics["compact_layout"])
        self.assertTrue(report.metrics["condensed"])
        self.assertEqual(report.metrics["preview_width"], 688.0)
        self.assertEqual(report.metrics["preview_height"], 302.0)
        self.assertEqual(report.metrics["folder_columns"], 4)
        self.assertEqual(report.metrics["folder_rows"], 2)

    def test_760x500_detects_clipped_folder_content(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copy_source(Path(directory))
            path = target / "PreviewWindow.qml"
            text = path.read_text(encoding="utf-8")
            old = "contentHeight: Math.max(height, folders.height + 10)"
            self.assertIn(old, text)
            path.write_text(text.replace(old,
                            "contentHeight: Math.max(height, folders.height + 400)"),
                            encoding="utf-8")
            report = evidence.check_layout(target, WIDTH, HEIGHT)
        clipped = [f for f in report.findings if f.code == "clipped-content"]
        self.assertEqual(len(clipped), 1, [f.as_dict() for f in report.findings])
        self.assertEqual(clipped[0].item, "folderScroller")
        self.assertIn("exceeds viewport", clipped[0].detail)
        self.assertGreater(report.metrics["folder_content_height"],
                           report.metrics["folder_scroller_height"])
        self.assertFalse(report.ok)

    def test_760x500_detects_preview_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copy_source(Path(directory))
            path = target / "Main.qml"
            text = path.read_text(encoding="utf-8")
            old = "width: Math.min(root.width - 72, Math.max(780, root.width * 0.56))"
            self.assertIn(old, text)
            path.write_text(text.replace(old,
                            "width: Math.min(root.width + 200, Math.max(780, root.width * 0.56))"),
                            encoding="utf-8")
            report = evidence.check_layout(target, WIDTH, HEIGHT)
        overflow = [f for f in report.findings
                    if f.code == "overflow" and f.item == "filesPreview"]
        self.assertEqual(len(overflow), 1, [f.as_dict() for f in report.findings])
        self.assertIn("exceed", overflow[0].detail)
        self.assertFalse(report.ok)

    def test_760x500_detects_launcher_panel_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copy_source(Path(directory))
            path = target / "LauncherOverlay.qml"
            text = path.read_text(encoding="utf-8")
            old = "width: Math.min(parent.width - 42, 814)"
            self.assertIn(old, text)
            path.write_text(text.replace(old,
                            "width: Math.min(parent.width + 42, 814)"),
                            encoding="utf-8")
            report = evidence.check_layout(target, WIDTH, HEIGHT)
        self.assertTrue(any(f.code == "overflow" and f.item == "launcherPanel"
                            for f in report.findings),
                        [f.as_dict() for f in report.findings])

    def test_full_resolution_source_still_has_no_findings(self):
        report = evidence.check_layout(SOURCE, 1920, 1080)
        self.assertTrue(report.ok, [f.as_dict() for f in report.findings])
        self.assertFalse(report.metrics["compact_layout"])

    def test_size_below_qml_minimum_is_reported(self):
        report = evidence.check_layout(SOURCE, 700, 500)
        self.assertTrue(any(f.code == "minimum-size"
                            for f in report.findings))
        self.assertFalse(report.ok)

    def test_missing_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copy_source(Path(directory))
            path = target / "Main.qml"
            path.write_text(path.read_text(encoding="utf-8").replace(
                "id: filesPreview", "id: renamedPreview"), encoding="utf-8")
            with self.assertRaises(evidence.ContractError):
                evidence.check_layout(target, WIDTH, HEIGHT)

    def test_cli_emits_json_and_nonzero_exit_for_clipped_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            target = copy_source(Path(directory))
            path = target / "PreviewWindow.qml"
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(
                "contentHeight: Math.max(height, folders.height + 10)",
                "contentHeight: Math.max(height, folders.height + 400)"),
                encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                status = evidence.main(["760x500", "--source", str(target)])
        payload = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["size"], [WIDTH, HEIGHT])
        self.assertTrue(any(f["code"] == "clipped-content"
                            for f in payload["findings"]))


if __name__ == "__main__":
    unittest.main()
