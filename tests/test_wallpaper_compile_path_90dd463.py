"""Focused compiled-resource contract for the exact Classic master wallpaper.

These are source-level, fail-closed checks only. They never compile Qt, decode
artwork or claim visual acceptance; they prove that the exact approved bytes
are declared as a Qt resource and that Main.qml can select that resource.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

from tools.check_wallpaper import (
    APPROVED_ASSET,
    APPROVED_BYTES,
    APPROVED_SHA256,
    DUPLICATE_ASSET,
    MASTER_NAME,
)

ROOT = Path(__file__).resolve().parents[1]
CMAKE = ROOT / "prototype" / "classic" / "CMakeLists.txt"
MAIN_QML = ROOT / "prototype" / "classic" / "Main.qml"
QRC_PREFIX = "/Canopy/Classic"
# CMake FILES are relative to prototype/classic, so the qrc alias drops that
# leading directory: qrc:/Canopy/Classic/assets/approved/wallpaper/<master>.
RESOURCE_REL = Path("assets/approved/wallpaper") / MASTER_NAME
QRC_URL = f"qrc:{QRC_PREFIX}/{RESOURCE_REL.as_posix()}"
APPROVED_GIT_BLOB = "2802e690e1a7d0f16336b90a456dbaea9f5f014d"


def git_blob_oid(raw: bytes) -> str:
    """Compute the git blob OID from bytes without invoking git."""
    header = b"blob " + str(len(raw)).encode("ascii") + b"\x00"
    return hashlib.sha1(header + raw).hexdigest()


class WallpaperCompilePathTests(unittest.TestCase):
    def test_exact_approved_png_is_declared_as_a_compiled_qt_resource(self):
        text = CMAKE.read_text(encoding="utf-8")
        match = re.search(r"qt_add_resources\([^)]*\)", text, re.DOTALL)
        self.assertIsNotNone(match, "qt_add_resources block missing")
        block = match.group(0)
        self.assertIn(f'PREFIX "{QRC_PREFIX}"', block)
        # FILES are relative to prototype/classic; the qrc URL is
        # qrc:/Canopy/Classic/<this exact relative path>.
        self.assertIn(RESOURCE_REL.as_posix(), block)
        files = re.search(r"\bFILES\b(.*)", block, re.DOTALL)
        self.assertIsNotNone(files, "qt_add_resources FILES list missing")
        for entry in files.group(1).replace(")", " ").split():
            self.assertTrue(
                (CMAKE.parent / entry).is_file(),
                f"declared resource does not exist: {entry}",
            )

    def test_declared_resource_is_the_exact_approved_blob(self):
        raw = (ROOT / APPROVED_ASSET).read_bytes()
        self.assertEqual(len(raw), APPROVED_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), APPROVED_SHA256)
        self.assertEqual(git_blob_oid(raw), APPROVED_GIT_BLOB)
        # The second source-tree copy must remain byte-identical; no art edit.
        self.assertEqual((ROOT / DUPLICATE_ASSET).read_bytes(), raw)

    def test_main_qml_prefers_the_qrc_url_with_safe_source_fallback(self):
        text = MAIN_QML.read_text(encoding="utf-8")
        self.assertIn(QRC_URL, text)
        # Compiled QML resolves relative URLs against qrc:; only an uncompiled
        # source-tree preview may use the CWD-relative file URL, and it names
        # the same approved master (never a substitute or legacy wave).
        self.assertIn('Qt.resolvedUrl("Main.qml")', text)
        self.assertIn('startsWith("qrc:")', text)
        self.assertIn(f'"file:{APPROVED_ASSET.as_posix()}"', text)
        self.assertIn("approvedMasterWallpaperUrl", text)
        self.assertIn("Qt.binding", text)
        self.assertIn("canopyLandscapeWallpaperUrl.length > 0", text)
        self.assertNotIn("blue-current.svg", text)
        self.assertNotIn("canopy-wave-preview.png", text)


if __name__ == "__main__":
    unittest.main()
