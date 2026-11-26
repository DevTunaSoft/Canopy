"""Contracts for the explicit owner Tux icon preview opt-in (128c973).

Source-only and byte-level checks. They do not claim compiled Qt execution
or owner visual approval: real offscreen-binary screenshots are evidence in
docs/CLASSIC_OWNER_ICONS_OPTIN.md and are labelled separately.
"""
import hashlib
import json
import re
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
OWNER = CLASSIC / "assets" / "owner_icons_20261126"
MANIFEST = OWNER / "manifest.json"
SOURCE_ZIP_SHA256 = "d84916fbe66f05821167c73b3fa5bde1a039547fb6f5d7969c666b1f2457415d"
EXPECTED_HASHES = {
    "Browser": "a6fc7c60e418cd4b7ea2c9d96141c2ebbc0e237f14d69550327d6735fd3dd6e9",
    "Mail": "5e7cff302bc2ff1f0ada410f7b74db7e9ebb8e76894c28ed1257c5752531d08a",
    "Files": "cb3282b4b246f720b0125fab0432135560acb9084ec5b1c3588dc1766713a31f",
    "Calendar": "093af486630b972395a47b4b1732c89a5fb9f1badf984f1c3d8e8b9e6e8bf267",
    "Photos": "2dde5b6084d17efb85efe97bf1d55d9b70b9ff3c62f89defee2bbbe4461a6df2",
    "Music": "be3dfeffaf0d51f8f72a005963b1f940a7cea8b996319ab66eff5dd23eb9eb62",
    "Terminal": "e9cc4b2787c1200e16f71e2058a21a9308e84dcebadd451bdb933d05e1b126cc",
    "Settings": "9b790a50a4c04eb7d579c4b9fe54e0d9b2d0d3fd0b45d58b1fa5bf256dd971d9",
}


def alpha_rows(path):
    """Decode only the alpha plane of an 8-bit RGBA PNG (stdlib only)."""
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    cursor = 8
    compressed = bytearray()
    width = height = None
    while cursor + 12 <= len(data):
        length = struct.unpack_from(">I", data, cursor)[0]
        kind = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:cursor + 8 + length]
        if cursor + 12 + length > len(data):
            raise ValueError("truncated PNG chunk")
        if kind == b"IHDR":
            width, height, depth, colour, comp, filt, inter = struct.unpack(
                ">IIBBBBB", payload)
            if (depth, colour, comp, filt, inter) != (8, 6, 0, 0, 0):
                raise ValueError("expected 8-bit RGBA PNG")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        cursor += 12 + length
    if width is None or height is None:
        raise ValueError("PNG header missing")
    raw = zlib.decompress(bytes(compressed))
    stride = width * 4
    if len(raw) != height * (stride + 1):
        raise ValueError("unexpected PNG data length")
    rows = []
    previous = bytearray(width)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        line = raw[offset:offset + stride]
        offset += stride
        alpha = bytearray(width)
        for x in range(width):
            byte = line[x * 4 + 3]
            left = alpha[x - 1] if x else 0
            above = previous[x]
            upper_left = previous[x - 1] if x else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) >> 1
            elif filter_type == 4:
                estimate = left + above - upper_left
                gaps = (abs(estimate - left), abs(estimate - above),
                        abs(estimate - upper_left))
                predictor = (left, above, upper_left)[gaps.index(min(gaps))]
            else:
                raise ValueError("unknown PNG filter")
            alpha[x] = (byte + predictor) & 0xFF
        rows.append(bytes(alpha))
        previous = alpha
    return width, height, rows


def transparent_square(path, manifest):
    width, height, rows = alpha_rows(path)
    canvas = manifest["canvas"]
    if width != canvas["width"] or height != canvas["height"] or width != height:
        return False
    threshold = canvas["alpha_threshold"]
    corner_max = canvas["corner_alpha_max"]
    if any(rows[y][x] > corner_max for x, y in
           ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))):
        return False
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y, row in enumerate(rows):
        for x, alpha in enumerate(row):
            if alpha > threshold:
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < 0:
        return False
    observed = (min_x, min_y, max_x + 1, max_y + 1)
    entry = next((i for i in manifest["icons"]
                  if path.name == Path(i["path"]).name), None)
    if entry is None:
        return False
    return all(abs(actual - expected) <= manifest["canvas"]["bbox_tolerance"]
               for actual, expected in zip(observed, entry["alpha_bbox"]))


class OwnerIconsOptInTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.cpp = (CLASSIC / "main.cpp").read_text(encoding="utf-8")
        cls.provider_cpp = (CLASSIC / "RoundedDockIconProvider.cpp").read_text(
            encoding="utf-8")
        cls.provider_h = (CLASSIC / "RoundedDockIconProvider.h").read_text(
            encoding="utf-8")
        cls.tile = (CLASSIC / "DockTile.qml").read_text(encoding="utf-8")
        cls.main_qml = (CLASSIC / "Main.qml").read_text(encoding="utf-8")
        cls.cmake = (CLASSIC / "CMakeLists.txt").read_text(encoding="utf-8")
        cls.docs = (ROOT / "docs" / "CLASSIC_OWNER_ICONS_OPTIN.md").read_text(
            encoding="utf-8")

    def test_manifest_pins_exact_provenance_and_canvas(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["source_zip_sha256"], SOURCE_ZIP_SHA256)
        self.assertEqual(manifest["kind"], "owner-icons-preview-not-approved")
        self.assertEqual(manifest["canvas"]["width"], 1254)
        self.assertEqual(manifest["canvas"]["height"], 1254)
        self.assertEqual(manifest["canvas"]["alpha_threshold"], 8)
        self.assertEqual(manifest["canvas"]["corner_alpha_max"], 8)
        self.assertEqual(manifest["canvas"]["bbox_tolerance"], 2)
        icons = manifest["icons"]
        self.assertEqual(len(icons), 8)
        self.assertEqual([i["name"] for i in icons], list(EXPECTED_HASHES))
        for icon in icons:
            with self.subTest(icon=icon["name"]):
                self.assertEqual(icon["path"],
                                 "icons/" + icon["name"] + ".png")
                self.assertEqual(icon["sha256"],
                                 EXPECTED_HASHES[icon["name"]])
                self.assertEqual(icon["width"], 1254)
                self.assertEqual(icon["height"], 1254)
                self.assertEqual(len(icon["alpha_bbox"]), 4)
                self.assertTrue(all(isinstance(v, int) and 0 <= v <= 1254
                                    for v in icon["alpha_bbox"]))

    def test_bundled_pngs_are_byte_exact_transparent_squares(self):
        for icon in self.manifest["icons"]:
            with self.subTest(icon=icon["name"]):
                path = OWNER / icon["path"]
                payload = path.read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(),
                                 icon["sha256"])
                width, height, rows = alpha_rows(path)
                self.assertEqual((width, height), (1254, 1254))
                for x, y in ((0, 0), (1253, 0), (0, 1253), (1253, 1253)):
                    self.assertLessEqual(rows[y][x], 8)
                min_x, min_y, max_x, max_y = 1254, 1254, -1, -1
                for y, row in enumerate(rows):
                    for x, alpha in enumerate(row):
                        if alpha > 8:
                            min_x, min_y = min(min_x, x), min(min_y, y)
                            max_x, max_y = max(max_x, x), max(max_y, y)
                observed = (min_x, min_y, max_x + 1, max_y + 1)
                for actual, expected in zip(observed, icon["alpha_bbox"]):
                    self.assertLessEqual(abs(actual - expected), 2)

    def test_negative_control_rejects_non_square_or_opaque_corner(self):
        # SYNTHETIC fixture: a 2x3 RGBA PNG with an opaque corner. It proves
        # the transparency gate is a real predicate, not a rubber stamp.
        width, height = 2, 3
        scanlines = b"".join(
            b"\x00" + bytes([0, 0, 0, 255] * width) for _ in range(height))
        header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

        def chunk(kind, payload):
            return (struct.pack(">I", len(payload)) + kind + payload
                    + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

        fixture = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                   + chunk(b"IDAT", zlib.compress(scanlines))
                   + chunk(b"IEND", b""))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__synthetic_not_committed.png"
            path.write_bytes(fixture)
            self.assertFalse(transparent_square(path, self.manifest))

    def test_flag_is_explicit_fail_closed_and_requires_approved_art(self):
        self.assertIn('QStringLiteral("--owner-icons-preview")', self.cpp)
        self.assertIn("if (ownerIconsMode && !approvedMode)", self.cpp)
        self.assertIn("OWNER_ICONS_PREVIEW_FAIL: --owner-icons-preview requires "
                      "--approved-art-dir", self.cpp)
        self.assertIn("verifyOwnerIconsPreview(args.at(ownerIconsIndex + 1), "
                      "&ownerError)", self.cpp)
        self.assertIn("OWNER_ICON_SHA256_MISMATCH refusing substitute", self.cpp)
        self.assertIn("owner icon corners are not transparent", self.cpp)
        self.assertIn("owner icon transparent square bbox mismatch", self.cpp)
        self.assertIn("CANOPY_OWNER_ICONS_VERIFIED", self.cpp)
        self.assertIn("CANOPY_APPROVED_ART_VERIFIED", self.cpp)
        self.assertIn("CANOPY_ROUNDED_DOCK_VERIFIED", self.cpp)
        self.assertIn("kOwnerIconsZipSha256", self.cpp)
        self.assertIn(SOURCE_ZIP_SHA256, self.cpp)
        self.assertIn('":/Canopy/Classic/assets/owner_icons_20261126/manifest.json"',
                      self.cpp)
        self.assertIn("assets/owner_icons_20261126/manifest.json", self.cmake)

    def test_default_startup_keeps_approved_dock_and_frozen_tiles(self):
        # The opt-in provider is registered only inside the owner branch;
        # the approved renderer remains the default branch.
        match = re.search(
            r"if \(approvedMode\) \{\s*if \(ownerIconsMode\) \{(.*?)\} else \{(.*?)\n        \}\n    \}",
            self.cpp, re.DOTALL)
        self.assertIsNotNone(match, "approved/opt-in provider branches missing")
        owner_branch, approved_branch = match.group(1), match.group(2)
        self.assertIn("OwnerIconsPreviewProvider", owner_branch)
        self.assertIn("CANOPY_OWNER_ICONS_VERIFIED", owner_branch)
        self.assertIn("RoundedDockIconProvider", approved_branch)
        self.assertIn('QStringLiteral("canopy-dock"), roundedIcons', approved_branch)
        self.assertIn('"image://canopy-dock/" + iconName.toLowerCase()', self.tile)
        self.assertIn("width: 54", self.tile)
        self.assertIn("height: 54", self.tile)
        self.assertIn('color: canopyApprovedMode ? "#b0d6e8f6" : '
                      'canopyTheme.dockSurface', self.main_qml)
        self.assertIn('readonly property bool ownerIconsPreviewActive',
                      self.main_qml)

    def test_owner_provider_returns_exact_bytes_without_regeneration(self):
        start = self.provider_cpp.index(
            "OwnerIconsPreviewProvider::OwnerIconsPreviewProvider")
        owner_impl = self.provider_cpp[start:]
        self.assertIn("return exact; // Exact decoded PNG bytes", owner_impl)
        self.assertNotIn("QPainter", owner_impl)
        self.assertNotIn("drawImage", owner_impl)
        self.assertNotIn("scaled(", owner_impl)
        self.assertNotIn("fillPath", owner_impl)
        self.assertNotIn("addRoundedRect", owner_impl)
        self.assertIn("QImageReader reader(path)", owner_impl)
        self.assertIn("m_images.insert(name.toLower(), image)", owner_impl)
        self.assertIn("class OwnerIconsPreviewProvider", self.provider_h)
        self.assertIn("bool isValid() const { return m_images.size() == 8; }",
                      self.provider_h)

    def test_dark_frosted_dock_is_injected_only_in_owner_mode(self):
        block = self.cpp[self.cpp.index("if (ownerIconsMode) {"):
                         self.cpp.index("QObject::connect(&activationState")]
        self.assertIn("#a31f2a33", block)
        self.assertIn("#33c6d8e4", block)
        self.assertIn('QStringLiteral("border.color")', block)
        self.assertIn("CANOPY_OWNER_DOCK_FROST_ACTIVE", block)
        self.assertIn("SELF_TEST_PASS: owner exact-PNG icons and dark frosted dock "
                      "at frozen 54px slots", self.cpp)

    def test_docs_disclose_preview_only_and_evidence_labels(self):
        self.assertIn("AWAITING_CHATGPT_VISUAL_APPROVAL", self.docs)
        self.assertIn("SYNTHETIC", self.docs)
        self.assertIn("NOT_RUN", self.docs)
        self.assertIn("CANOPY_OWNER_ICONS_VERIFIED", self.docs)
        self.assertIn("screen-reader", self.docs)


if __name__ == "__main__":
    unittest.main()
