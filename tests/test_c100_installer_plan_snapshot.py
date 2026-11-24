"""Contract tests for the pure installer plan snapshot composition.

Run: python -m unittest tests.test_c100_installer_plan_snapshot -v
"""
import ast
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path, PurePosixPath
import unittest

from canopy_features.installer import icon_cache_optin as icon_mod
from canopy_features.installer import session_entry_validation as session_mod
from canopy_features.installer.installer_plan_snapshot import (
    MAX_OWNED_FILES, SCHEMA, InstallerPlanSnapshot, SnapshotError, snapshot,
)

NEGATIVE_CLAIMS = (
    "filesystem_verified", "binary_verified", "uninstall_executed",
    "session_registered", "package_installed", "release_approved",
    "linux_mint_acceptance_proven", "owner_visual_approval",
)


def entry_text(name="Canopy Classic", exec_path=None):
    if exec_path is None:
        exec_path = ("C:/Canopy/canopy.exe" if os.name == "nt"
                     else "/usr/bin/canopy-classic")
    return "[Desktop Entry]\nType=Session\nName=" + name + "\nExec=" + exec_path + "\n"


_UNSET = object()


def _native_home():
    return "C:/Users/alice" if os.name == "nt" else "/home/alice"


def record(home="/home/alice", xdg_home=_UNSET, dirs=_UNSET, available=_UNSET,
           kind="cache", relative="canopy", env=_UNSET, ownership=_UNSET,
           entry=_UNSET):
    return {
        "schema": SCHEMA,
        "home": home,
        "xdg_home": _native_home() if xdg_home is _UNSET else xdg_home,
        "icon_dirs": (["/home/alice/.local/share/icons"] if dirs is _UNSET else dirs),
        "tool_available": True if available is _UNSET else available,
        "xdg_kind": kind,
        "xdg_relative": relative,
        "env": ({} if env is _UNSET else env),
        "ownership_manifest": (
            {"schema": 1, "files": {"share/canopy/app.desktop": "a" * 64}}
            if ownership is _UNSET else ownership),
        "session_entry_text": (entry_text() if entry is _UNSET else entry),
    }


def compose(rec):
    return snapshot(rec).as_dict()


class RealCompositionTests(unittest.TestCase):
    def test_all_boundaries_decide(self):
        out = compose(record())
        self.assertEqual(out["status"], "PLAN_SNAPSHOT")
        self.assertEqual(out["schema"], SCHEMA)
        self.assertEqual(out["icon_status"], "AVAILABLE")
        self.assertEqual(out["xdg_status"], "WITHIN_HOME")
        self.assertEqual(out["ownership_status"], "VALID")
        self.assertEqual(out["ownership_file_count"], 1)
        self.assertEqual(out["session_status"], "VALID")

    def test_all_negative_claims_hardcoded(self):
        for key in NEGATIVE_CLAIMS:
            self.assertIs(compose(record())[key], False)

    def test_missing_tool_is_fixed_token(self):
        out = compose(record(available=False))
        self.assertEqual(out["icon_status"], "UNAVAILABLE")
        self.assertEqual(out["ownership_status"], "VALID")

    def test_icon_dir_outside_home_is_invalid_token(self):
        self.assertEqual(
            compose(record(dirs=["/usr/share/icons"]))["icon_status"], "INVALID")

    def test_empty_icon_dirs_is_invalid_token(self):
        self.assertEqual(compose(record(dirs=[]))["icon_status"], "INVALID")

    def test_xdg_global_env_is_outside_home(self):
        outside = "C:/Windows/Temp" if os.name == "nt" else "/var/cache"
        out = compose(record(env={"XDG_CACHE_HOME": outside}))
        self.assertEqual(out["xdg_status"], "OUTSIDE_HOME")

    def test_unknown_xdg_kind_is_invalid_token(self):
        self.assertEqual(compose(record(kind="bogus"))["xdg_status"], "INVALID")

    def test_traversal_relative_is_invalid_token(self):
        self.assertEqual(
            compose(record(relative="../etc"))["xdg_status"], "INVALID")

    def test_bad_ownership_manifest_is_isolated(self):
        out = compose(record(ownership={"schema": 2, "files": {}}))
        self.assertEqual(out["ownership_status"], "INVALID")
        self.assertEqual(out["ownership_file_count"], 0)
        self.assertEqual(out["session_status"], "VALID")

    def test_oversized_ownership_prebounded(self):
        files = {"f" + str(i): "a" * 64 for i in range(MAX_OWNED_FILES + 1)}
        out = compose(record(ownership={"schema": 1, "files": files}))
        self.assertEqual(out["ownership_status"], "INVALID")
        self.assertEqual(out["ownership_file_count"], 0)

    def test_bad_session_text_is_isolated(self):
        out = compose(record(entry="[Desktop Entry]\nType=Session\n"))
        self.assertEqual(out["session_status"], "INVALID")
        self.assertEqual(out["icon_status"], "AVAILABLE")

    def test_exec_shell_syntax_is_invalid(self):
        text = entry_text(exec_path="/usr/bin/sh -c sudo")
        self.assertEqual(compose(record(entry=text))["session_status"], "INVALID")

    def test_mutually_hostile_inputs(self):
        rec = record(dirs=["/usr/share/icons"], kind="bogus",
                     ownership={"schema": 99}, entry="garbage")
        out = compose(rec)
        self.assertEqual(out["icon_status"], "INVALID")
        self.assertEqual(out["xdg_status"], "INVALID")
        self.assertEqual(out["ownership_status"], "INVALID")
        self.assertEqual(out["session_status"], "INVALID")
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_no_raw_value_echo(self):
        out = compose(record(
            home="/home/SECRET_HOME_MARKER", relative="SECRET_REL_MARKER",
            env={"XDG_CACHE_HOME": "/home/alice/SECRET_ENV_MARKER"},
            entry=entry_text(name="SECRET_NAME_MARKER"),
        ))
        rendered = json.dumps(out, sort_keys=True)
        for marker in ("SECRET_HOME_MARKER", "SECRET_REL_MARKER",
                       "SECRET_ENV_MARKER", "SECRET_NAME_MARKER"):
            self.assertNotIn(marker, rendered)

    def test_deterministic_bytes(self):
        rec = record()
        self.assertEqual(json.dumps(compose(rec), sort_keys=True),
                         json.dumps(compose(rec), sort_keys=True))

    def test_no_live_alias_to_caller_containers(self):
        rec = record()
        made = snapshot(rec)
        rec["icon_dirs"].append("/usr/share/icons")
        rec["env"]["XDG_CACHE_HOME"] = "/var/cache"
        rec["ownership_manifest"]["files"]["extra"] = "b" * 64
        out = made.as_dict()
        self.assertEqual(out["icon_status"], "AVAILABLE")
        self.assertEqual(out["xdg_status"], "WITHIN_HOME")
        self.assertEqual(out["ownership_file_count"], 1)


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

    def test_bad_home(self):
        for bad in ("", 7, None, "x" * 600):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(SnapshotError):
                snapshot(record(home=bad))
        # A non-absolute POSIX home is a component rejection, not a wrapper
        # shape error: it must still fail closed as a fixed token.
        out = compose(record(home="relative/path"))
        self.assertEqual(out["icon_status"], "INVALID")

    def test_bad_icon_dirs_container(self):
        for bad in ("path", 7, None, {1, 2},
                    ["/home/alice/.icons"] * (icon_mod.MAX_THEME_DIRS + 1)):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(SnapshotError):
                snapshot(record(dirs=bad))

    def test_bad_tool_available(self):
        for bad in (0, 1, "yes", None, []):
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                snapshot(record(available=bad))

    def test_bad_env(self):
        for bad in (None, [], "x", {1: "v"}, {"K": 7},
                    {"K": "v" * 600}, {"k" + str(i): "v" for i in range(65)}):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(SnapshotError):
                snapshot(record(env=bad))

    def test_bad_session_text_container(self):
        for bad in (None, 7, [], "x" * (session_mod.MAX_ENTRY_BYTES + 1)):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(SnapshotError):
                snapshot(record(entry=bad))


class ForgedRecordTests(unittest.TestCase):
    def make(self, **overrides):
        values = dict(
            schema=SCHEMA, icon_status="AVAILABLE", xdg_status="WITHIN_HOME",
            ownership_status="VALID", ownership_file_count=1,
            session_status="VALID",
        )
        values.update(overrides)
        return InstallerPlanSnapshot(**values)

    def test_forged_record_cannot_emit_execution_claim(self):
        out = self.make().as_dict()
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_bad_tokens_fail_closed(self):
        for field, token in (
            ("icon_status", "EXECUTED"), ("xdg_status", "WRITTEN"),
            ("ownership_status", "DELETED"), ("session_status", "REGISTERED"),
        ):
            with self.subTest(field=field), self.assertRaises(SnapshotError):
                self.make(**{field: token}).as_dict()

    def test_unhashable_token_fails_closed(self):
        for bad in ([], {}, bytearray(), 7, None):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(SnapshotError):
                self.make(icon_status=bad).as_dict()

    def test_bad_count_and_schema_fail_closed(self):
        for bad in (-1, MAX_OWNED_FILES + 1, True, "1", None):
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                self.make(ownership_file_count=bad).as_dict()
            with self.subTest(schema=bad), self.assertRaises(SnapshotError):
                self.make(schema=bad).as_dict()

    def test_report_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.make().icon_status = "INVALID"

    def test_as_dict_returns_fresh_container(self):
        rec = self.make()
        first = rec.as_dict()
        first["icon_status"] = "INVALID"
        self.assertEqual(rec.as_dict()["icon_status"], "AVAILABLE")


class PurityTests(unittest.TestCase):
    def test_no_io_exec_or_visual_imports(self):
        module_file = Path(__file__).resolve().parents[1] / (
            "canopy_features/installer/installer_plan_snapshot.py")
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
        allowed = {"dataclasses", "pathlib", "canopy_features"}
        forbidden = {
            "os", "time", "random", "subprocess", "socket", "threading",
            "datetime", "multiprocessing", "ctypes", "shutil", "importlib",
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
                                                  "open", "write", "unlink"})

    def test_no_filesystem_call_from_own_module(self):
        module_file = Path(__file__).resolve().parents[1] / (
            "canopy_features/installer/installer_plan_snapshot.py")
        source = module_file.read_text(encoding="utf-8")
        for name in ("validate_session_entry",
                     "scan_session_entries", "plan_uninstall", "read_manifest"):
            self.assertNotIn(name, source)


class HostileWrongTypeLabelTests(unittest.TestCase):
    """Bounded wrong-type labels must fail closed, not leak a built-in error."""

    def test_broken_pathlike_icon_label_fails_closed(self):
        class BrokenPath(PurePosixPath):
            def __str__(self):
                raise TypeError("hostile icon label")

        with self.assertRaises(SnapshotError):
            snapshot(record(dirs=[BrokenPath("/home/alice/.icons")]))

    def test_broken_ownership_key_label_fails_closed(self):
        class BrokenKey:
            def __repr__(self):
                raise TypeError("hostile ownership label")

        manifest = {"schema": 1, "files": {BrokenKey(): "a" * 64}}
        with self.assertRaises(SnapshotError):
            snapshot(record(ownership=manifest))


if __name__ == "__main__":
    unittest.main()
