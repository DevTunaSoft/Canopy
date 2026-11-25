"""Independent security negative controls for the read-only Shell Pack registry."""

import json
from pathlib import Path
import tempfile
import unittest

from canopy_core.registry import (
    MAX_PACK_DIRECTORIES,
    PackScan,
    ShellPackInfo,
    scan_shell_packs,
)
from tools.check_shell_pack import (
    MAX_MANIFEST_BYTES,
    MAX_QML_ENTRYPOINT_BYTES,
    PackValidationError,
    validate_pack,
)


VALID_ID = "com.example.valid"


class RegistryNegativeControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "packs"
        self.root.mkdir()

    def _manifest(self, pack_id=VALID_ID, **overrides):
        manifest = {
            "manifest_version": 1,
            "id": pack_id,
            "name": "Valid Pack",
            "description": "Independent presentation",
            "shell_api": 1,
            "kind": "presentation",
            "ui_engine": "qt-qml",
            "entrypoint": "ui/Main.qml",
            "capabilities": ["dock"],
            "switch_strategy": "same-session",
            "permissions": [],
        }
        manifest.update(overrides)
        return manifest

    def _write_manifest(self, directory, manifest):
        (directory / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def _write_raw(self, directory, raw):
        target = directory / "manifest.json"
        if isinstance(raw, bytes):
            target.write_bytes(raw)
        else:
            target.write_text(raw, encoding="utf-8")

    def _add_pack(self, folder, pack_id=VALID_ID, manifest=None, qml_text="import QtQuick\nItem {}\n"):
        directory = self.root / folder
        directory.mkdir()
        (directory / "ui").mkdir()
        (directory / "ui" / "Main.qml").write_text(qml_text, encoding="utf-8")
        self._write_manifest(directory, manifest if manifest is not None
                             else self._manifest(pack_id))
        return directory

    def _outside(self, folder="outside"):
        directory = self.base / folder
        directory.mkdir(exist_ok=True)
        return directory

    def _problem_reasons(self, report):
        return [problem.reason for problem in report.problems]

    def test_missing_catalog_root_rejected(self):
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(self.root / "missing")

    def test_regular_file_as_catalog_root_rejected(self):
        catalog_file = self.base / "catalog.txt"
        catalog_file.write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(catalog_file)

    def test_symlink_catalog_root_rejected(self):
        alias = self.base / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(alias)

    def test_broken_symlink_catalog_root_rejected(self):
        alias = self.base / "broken"
        alias.symlink_to(self.base / "does-not-exist", target_is_directory=True)
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(alias)

    def test_catalog_above_entry_bound_rejected(self):
        for n in range(MAX_PACK_DIRECTORIES + 1):
            (self.root / f"entry-{n:03}").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(PackValidationError, "64 entries"):
            scan_shell_packs(self.root)

    def test_catalog_at_entry_bound_accepted(self):
        for n in range(MAX_PACK_DIRECTORIES):
            (self.root / f"entry-{n:03}").write_text("x", encoding="utf-8")
        report = scan_shell_packs(self.root)
        self.assertIsInstance(report, PackScan)
        self.assertEqual(report.packs, ())
        self.assertEqual(report.problems, ())

    def test_ordinary_catalog_files_ignored(self):
        (self.root / "README.md").write_text("docs", encoding="utf-8")
        (self.root / ".DS_Store").write_bytes(b"\x00")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.checked_directories, 0)
        self.assertEqual(report.problems, ())

    def test_invalid_json_text_rejected(self):
        directory = self._add_pack("bad-json")
        self._write_raw(directory, "{not valid json")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("invalid manifest JSON", self._problem_reasons(report)[0])

    def test_invalid_utf8_manifest_rejected(self):
        directory = self._add_pack("bad-utf8")
        self._write_raw(directory, b"\xff\xfe not json")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("invalid manifest JSON", self._problem_reasons(report)[0])

    def test_duplicate_json_key_rejected(self):
        directory = self._add_pack("dup-key")
        self._write_raw(directory, '{"manifest_version": 1, "manifest_version": 1}')
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("duplicate JSON key", self._problem_reasons(report)[0])

    def test_nan_json_constant_rejected(self):
        directory = self._add_pack("nan")
        raw = json.dumps(self._manifest()).replace('"shell_api": 1', '"shell_api": NaN')
        self._write_raw(directory, raw)
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("invalid JSON constant", self._problem_reasons(report)[0])

    def test_infinity_json_constant_rejected(self):
        directory = self._add_pack("infinity")
        raw = json.dumps(self._manifest()).replace('"shell_api": 1', '"shell_api": Infinity')
        self._write_raw(directory, raw)
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("invalid JSON constant", self._problem_reasons(report)[0])

    def test_manifest_top_level_array_rejected(self):
        directory = self._add_pack("array")
        self._write_raw(directory, "[]")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("one JSON object", self._problem_reasons(report)[0])

    def test_missing_required_field_rejected(self):
        manifest = self._manifest()
        del manifest["capabilities"]
        directory = self._add_pack("missing-field", manifest=manifest)
        with self.assertRaisesRegex(PackValidationError, "unexpected manifest fields"):
            validate_pack(directory)
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())

    def test_extra_manifest_field_rejected(self):
        manifest = self._manifest()
        manifest["trusted"] = True
        directory = self._add_pack("extra-field", manifest=manifest)
        with self.assertRaisesRegex(PackValidationError, "unexpected manifest fields"):
            validate_pack(directory)

    def test_boolean_version_fields_rejected(self):
        for field in ("manifest_version", "shell_api"):
            with self.subTest(field=field):
                directory = self._add_pack(f"bool-{field}", manifest=self._manifest(**{field: True}))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_wrong_version_fields_rejected(self):
        for field in ("manifest_version", "shell_api"):
            with self.subTest(field=field):
                directory = self._add_pack(f"wrong-{field}", manifest=self._manifest(**{field: 2}))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_unsupported_kind_engine_strategy_rejected(self):
        for field, value in (("kind", "utility"), ("ui_engine", "web"),
                             ("switch_strategy", "restart-session")):
            with self.subTest(field=field):
                directory = self._add_pack(f"unsupported-{field}",
                                            manifest=self._manifest(**{field: value}))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_hostile_name_shapes_rejected(self):
        for value in ("", "   ", " padded ", "A\x00B", "A\nB", 42, None):
            with self.subTest(value=value):
                directory = self._add_pack(f"name-{abs(hash(str(value))) % 100000}",
                                            manifest=self._manifest(name=value))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_hostile_description_shapes_rejected(self):
        for value in ("", " ", "x\x1fy", 7):
            with self.subTest(value=value):
                directory = self._add_pack(f"desc-{abs(hash(str(value))) % 100000}",
                                            manifest=self._manifest(description=value))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_hostile_capability_shapes_rejected(self):
        cases = ([], ["dock", "dock"], ["unknown-cap"], "dock", [None], [{"x": 1}])
        for caps in cases:
            with self.subTest(caps=caps):
                directory = self._add_pack(f"caps-{abs(hash(str(caps))) % 100000}",
                                            manifest=self._manifest(capabilities=caps))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_permissions_must_be_empty_list(self):
        for permissions in (["run-shell"], "root", None, {}):
            with self.subTest(permissions=permissions):
                directory = self._add_pack(f"perm-{abs(hash(str(permissions))) % 100000}",
                                            manifest=self._manifest(permissions=permissions))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_hostile_id_shapes_rejected(self):
        ids = ("", "Single", "com.Example.ok", "com..example", "com.example",
               "org.canopy.trusted", 123, "../../etc/passwd")
        for pack_id in ids:
            with self.subTest(pack_id=pack_id):
                directory = self._add_pack(f"id-{abs(hash(str(pack_id))) % 100000}",
                                            manifest=self._manifest(pack_id))
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_symlink_manifest_rejected(self):
        directory = self._add_pack("symlink-manifest")
        real_manifest = self.base / "real-manifest.json"
        real_manifest.write_text(json.dumps(self._manifest()), encoding="utf-8")
        (directory / "manifest.json").unlink()
        (directory / "manifest.json").symlink_to(real_manifest)
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("regular local file", self._problem_reasons(report)[0])

    def test_invalid_manifest_does_not_block_valid_neighbor(self):
        bad = self._add_pack("bad")
        self._write_manifest(bad, self._manifest(permissions=["root"]))
        self._add_pack("good", "com.example.good")
        report = scan_shell_packs(self.root)
        self.assertEqual([p.pack_id for p in report.packs], ["com.example.good"])
        self.assertEqual(len(report.problems), 1)

    def test_entrypoint_traversal_variants_rejected(self):
        variants = (
            "ui/../Main.qml",
            "/ui/Main.qml",
            "ui//Main.qml",
            "ui/./Main.qml",
            "ui\\..\\Main.qml",
            "ui/sub/../../Main.qml",
            "ui/Main.qml/../Main.qml",
            "Main.qml",
            "ui/Nope.qml",
            "ui/Main.qml/child.qml",
            "UI/Main.qml",
            "ui/.hidden.qml",
            "",
        )
        for entrypoint in variants:
            with self.subTest(entrypoint=entrypoint):
                directory = self._add_pack(
                    f"ep-{abs(hash(entrypoint)) % 100000}",
                    manifest=self._manifest(entrypoint=entrypoint),
                )
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_entrypoint_directory_not_treated_as_file(self):
        directory = self._add_pack("entrypoint-dir")
        (directory / "ui" / "Main.qml").unlink()
        (directory / "ui" / "Main.qml").mkdir()
        with self.assertRaisesRegex(PackValidationError, "missing"):
            validate_pack(directory)

    def test_entrypoint_symlink_component_rejected(self):
        directory = self.root / "symlink-ui"
        directory.mkdir()
        self._write_manifest(directory, self._manifest())
        outside = self._outside()
        (outside / "Main.qml").write_text("import QtQuick\nItem {}\n", encoding="utf-8")
        (directory / "ui").symlink_to(outside, target_is_directory=True)
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("symlink", self._problem_reasons(report)[0])

    def test_entrypoint_symlink_final_file_rejected(self):
        directory = self._add_pack("symlink-file")
        outside = self._outside()
        (outside / "Main.qml").write_text("import QtQuick\nItem {}\n", encoding="utf-8")
        (directory / "ui" / "Main.qml").unlink()
        (directory / "ui" / "Main.qml").symlink_to(outside / "Main.qml")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("symlink", self._problem_reasons(report)[0])

    def test_traversal_entrypoint_never_executes_pack_text(self):
        side_effect = self.base / "would-be-side-effect.txt"
        qml_text = "INVALID QML\n// would create " + str(side_effect) + "\n"
        self._add_pack("inert", manifest=self._manifest(), qml_text=qml_text)
        report = scan_shell_packs(self.root)
        self.assertEqual(len(report.packs), 1)
        self.assertFalse(side_effect.exists())

    def test_pack_directory_symlink_rejected_by_registry(self):
        outside = self._outside()
        external_pack = outside / "external"
        external_pack.mkdir()
        (external_pack / "ui").mkdir()
        (external_pack / "ui" / "Main.qml").write_text("x", encoding="utf-8")
        self._write_manifest(external_pack, self._manifest("com.example.external"))
        (self.root / "escape").symlink_to(external_pack, target_is_directory=True)
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertIn("symlink", self._problem_reasons(report)[0])

    def test_symlink_pack_does_not_duplicate_valid_pack(self):
        real_pack = self._add_pack("real", "com.example.real")
        (self.root / "link").symlink_to(real_pack, target_is_directory=True)
        report = scan_shell_packs(self.root)
        self.assertEqual([p.pack_id for p in report.packs], ["com.example.real"])
        self.assertEqual(len(report.problems), 1)

    def test_duplicate_ids_excluded_without_winner(self):
        self._add_pack("a", "com.example.duplicate")
        self._add_pack("b", "com.example.duplicate")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertEqual(len(report.problems), 2)
        self.assertTrue(all("duplicate" in reason for reason in self._problem_reasons(report)))

    def test_three_colliding_ids_all_excluded(self):
        for folder in ("a", "b", "c"):
            self._add_pack(folder, "com.example.triple")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertEqual(len(report.problems), 3)

    def test_duplicate_id_keeps_unrelated_valid_pack(self):
        self._add_pack("a", "com.example.duplicate")
        self._add_pack("b", "com.example.duplicate")
        self._add_pack("c", "com.example.unique")
        report = scan_shell_packs(self.root)
        self.assertEqual([p.pack_id for p in report.packs], ["com.example.unique"])

    def test_case_variant_id_is_rejected_not_merged(self):
        self._add_pack("a", "com.example.case")
        self._add_pack("b", "com.example.CASE")
        report = scan_shell_packs(self.root)
        self.assertEqual([p.pack_id for p in report.packs], ["com.example.case"])
        self.assertEqual(len(report.problems), 1)

    def test_discovered_directory_is_resolved_absolute(self):
        directory = self._add_pack("resolve", "com.example.resolve")
        info = scan_shell_packs(self.root).get("com.example.resolve")
        self.assertTrue(info.directory.is_absolute())
        self.assertEqual(info.directory, directory.resolve(strict=True))
        self.assertNotIn("..", info.directory.parts)

    def test_get_is_exact_case_and_not_a_filesystem_lookup(self):
        self._add_pack("lookup", "com.example.lookup")
        report = scan_shell_packs(self.root)
        self.assertIsInstance(report.get("com.example.lookup"), ShellPackInfo)
        for query in ("COM.EXAMPLE.LOOKUP", "../../etc/passwd", "ui/../Main.qml", "",
                      "com.example.lookup ", "com.example.missing"):
            with self.subTest(query=query):
                self.assertIsNone(report.get(query))

    def test_compatible_requires_frozenset_and_is_subset_filter(self):
        self._add_pack("small", "com.example.small")
        self._add_pack("large", "com.example.large",
                       manifest=self._manifest("com.example.large", capabilities=["dock", "top-bar"]))
        report = scan_shell_packs(self.root)
        self.assertEqual(len(report.compatible(frozenset({"dock"}))), 1)
        self.assertEqual(len(report.compatible(frozenset({"dock", "top-bar"}))), 2)
        self.assertEqual(len(report.compatible(frozenset())), 0)
        with self.assertRaises(TypeError):
            report.compatible(["dock"])

    def test_shellpackinfo_is_immutable_metadata(self):
        self._add_pack("immutable", "com.example.immutable")
        info = scan_shell_packs(self.root).get("com.example.immutable")
        with self.assertRaises(AttributeError):
            info.pack_id = "tampered"

    def test_name_length_boundary(self):
        directory = self._add_pack("name-len", manifest=self._manifest(name="A" * 80))
        self.assertEqual(validate_pack(directory)["name"], "A" * 80)
        too_long = self._add_pack("name-over", manifest=self._manifest(name="A" * 81))
        with self.assertRaises(PackValidationError):
            validate_pack(too_long)

    def test_description_length_boundary(self):
        directory = self._add_pack("desc-len", manifest=self._manifest(description="D" * 240))
        self.assertEqual(validate_pack(directory)["description"], "D" * 240)
        too_long = self._add_pack("desc-over", manifest=self._manifest(description="D" * 241))
        with self.assertRaises(PackValidationError):
            validate_pack(too_long)

    def test_id_length_boundary(self):
        exact = "com.example." + "a" * 116
        over = "com.example." + "a" * 117
        self.assertEqual(len(exact), 128)
        directory = self._add_pack("id-len", manifest=self._manifest(exact))
        self.assertEqual(validate_pack(directory)["id"], exact)
        too_long = self._add_pack("id-over", manifest=self._manifest(over))
        with self.assertRaises(PackValidationError):
            validate_pack(too_long)

    def test_manifest_byte_size_boundary(self):
        base_len = len(json.dumps(self._manifest()))
        exact = self._add_pack("manifest-len")
        padding = MAX_MANIFEST_BYTES - base_len
        self._write_raw(exact, json.dumps(self._manifest()) + " " * padding)
        self.assertEqual((exact / "manifest.json").stat().st_size, MAX_MANIFEST_BYTES)
        self.assertEqual(validate_pack(exact)["id"], VALID_ID)
        over = self._add_pack("manifest-over")
        self._write_raw(over, json.dumps(self._manifest()) + " " * (padding + 1))
        with self.assertRaisesRegex(PackValidationError, "16 KiB"):
            validate_pack(over)

    def test_qml_entrypoint_byte_size_boundary(self):
        directory = self.root / "qml-len"
        directory.mkdir()
        (directory / "ui").mkdir()
        (directory / "ui" / "Main.qml").write_bytes(b"x" * MAX_QML_ENTRYPOINT_BYTES)
        self._write_manifest(directory, self._manifest())
        self.assertEqual(validate_pack(directory)["id"], VALID_ID)
        over = self.root / "qml-over"
        over.mkdir()
        (over / "ui").mkdir()
        (over / "ui" / "Main.qml").write_bytes(b"x" * (MAX_QML_ENTRYPOINT_BYTES + 1))
        self._write_manifest(over, self._manifest())
        with self.assertRaisesRegex(PackValidationError, "1 MiB"):
            validate_pack(over)

    def test_top_level_json_scalars_rejected(self):
        for raw in ("null", '"string"', "3", "true", "[]"):
            with self.subTest(raw=raw):
                directory = self._add_pack(f"scalar-{abs(hash(raw)) % 100000}")
                self._write_raw(directory, raw)
                with self.assertRaisesRegex(PackValidationError, "one JSON object"):
                    validate_pack(directory)

    def test_empty_json_object_rejected(self):
        directory = self._add_pack("empty-object")
        self._write_raw(directory, "{}")
        with self.assertRaisesRegex(PackValidationError, "unexpected manifest fields"):
            validate_pack(directory)

    def test_bom_prefixed_manifest_rejected(self):
        directory = self._add_pack("bom")
        raw = b"\xef\xbb\xbf" + json.dumps(self._manifest()).encode("utf-8")
        self._write_raw(directory, raw)
        with self.assertRaisesRegex(PackValidationError, "invalid manifest JSON"):
            validate_pack(directory)

    def test_manifest_json_as_directory_rejected(self):
        directory = self._add_pack("manifest-dir")
        (directory / "manifest.json").unlink()
        (directory / "manifest.json").mkdir()
        with self.assertRaisesRegex(PackValidationError, "regular local file"):
            validate_pack(directory)

    def test_entrypoint_nested_symlink_component_rejected(self):
        directory = self.root / "nested-symlink"
        directory.mkdir()
        (directory / "ui").mkdir()
        (directory / "ui" / "Main.qml").write_text(
            "import QtQuick\nItem {}\n", encoding="utf-8"
        )
        outside = self._outside("nested-outside")
        (outside / "Main.qml").write_text("import QtQuick\nItem {}\n", encoding="utf-8")
        (directory / "ui" / "sub").symlink_to(outside, target_is_directory=True)
        self._write_manifest(directory, self._manifest(entrypoint="ui/sub/Main.qml"))
        with self.assertRaisesRegex(PackValidationError, "symlink"):
            validate_pack(directory)

    def test_entrypoint_broken_symlink_final_rejected(self):
        directory = self._add_pack("broken-entry")
        (directory / "ui" / "Main.qml").unlink()
        (directory / "ui" / "Main.qml").symlink_to(self.base / "no-such-target.qml")
        with self.assertRaisesRegex(PackValidationError, "symlink"):
            validate_pack(directory)

    def test_entrypoint_encoded_traversal_rejected(self):
        variants = ("ui/%2e%2e/Main.qml", "ui/Main.qml%00", "ui/..%2fMain.qml")
        for entrypoint in variants:
            with self.subTest(entrypoint=entrypoint):
                directory = self._add_pack(
                    f"enc-{abs(hash(entrypoint)) % 100000}",
                    manifest=self._manifest(entrypoint=entrypoint),
                )
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_duplicate_id_with_invalid_neighbor_not_miscounted(self):
        self._add_pack("valid", "com.example.collide")
        invalid = self._add_pack("invalid", "com.example.collide")
        self._write_manifest(
            invalid, self._manifest("com.example.collide", permissions=["root"])
        )
        report = scan_shell_packs(self.root)
        self.assertEqual([p.pack_id for p in report.packs], ["com.example.collide"])
        self.assertEqual(len(report.problems), 1)
        self.assertIn("permissions", self._problem_reasons(report)[0])

    def test_packs_sorted_deterministically(self):
        for folder, pack_id in (("z", "com.example.zed"),
                                ("a", "com.example.alpha"),
                                ("m", "com.example.middle")):
            self._add_pack(folder, pack_id)
        report = scan_shell_packs(self.root)
        self.assertEqual(
            [p.pack_id for p in report.packs],
            ["com.example.alpha", "com.example.middle", "com.example.zed"],
        )

    def test_checked_directories_excludes_files_and_broken_symlinks(self):
        self._add_pack("one", "com.example.one")
        self._add_pack("two", "com.example.two")
        (self.root / "notes.txt").write_text("docs", encoding="utf-8")
        (self.root / "dangling").symlink_to(self.base / "missing")
        report = scan_shell_packs(self.root)
        self.assertEqual(len(report.packs), 2)
        self.assertEqual(report.checked_directories, 2)
        self.assertIn("symlink", self._problem_reasons(report)[0])


    def test_validate_pack_rejects_symlink_root_directly(self):
        real = self._add_pack("direct-root")
        outside = self._outside()
        alias = outside / "pack-alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(PackValidationError, "real local directory"):
            validate_pack(alias)

    def test_entrypoint_type_confusions_rejected(self):
        values = (None, 1, True, ["ui/Main.qml"], {"path": "ui/Main.qml"})
        for index, entrypoint in enumerate(values):
            with self.subTest(entrypoint=entrypoint):
                directory = self._add_pack(
                    f"ep-type-{index}",
                    manifest=self._manifest(entrypoint=entrypoint),
                )
                with self.assertRaisesRegex(PackValidationError, "local"):
                    validate_pack(directory)

    def test_kind_engine_strategy_type_confusions_rejected(self):
        values = (None, 7, True, [], {})
        for field in ("kind", "ui_engine", "switch_strategy"):
            for index, value in enumerate(values):
                with self.subTest(field=field, value=value):
                    directory = self._add_pack(
                        f"tc-{field}-{index}",
                        manifest=self._manifest(**{field: value}),
                    )
                    with self.assertRaises(PackValidationError):
                        validate_pack(directory)

    def test_reserved_id_prefix_variants_rejected(self):
        ids = ("org.canopy.trusted", "org.canopy.shell", "org.canopy.a.b")
        for index, pack_id in enumerate(ids):
            with self.subTest(pack_id=pack_id):
                directory = self._add_pack(
                    f"reserved-{index}", manifest=self._manifest(pack_id)
                )
                with self.assertRaisesRegex(PackValidationError, "reserved"):
                    validate_pack(directory)

    def test_id_regex_edge_shapes_rejected(self):
        ids = ("1com.example.a", "-com.example.a", "com.example.a_b",
               "com.example.A", "com.example.a b", "com.example.a/b",
               "com.example.", "com..example.a")
        for index, pack_id in enumerate(ids):
            with self.subTest(pack_id=pack_id):
                directory = self._add_pack(
                    f"id-edge-{index}", manifest=self._manifest(pack_id)
                )
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_valid_multisegment_id_with_hyphens_accepted(self):
        pack_id = "com.example-my.shell-pack.v1"
        directory = self._add_pack("hyphen-id", manifest=self._manifest(pack_id))
        self.assertEqual(validate_pack(directory)["id"], pack_id)

    def test_entrypoint_component_name_shapes_rejected(self):
        variants = ("ui/Bad.Name.qml", "ui/1main.qml", "ui/Bad Name.qml",
                    "ui/caf\u00e9.qml", "ui/with@symbol.qml",
                    "ui/A.qml/../Main.qml")
        for index, entrypoint in enumerate(variants):
            with self.subTest(entrypoint=entrypoint):
                directory = self._add_pack(
                    f"ep-name-{index}", manifest=self._manifest(entrypoint=entrypoint)
                )
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_entrypoint_symlink_loop_rejected(self):
        directory = self._add_pack("entry-loop")
        (directory / "ui" / "Main.qml").unlink()
        (directory / "ui" / "Main.qml").symlink_to("Main.qml")
        with self.assertRaisesRegex(PackValidationError, "symlink"):
            validate_pack(directory)

    def test_manifest_utf16_text_rejected(self):
        directory = self._add_pack("utf16")
        self._write_raw(directory, json.dumps(self._manifest()).encode("utf-16"))
        with self.assertRaisesRegex(PackValidationError, "invalid manifest JSON"):
            validate_pack(directory)

    def test_capabilities_wrong_container_types_rejected(self):
        for index, caps in enumerate(({"dock": True}, (), "dock", 5, None)):
            with self.subTest(caps=caps):
                directory = self._add_pack(
                    f"caps-type-{index}", manifest=self._manifest(capabilities=caps)
                )
                with self.assertRaises(PackValidationError):
                    validate_pack(directory)

    def test_duplicate_id_problem_locations_are_folder_names(self):
        self._add_pack("first", "com.example.dup-loc")
        self._add_pack("second", "com.example.dup-loc")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertEqual(sorted(p.location for p in report.problems),
                         ["first", "second"])


if __name__ == "__main__":
    unittest.main()
