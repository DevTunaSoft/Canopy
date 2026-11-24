"""Contract tests for the pure security decision snapshot composition.

Run: python -m unittest tests.test_c100_security_decision_snapshot -v
"""
import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from unittest import mock

from canopy_features.security import privilege_boundary as priv
from canopy_features.security import untrusted_uri_schemes as uri
from canopy_features.security.security_decision_snapshot import (
    CAPABILITIES,
    MAX_MANIFEST_FIELDS,
    PRIVILEGE_REASONS,
    SCHEMA,
    SecurityDecisionSnapshot,
    SnapshotError,
    compose_decision,
    snapshot,
)

NEGATIVE_CLAIMS = (
    "launch_authorized", "process_launched", "release_approved",
    "linux_mint_acceptance_proven", "real_hardware_measured",
    "owner_visual_approval", "measurement_performed",
)


def manifest():
    return {
        "manifest_version": 1,
        "id": "com.community.calm.desktop",
        "name": "Calm Desktop",
        "description": "An original Canopy presentation pack",
        "shell_api": 1,
        "kind": "presentation",
        "ui_engine": "qt-qml",
        "entrypoint": "ui/Main.qml",
        "capabilities": ["dock", "app-launcher"],
        "switch_strategy": "same-session",
        "permissions": [],
    }


def record(uri_intent="https://example.org/", argv=("eog", "--fullscreen"),
           man=None, euid=1000):
    return {
        "schema": SCHEMA,
        "uri_intent": uri_intent,
        "argv": argv,
        "manifest": manifest() if man is None else man,
        "euid": euid,
    }


def compose(rec):
    return snapshot(rec).as_dict()


class RealCompositionTests(unittest.TestCase):
    def test_all_boundaries_permit(self):
        out = compose(record())
        self.assertEqual(out["status"], "SNAPSHOT")
        self.assertEqual(out["schema"], SCHEMA)
        self.assertEqual(out["uri_status"], "PERMITTED")
        self.assertEqual(out["privilege_status"], "ALLOWED")
        self.assertEqual(out["privilege_reason"], priv.ALLOWED)
        self.assertEqual(out["metadata_status"], "SAFE")
        self.assertEqual(out["metadata_capability_count"], 2)

    def test_all_negative_claims_hardcoded(self):
        out = compose(record())
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_rejected_uri_is_isolated(self):
        out = compose(record(uri_intent="javascript:alert(1)"))
        self.assertEqual(out["uri_status"], "REJECTED")
        self.assertEqual(out["privilege_status"], "ALLOWED")
        self.assertEqual(out["metadata_status"], "SAFE")

    def test_denied_privilege_reason_is_a_fixed_code(self):
        out = compose(record(argv=("sudo", "mount", "/")))
        self.assertEqual(out["privilege_status"], "DENIED")
        self.assertIn(out["privilege_reason"], PRIVILEGE_REASONS)
        self.assertNotEqual(out["privilege_reason"], priv.ALLOWED)

    def test_empty_argv_reason(self):
        out = compose(record(argv=()))
        self.assertEqual(out["privilege_reason"], priv.DENIED_EMPTY_ACTION)

    def test_oversized_argv_reason(self):
        out = compose(record(argv=("eog",) * (priv.MAX_ARGUMENTS + 1)))
        self.assertEqual(out["privilege_reason"], priv.DENIED_OVERSIZED)

    def test_inherited_root_reason(self):
        out = compose(record(euid=0))
        self.assertEqual(out["privilege_reason"], priv.DENIED_INHERITED_ROOT)

    def test_none_euid_is_explicit_and_deterministic(self):
        out = compose(record(euid=None))
        self.assertEqual(out["privilege_status"], "ALLOWED")

    def test_unsafe_metadata_is_isolated(self):
        man = manifest()
        man["exec-path"] = "/bin/sh"
        out = compose(record(man=man))
        self.assertEqual(out["metadata_status"], "REJECTED")
        self.assertEqual(out["metadata_capability_count"], 0)
        self.assertEqual(out["uri_status"], "PERMITTED")
        self.assertEqual(out["privilege_status"], "ALLOWED")

    def test_no_capabilities_metadata_rejected(self):
        man = manifest()
        man["capabilities"] = []
        self.assertEqual(compose(record(man=man))["metadata_status"], "REJECTED")

    def test_oversize_manifest_mapping_prebounded(self):
        man = manifest()
        for index in range(MAX_MANIFEST_FIELDS):
            man["field_" + str(index)] = "x"
        out = compose(record(man=man))
        self.assertEqual(out["metadata_status"], "REJECTED")
        self.assertEqual(out["metadata_capability_count"], 0)

    def test_mutually_hostile_inputs_all_refused(self):
        man = manifest()
        man["exec-path"] = "/bin/sh"
        out = compose(record("javascript:alert(1)", ("sudo", "reboot"), man, 0))
        self.assertEqual(out["uri_status"], "REJECTED")
        self.assertEqual(out["privilege_status"], "DENIED")
        self.assertEqual(out["metadata_status"], "REJECTED")
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_no_raw_value_echo(self):
        out = compose(record(
            uri_intent="https://SECRET_URI_MARKER.example/",
            argv=("SECRET_ARG_MARKER",),
            man=dict(manifest(), name="SECRET_NAME_MARKER"),
        ))
        rendered = json.dumps(out, sort_keys=True)
        for marker in ("SECRET_URI_MARKER", "SECRET_ARG_MARKER",
                       "SECRET_NAME_MARKER"):
            self.assertNotIn(marker, rendered)

    def test_deterministic_bytes(self):
        rec = record()
        self.assertEqual(
            json.dumps(compose(rec), sort_keys=True),
            json.dumps(compose(rec), sort_keys=True),
        )

    def test_no_live_alias_to_caller_containers(self):
        argv = ["eog"]
        man = manifest()
        rec = record(argv=argv, man=man)
        made = snapshot(rec)
        argv.append("sudo")
        man["name"] = "Changed"
        rec["uri_intent"] = "javascript:alert(1)"
        out = made.as_dict()
        self.assertEqual(out["uri_status"], "PERMITTED")
        self.assertEqual(out["privilege_status"], "ALLOWED")
        self.assertEqual(out["metadata_status"], "SAFE")


class WrapperBoundaryTests(unittest.TestCase):
    def test_bad_key_set(self):
        for bad in ({}, {"schema": 1}, dict(record(), extra=1)):
            with self.subTest(keys=sorted(bad)), self.assertRaises(SnapshotError):
                snapshot(bad)

    def test_non_dict_wrapper(self):
        for bad in (None, [], 7, "x", True):
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                snapshot(bad)

    def test_wrong_schema(self):
        for bad in ("1", True, 2, 1.0, None):
            rec = record()
            rec["schema"] = bad
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                snapshot(rec)

    def test_invalid_euid(self):
        for bad in (-1, 2 ** 32, True, 1.0, "1000", [], {}):
            rec = record(euid=bad)
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                snapshot(rec)

    def test_compose_decision_rejects_bad_euid(self):
        with self.assertRaises(SnapshotError):
            compose_decision(uri_intent="https://x/", argv=[], manifest=manifest(),
                             euid=-1)


class ForgedRecordTests(unittest.TestCase):
    def make(self, **overrides):
        values = dict(
            schema=SCHEMA, uri_status="PERMITTED",
            privilege_status="ALLOWED", privilege_reason=priv.ALLOWED,
            metadata_status="SAFE", metadata_capability_count=2,
        )
        values.update(overrides)
        return SecurityDecisionSnapshot(**values)

    def test_forged_record_cannot_authorize_launch(self):
        out = self.make().as_dict()
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_bad_status_tokens_fail_closed(self):
        for field, bad in (
            ("uri_status", "APPROVED"),
            ("privilege_status", "APPROVED"),
            ("metadata_status", "APPROVED"),
            ("privilege_reason", "APPROVED"),
        ):
            with self.subTest(field=field), self.assertRaises(SnapshotError):
                self.make(**{field: bad}).as_dict()

    def test_unhashable_status_token_fails_closed(self):
        # Type-check must precede frozenset membership (item 11 contract).
        for bad in ([], {}, bytearray(), 7, None):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(SnapshotError):
                self.make(uri_status=bad).as_dict()

    def test_contradictory_privilege_flags_fail_closed(self):
        # A forged record must not emit a "ALLOWED" status while its reason
        # code is a denial (or vice versa). Each field is a valid token on
        # its own, but the pair is contradictory: the reason is the ground
        # truth from the privilege validator, so status must agree with it.
        denied_reasons = PRIVILEGE_REASONS - {priv.ALLOWED}
        for reason in sorted(denied_reasons):
            with self.subTest(reason=reason), self.assertRaises(SnapshotError):
                self.make(privilege_status="ALLOWED",
                          privilege_reason=reason).as_dict()
        with self.assertRaises(SnapshotError):
            self.make(privilege_status="DENIED",
                      privilege_reason=priv.ALLOWED).as_dict()

    def test_consistent_privilege_flags_still_serialize(self):
        # Guard against over-rejection: the two real, self-consistent pairs
        # must remain serializable.
        allowed = self.make(privilege_status="ALLOWED",
                            privilege_reason=priv.ALLOWED).as_dict()
        self.assertEqual(allowed["privilege_status"], "ALLOWED")
        denied = self.make(privilege_status="DENIED",
                           privilege_reason=priv.DENIED_ELEVATION).as_dict()
        self.assertEqual(denied["privilege_status"], "DENIED")
        self.assertEqual(denied["privilege_reason"], priv.DENIED_ELEVATION)

    def test_bad_counts_fail_closed(self):
        for bad in (-1, len(CAPABILITIES) + 1, True, "2", None):
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                self.make(metadata_capability_count=bad).as_dict()

    def test_bad_schema_fails_closed(self):
        for bad in (0, 2, "1", True, None):
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                self.make(schema=bad).as_dict()

    def test_report_is_frozen(self):
        rec = self.make()
        with self.assertRaises(FrozenInstanceError):
            rec.uri_status = "REJECTED"

    def test_as_dict_returns_fresh_container(self):
        rec = self.make()
        first = rec.as_dict()
        first["uri_status"] = "REJECTED"
        self.assertEqual(rec.as_dict()["uri_status"], "PERMITTED")


class PurityTests(unittest.TestCase):
    def test_no_io_exec_or_environment_imports(self):
        module_file = Path(__file__).resolve().parents[1] / (
            "canopy_features/security/security_decision_snapshot.py")
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
        allowed = {
            "collections", "dataclasses", "canopy_features", "tools",
        }
        forbidden = {
            "os", "time", "random", "subprocess", "socket", "threading",
            "datetime", "multiprocessing", "ctypes", "pathlib", "importlib",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(top, forbidden)
                    self.assertIn(top, allowed)
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                self.assertNotIn(top, forbidden)
                self.assertIn(top, allowed)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, {"system", "popen", "Popen",
                                                  "geteuid", "spawn"})

    def test_does_not_call_elevation_detection(self):
        with mock.patch.object(priv, "current_euid",
                               side_effect=AssertionError("called")):
            self.assertEqual(compose(record())["privilege_status"], "ALLOWED")


if __name__ == "__main__":
    unittest.main()
