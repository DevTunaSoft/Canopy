"""Targeted tests for bounded Classic config schema versioning and migration.

Pure host-side contract tests only. No file, VM, credential or visual path is
touched; synthetic config bytes are parsed in memory.
"""

import ast
import json
from pathlib import Path
import unittest

from canopy_features.accessibility import reduced_motion_contract as motion
from canopy_features.settings import config_schema_migration as source
from canopy_features.settings import persisted_preferences as prefs


class CurrentSchemaTests(unittest.TestCase):
    def test_current_document_is_canonicalized_without_changing_values(self):
        raw = json.dumps({
            "version": 1,
            "values": {"reduced_motion": motion.REDUCE},
        }).encode("utf-8")
        result = source.migrate_document(raw)
        self.assertEqual(result, {
            "version": source.CURRENT_SCHEMA_VERSION,
            "values": {"reduced_motion": motion.REDUCE},
        })
        self.assertEqual(list(result["values"]), ["reduced_motion"])

    def test_current_document_with_empty_values_is_accepted(self):
        result = source.migrate_document(b'{"version":1,"values":{}}')
        self.assertEqual(result, {"version": 1, "values": {}})

    def test_current_schema_version_is_pinned_to_the_store(self):
        self.assertEqual(source.CURRENT_SCHEMA_VERSION, prefs.SCHEMA_VERSION)
        self.assertEqual(source.MAX_STATE_BYTES, prefs.MAX_STATE_BYTES)
        self.assertEqual(source.MAX_KEYS, prefs.MAX_KEYS)

    def test_result_does_not_alias_a_later_parse(self):
        raw = json.dumps({
            "version": 1, "values": {"reduced_motion": motion.FULL},
        }).encode("utf-8")
        first = source.migrate_document(raw)
        first["values"]["reduced_motion"] = "tampered"
        second = source.migrate_document(raw)
        self.assertEqual(second["values"]["reduced_motion"], motion.FULL)

    def test_input_bytes_are_unchanged(self):
        raw = b'{"version":1,"values":{"reduced_motion":"reduce"}}'
        before = bytes(raw)
        source.migrate_document(raw)
        self.assertEqual(raw, before)

    def test_text_source_is_bounded_and_accepted(self):
        result = source.migrate_document('{"reduced_motion":"full"}')
        self.assertEqual(result["values"], {"reduced_motion": motion.FULL})


class LegacySourceTests(unittest.TestCase):
    def test_flat_legacy_document_migrates_with_registered_step(self):
        raw = json.dumps({"reduced_motion": motion.REDUCE}).encode("utf-8")
        self.assertEqual(source.migration_plan(0), ("flat_preferences_to_v1",))
        self.assertEqual(source.migrate_document(raw), {
            "version": 1, "values": {"reduced_motion": motion.REDUCE},
        })

    def test_empty_flat_document_migrates_to_empty_values(self):
        self.assertEqual(source.migrate_document(b"{}"),
                         {"version": 1, "values": {}})

    def test_flat_source_with_several_allowed_keys_is_sorted(self):
        # Only reduced_motion is available today; a second key is a domain
        # violation and must not be silently dropped.
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"reduced_motion":"reduce","power":"suspend"}')

    def test_flat_source_cannot_hide_a_values_wrapper(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"values":{"reduced_motion":"reduce"}}')

    def test_explicit_legacy_version_wrapper_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"version":0,"values":{"reduced_motion":"reduce"}}')


class FailClosedDocumentTests(unittest.TestCase):
    def test_future_and_unknown_versions_are_refused(self):
        for raw in (b'{"version":2,"values":{}}',
                    b'{"version":-1,"values":{}}',
                    b'{"version":99,"values":{}}'):
            with self.subTest(raw=raw):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migrate_document(raw)

    def test_bool_and_wrong_type_versions_are_refused(self):
        for raw in (b'{"version":true,"values":{}}',
                    b'{"version":1.0,"values":{}}',
                    b'{"version":"1","values":{}}'):
            with self.subTest(raw=raw):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migrate_document(raw)

    def test_extra_top_level_field_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"version":1,"values":{},"note":"synthetic"}')

    def test_missing_values_field_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(b'{"version":1}')

    def test_duplicate_top_level_json_key_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"version":1,"version":1,"values":{}}')

    def test_duplicate_nested_json_key_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"version":1,"values":{"reduced_motion":"reduce",'
                b'"reduced_motion":"full"}}')

    def test_non_finite_json_constants_are_refused(self):
        for token in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(token=token):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migrate_document(
                        b'{"version":1,"values":{"reduced_motion":'
                        + token + b"}}")

    def test_invalid_utf8_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(b'{"reduced_motion":"\xff"}')

    def test_escaped_lone_surrogate_key_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(b'{"\\ud800":"reduce"}')

    def test_escaped_lone_surrogate_value_is_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"version":1,"values":{"reduced_motion":"\\ud800"}}')

    def test_oversized_source_refuses_before_full_decode(self):
        raw = b'{"reduced_motion":"reduce"}' + b" " * source.MAX_STATE_BYTES
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(raw)

    def test_huge_numeric_literal_translates_plain_value_error(self):
        raw = b'{"version":' + b"9" * 5000 + b',"values":{}}'
        with self.assertRaises(source.ConfigSchemaMigrationError) as raised:
            source.migrate_document(raw)
        self.assertIs(type(raised.exception), source.ConfigSchemaMigrationError)

    def test_deeply_nested_source_translates_recursion_error(self):
        raw = b"[" * 2000 + b"]" * 2000
        with self.assertRaises(source.ConfigSchemaMigrationError) as raised:
            source.migrate_document(raw)
        self.assertIs(type(raised.exception), source.ConfigSchemaMigrationError)

    def test_non_object_documents_are_refused(self):
        for raw in (b"[]", b"null", b'"text"', b"42", b"true"):
            with self.subTest(raw=raw):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migrate_document(raw)

    def test_wrong_source_container_types_are_refused(self):
        for raw in (None, 1, [], {}, object()):
            with self.subTest(raw=type(raw).__name__):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migrate_document(raw)

    def test_unavailable_and_unknown_keys_are_refused(self):
        for key in ("theme", "power", "shell_pack", "unknown"):
            with self.subTest(key=key):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migrate_document(
                        json.dumps({key: "reduce"}).encode("utf-8"))

    def test_wrong_value_types_and_out_of_domain_values_are_refused(self):
        for value in (1, None, ["reduce"], {}, "suspend", "reduce "):
            with self.subTest(value=value):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migrate_document(json.dumps({
                        "version": 1,
                        "values": {"reduced_motion": value},
                    }).encode("utf-8"))

    def test_nested_value_objects_are_refused(self):
        with self.assertRaises(source.ConfigSchemaMigrationError):
            source.migrate_document(
                b'{"version":1,"values":{"reduced_motion":{"value":"reduce"}}}')

    def test_value_domain_is_borrowed_from_the_store(self):
        allowed = prefs.KEYS["reduced_motion"]["values"]
        self.assertEqual(
            source.SOURCE_CONTRACTS[0].allowed_keys,
            frozenset(key for key, definition in prefs.KEYS.items()
                      if definition["available"]),
        )
        for value in allowed:
            with self.subTest(value=value):
                self.assertEqual(
                    source.migrate_document(json.dumps({
                        "version": 1,
                        "values": {"reduced_motion": value},
                    }).encode("utf-8"))["values"]["reduced_motion"],
                    value,
                )


class ContractAndPurityTests(unittest.TestCase):
    def test_source_contracts_are_immutable_and_bounded(self):
        contract = source.source_contract(0)
        self.assertEqual(contract.shape, "flat")
        self.assertEqual(contract.target_version, 1)
        self.assertEqual(contract.step, "flat_preferences_to_v1")
        self.assertLessEqual(contract.max_keys, prefs.MAX_KEYS)
        self.assertLessEqual(contract.max_bytes, prefs.MAX_STATE_BYTES)
        with self.assertRaises(TypeError):
            source.SOURCE_CONTRACTS[0] = contract  # type: ignore[index]
        with self.assertRaises(AttributeError):
            setattr(contract, "step", "changed")

    def test_source_contract_rejects_bool_and_unknown_versions(self):
        for version in (True, False, 1.0, "1", None, -1, 2):
            with self.subTest(version=version):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.source_contract(version)

    def test_migration_plan_is_bounded_and_deterministic(self):
        self.assertEqual(source.migration_plan(1), ())
        self.assertEqual(source.migration_plan(0),
                         source.migration_plan(0))
        self.assertLessEqual(len(source.migration_plan(0)),
                             source.MAX_MIGRATION_HOPS)
        for version in (True, 2, -1, "0", None):
            with self.subTest(version=version):
                with self.assertRaises(source.ConfigSchemaMigrationError):
                    source.migration_plan(version)

    def test_migration_steps_are_pinned_to_flat_sources_only(self):
        self.assertEqual(dict(source.MIGRATION_STEPS), {
            0: "flat_preferences_to_v1",
        })

    def test_module_has_no_filesystem_process_or_network_calls(self):
        tree = ast.parse(Path(source.__file__).read_text(encoding="utf-8"))
        forbidden_imports = {
            "os", "pathlib", "shutil", "subprocess", "socket", "tempfile",
        }
        forbidden_calls = {
            "open", "write", "writelines", "write_bytes", "write_text",
            "replace", "unlink", "remove", "rmdir", "mkdir", "chmod",
            "symlink", "system", "Popen",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0],
                                     forbidden_imports)
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertNotIn(module.split(".")[0], forbidden_imports)
            if isinstance(node, ast.Call):
                func = node.func
                name = (func.id if isinstance(func, ast.Name)
                        else func.attr if isinstance(func, ast.Attribute)
                        else "")
                self.assertNotIn(name, forbidden_calls)


if __name__ == "__main__":
    unittest.main()
