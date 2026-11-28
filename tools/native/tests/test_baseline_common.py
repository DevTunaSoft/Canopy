"""Pure helper tests for the native baseline tooling (no VM, no repo changes)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.native.baseline_common import (
    APPROVED_WALLPAPER_SHA256, SOURCE_COMMIT, canonical_sha256,
    check_manifest_pins, is_hex40, make_sha256sums, parse_sha256sums,
    sha256_bytes, write_deterministic_tarball,
)


class BaselineCommonTests(unittest.TestCase):
    def test_pins_are_well_formed(self):
        self.assertTrue(is_hex40(SOURCE_COMMIT))
        self.assertEqual(len(APPROVED_WALLPAPER_SHA256), 64)
        self.assertTrue(canonical_sha256(APPROVED_WALLPAPER_SHA256.upper()))

    def test_canonical_sha_rejects_malformed(self):
        for bad in ("", "abc", "z" * 64, None, 123, " " + "a" * 64):
            self.assertIsNone(canonical_sha256(bad), bad)

    def test_sha256_bytes(self):
        self.assertEqual(sha256_bytes(b"canopy"),
                         hashlib.sha256(b"canopy").hexdigest())

    def test_sha256sums_parse_and_duplicate_negative_control(self):
        text = "%s  a.txt\n%s  b.txt\n" % ("a" * 64, "b" * 64)
        self.assertEqual(parse_sha256sums(text),
                         {"a.txt": "a" * 64, "b.txt": "b" * 64})
        with self.assertRaises(ValueError):
            parse_sha256sums(text + "%s  a.txt\n" % ("c" * 64))
        with self.assertRaises(ValueError):
            parse_sha256sums("zz  a.txt\n")

    def test_deterministic_tar_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pkg"
            (root / "nested").mkdir(parents=True)
            (root / "a.txt").write_bytes(b"alpha")
            (root / "nested" / "b.txt").write_bytes(b"beta")
            one = write_deterministic_tarball(root, Path(tmp) / "one.tar.gz")
            two = write_deterministic_tarball(root, Path(tmp) / "two.tar.gz")
            self.assertEqual(one, two)
            (root / "a.txt").write_bytes(b"changed")
            self.assertNotEqual(
                one, write_deterministic_tarball(root, Path(tmp) / "three.tar.gz"))

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pkg"
            root.mkdir()
            (root / "real.txt").write_bytes(b"x")
            (root / "link.txt").symlink_to(root / "real.txt")
            with self.assertRaises(ValueError):
                write_deterministic_tarball(root, Path(tmp) / "x.tar.gz")

    def test_sha256sums_excludes_requested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").write_bytes(b"a")
            (root / "SHA256SUMS").write_bytes(b"stale")
            sums = parse_sha256sums(make_sha256sums(root, frozenset({"SHA256SUMS"})))
            self.assertEqual(sorted(sums), ["a"])

    def test_approved_icon_pins_and_negative_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "approved"
            (root / "icons").mkdir(parents=True)
            names = ["Browser", "Mail", "Files", "Calendar", "Photos",
                     "Music", "Terminal", "Settings"]
            icons = []
            for index, name in enumerate(names):
                relative = "icons/%s.png" % name
                data = ("icon-%d" % index).encode()
                (root / relative).write_bytes(data)
                icons.append({"name": name, "path": relative,
                              "sha256": hashlib.sha256(data).hexdigest()})
            manifest = {"icons": icons}
            self.assertEqual(len(check_manifest_pins(manifest, root)), 8)
            icons[0]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                check_manifest_pins(manifest, root)


if __name__ == "__main__":
    unittest.main()
