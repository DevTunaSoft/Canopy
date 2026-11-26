"""Synthetic-only checks for the bounded native launcher catalog producer.

Every fixture lives in a fresh temp directory. No test reads a real host
XDG_DATA_HOME, contacts a network, launches a process or writes repository
files. Evidence produced here is SYNTHETIC.
"""
from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from canopy_features.launcher import native_catalog_producer as producer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "canopy_features" / "launcher" / "native_catalog_producer.py"
DOC = ROOT / "docs" / "CLASSIC_NATIVE_CATALOG_PRODUCER.md"


def write_entry(apps: Path, filename: str, title: str = "Files",
                *, extra: str = "", data: bytes | None = None) -> Path:
    """Create one synthetic desktop entry inside a synthetic applications dir."""
    path = apps / filename
    if data is None:
        data = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={title}\n"
            "Exec=/usr/bin/synthetic\n"
            "Categories=Utility;\n"
            + extra
        ).encode("utf-8")
    path.write_bytes(data)
    return path


def tree_snapshot(root: Path):
    """Byte-and-name snapshot used to prove the producer performs no writes."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


class ProducerBridgeFormatTests(unittest.TestCase):
    def test_emits_headerless_lf_terminated_sorted_tsv(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            write_entry(apps, "org.example.Files.desktop", "Files")
            write_entry(apps, "org.example.Browser.desktop", "Browser")
            before = tree_snapshot(Path(folder))

            wire = producer.produce_catalog_bytes(apps)

            self.assertEqual(
                wire,
                b"org.example.Browser.desktop\tBrowser\n"
                b"org.example.Files.desktop\tFiles\n",
            )
            self.assertEqual(tree_snapshot(Path(folder)), before)


class ProducerBoundTests(unittest.TestCase):
    def test_snapshot_byte_cap_refuses_before_emitting(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            write_entry(apps, "org.example.Files.desktop", "Files")
            write_entry(apps, "org.example.Browser.desktop", "Browser")
            before = tree_snapshot(Path(folder))
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(apps, max_snapshot_bytes=40)
            self.assertEqual(tree_snapshot(Path(folder)), before)

    def test_directory_entry_cap_refuses_large_directory(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            for name in ("org.example.A.desktop", "org.example.B.desktop",
                         "org.example.C.desktop"):
                write_entry(apps, name, name.split(".")[2])
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(apps, max_directory_entries=2)

    def test_entry_size_cap_refuses_oversized_file(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            write_entry(apps, "org.example.Big.desktop", data=b"x" * 65)
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(apps, max_file_bytes=64)

    def test_entry_count_cap_refuses_extra_rows(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            for name in ("org.example.A.desktop", "org.example.B.desktop",
                         "org.example.C.desktop"):
                write_entry(apps, name, name.split(".")[2])
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(apps, max_entries=2)

    def test_hidden_entry_is_skipped_without_emitting_its_title(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            write_entry(apps, "org.example.Files.desktop", "Files")
            write_entry(apps, "org.example.Hidden.desktop", "NeverShown",
                        extra="Hidden=true\n")
            wire = producer.produce_catalog_bytes(apps)
            self.assertEqual(wire, b"org.example.Files.desktop\tFiles\n")
            self.assertNotIn(b"NeverShown", wire)

    def test_requires_explicit_absolute_applications_directory(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            root = Path(folder)
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes("applications")
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(root)
            apps = root / "applications"
            apps.mkdir()
            write_entry(apps, "org.example.Files.desktop", "Files")
            self.assertEqual(producer.produce_catalog_bytes(str(apps)),
                             b"org.example.Files.desktop\tFiles\n")

    def test_deterministic_order_independent_of_creation_order(self):
        wires = []
        for names in (("org.example.Zeta.desktop", "org.example.Alpha.desktop"),
                      ("org.example.Alpha.desktop", "org.example.Zeta.desktop")):
            with tempfile.TemporaryDirectory(
                    prefix="canopy-native-catalog-") as folder:
                apps = Path(folder) / "applications"
                apps.mkdir()
                for name in names:
                    write_entry(apps, name, name.split(".")[2])
                wires.append(producer.produce_catalog_bytes(apps))
        self.assertEqual(wires[0], wires[1])
        self.assertEqual(wires[0],
                         b"org.example.Alpha.desktop\tAlpha\n"
                         b"org.example.Zeta.desktop\tZeta\n")


class ProducerSymlinkTests(unittest.TestCase):
    @staticmethod
    def _symlink_or_skip(target, link):
        try:
            os.symlink(target, link)
        except OSError as exc:
            if getattr(exc, "winerror", None) in (5, 1314) or exc.errno == 1:
                raise unittest.SkipTest("synthetic symlink creation unavailable")
            raise

    def test_symlinked_desktop_entry_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            real = write_entry(apps, "org.example.Real.desktop", "Files")
            before = real.read_bytes()
            link = apps / "org.example.Link.desktop"
            self._symlink_or_skip(real.name, link)
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(apps)
            self.assertEqual(real.read_bytes(), before)

    def test_symlinked_applications_root_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            real = Path(folder) / "real-apps"
            real.mkdir()
            write_entry(real, "org.example.Files.desktop", "Files")
            alias = Path(folder) / "applications"
            self._symlink_or_skip(real, alias)
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(alias)


class ProducerHostileInputTests(unittest.TestCase):
    def test_hostile_filename_is_never_emitted(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            write_entry(apps, "org.example.Files.desktop", "Files")
            marker = "".join(["hostile", " ", "name", ".desktop"])
            write_entry(apps, marker, "NeverShown")
            wire = producer.produce_catalog_bytes(apps)
            self.assertEqual(wire, b"org.example.Files.desktop\tFiles\n")
            self.assertNotIn(marker.encode("utf-8"), wire)
            self.assertNotIn(b"NeverShown", wire)

    def test_hostile_content_is_refused_without_marker_echo(self):
        marker = "".join(["https://provider", ".invalid/", "TOKEN"])
        hostile = {
            "invalid_utf8": b"[Desktop Entry]\nName=\xff\nType=Application\nExec=/bin/x\n",
            "nul_byte": ("[Desktop Entry]\nType=Application\nName=A\x00B\n"
                         "Exec=/bin/x\n").encode("utf-8"),
            "carriage_return": ("[Desktop Entry]\nType=Application\n"
                                "Name=A\rB\nExec=/bin/x\n").encode("utf-8"),
            "bidi_control": ("[Desktop Entry]\nType=Application\nName=A\u202eB\n"
                             "Exec=/bin/x\n").encode("utf-8"),
            "embedded_tab": ("[Desktop Entry]\nType=Application\nName=A\tB\n"
                             "Exec=/bin/x\n").encode("utf-8"),
            "duplicate_key": ("[Desktop Entry]\nType=Application\nName=A\n"
                              "Name=B\nExec=/bin/x\n").encode("utf-8"),
            "wrong_type": ("[Desktop Entry]\nType=Link\nName=A\n"
                           "Exec=/bin/x\n").encode("utf-8"),
            "missing_exec": ("[Desktop Entry]\nType=Application\n"
                             "Name=A\n").encode("utf-8"),
            "marker_text": ("[Desktop Entry]\nType=Application\nName=" + marker
                            + "\x01\nExec=/bin/x\n").encode("utf-8"),
        }
        for label, data in hostile.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory(
                        prefix="canopy-native-catalog-") as folder:
                    apps = Path(folder) / "applications"
                    apps.mkdir()
                    write_entry(apps, "org.example.Hostile.desktop", data=data)
                    with self.assertRaises(producer.NativeCatalogError) as raised:
                        producer.produce_catalog_bytes(apps)
                    self.assertNotIn(marker, str(raised.exception))
                    self.assertEqual(
                        tree_snapshot(Path(folder)),
                        {"applications/org.example.Hostile.desktop": data})

    def test_control_character_directory_name_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            # The path is never created: Windows rejects control characters in
            # filenames, but the producer must reject the value before any I/O.
            bad = Path(folder) / ("applicati\x01ons")
            with self.assertRaises(producer.NativeCatalogError):
                producer.produce_catalog_bytes(bad)

    def test_no_network_process_or_write_primitives(self):
        text = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("import socket", "import urllib", "import subprocess",
                          "import shutil", "socket.", "urllib.", "subprocess.",
                          "os.system(", "popen(", "shutil.", "os.walk(",
                          "rglob(", "glob(", "O_CREAT", "O_WRONLY",
                          "write_bytes(", "write_text("):
            self.assertNotIn(forbidden, text, forbidden)
        for needed in ("os.scandir", "compose_launcher_catalog", "parse(",
                       "O_NOFOLLOW", "stat.S_ISLNK",
                       "sorted(snapshot.rows, key=lambda row: row.app_id)"):
            self.assertIn(needed, text, needed)
        # NTFS happens to return directory entries in name order, so a
        # behavioral two-directory test cannot fail on this host when the
        # explicit row sort is removed. Pin the cross-filesystem guard here.

    def test_documentation_carries_synthetic_and_not_run_labels(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC", text)
        self.assertIn("NOT_RUN", text)
        self.assertIn("app_id<TAB>title", text)
        self.assertIn("512", text)


class ProducerBoundedEnumerationTests(unittest.TestCase):
    def test_thousand_names_stop_at_limit_plus_one_without_partial_output(self):
        """Negative control for the directory-entry bound.

        The proxy is finite (1000 synthetic files), so unfixed code fails
        fast on the consumed-count assertion instead of hanging. It proves
        the scan stops on the first entry *after* the cap instead of
        materializing the whole hostile directory first.
        """
        with tempfile.TemporaryDirectory(prefix="canopy-native-catalog-") as folder:
            apps = Path(folder) / "applications"
            apps.mkdir()
            # File bodies are irrelevant here: a bounded scan must refuse
            # before reading any of them, so only the 1000 names matter.
            for index in range(1000):
                (apps / f"org.example.App{index:04d}.desktop").touch()
            before = tree_snapshot(Path(folder))

            real_scandir = os.scandir
            consumed = []

            class CountingScandir:
                """Finite proxy that records each name the producer consumes."""

                def __init__(self, path):
                    self._real = real_scandir(path)

                def __enter__(self):
                    self._real.__enter__()
                    return self

                def __exit__(self, *args):
                    return self._real.__exit__(*args)

                def __iter__(self):
                    for entry in self._real:
                        consumed.append(entry.name)
                        yield entry

            with mock.patch.object(producer.os, "scandir", CountingScandir):
                with self.assertRaises(producer.NativeCatalogError):
                    producer.produce_catalog_bytes(apps)

            # 512 names may be retained; entry 513 must refuse the snapshot
            # before the remaining 487 names are ever yielded.
            self.assertEqual(len(consumed), producer.MAX_DIRECTORY_ENTRIES + 1)
            self.assertLess(len(consumed), 1000)
            # No partial bytes and no output file: the call refused and the
            # synthetic tree is byte-for-byte unchanged.
            self.assertEqual(tree_snapshot(Path(folder)), before)
            self.assertEqual(
                [p.name for p in Path(folder).iterdir()
                 if p.name != "applications"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
