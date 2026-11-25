"""Regression tests for the reversible user-level Classic session planner.

All inputs are bounded and local. No installer command, compositor, session
manager, display manager, package manager or Mint guest is contacted. The
tests prove planning, exact-byte ownership, explicit unwind, hostile-input
fail-closed behavior and the hardcoded absence of host side effects.
"""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from typing import Any

from canopy_features.installer import desktop_session_registration as dsr


def digest(data):
    return hashlib.sha256(data).hexdigest()


class DesktopSessionRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="canopy-dsr-")
        self.addCleanup(self.temp.cleanup)
        self.home = str(Path(self.temp.name) / "home")
        self.data_home = str(Path(self.home) / ".local" / "share")
        self.env = {"XDG_DATA_HOME": self.data_home}
        self.exec_path = str(Path(self.temp.name) / "canopy-classic")
        self.entry_text = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Canopy Classic\n"
            "Comment=Canopy Classic X11 session\n"
            f"Exec={self.exec_path}\n"
            "Icon=canopy-classic\n"
        )
        self.entry_sha = digest(self.entry_text.encode("utf-8"))
        self.marker_text = (
            '{"schema":1,"sha256":"' + self.entry_sha + '"}\n'
        )
        self.marker_sha = digest(self.marker_text.encode("utf-8"))

    def record(self, action="dry-run", *, observed=None, entry_text: Any = True,
               home=None, env=None, entry_name="org.canopy.Classic.desktop"):
        return {
            "schema": dsr.SCHEMA,
            "action": action,
            "home": self.home if home is None else home,
            "env": self.env if env is None else env,
            "entry_name": entry_name,
            "entry_text": (self.entry_text if entry_text is True
                           else None if entry_text is False else entry_text),
            "observed": {} if observed is None else observed,
        }

    def observations(self, *, entry=None, marker=None, recorded=None):
        return {
            "entry_sha256": self.entry_sha if entry is None else entry,
            "marker_sha256": self.marker_sha if marker is None else marker,
            "recorded_entry_sha256": (
                self.entry_sha if recorded is None else recorded),
        }

    # -- planning ---------------------------------------------------------

    def test_dry_run_is_exact_hash_bearing_and_mint_neutral(self):
        plan = dsr.build_plan(self.record())
        self.assertTrue(plan.safe)
        self.assertEqual(plan.action, "dry-run")
        self.assertEqual(plan.entry_relative,
                         "xsessions/org.canopy.Classic.desktop")
        self.assertEqual(plan.marker_relative, dsr.MARKER_RELATIVE)
        self.assertEqual(plan.entry_sha256, digest(
            self.entry_text.encode("utf-8")))
        self.assertEqual(plan.marker_sha256, digest(
            self.marker_text.encode("utf-8")))
        self.assertEqual(plan.remove_files, ())
        self.assertEqual([step.phase for step in plan.steps],
                         ["preserve-session", "validate-target", "write-entry",
                          "write-marker", "verify"])
        self.assertEqual(plan.unwind[0].trigger, "marker_write_failed")
        self.assertEqual(plan.unwind[0].remove_files,
                         (plan.entry_relative,))
        self.assertFalse(Path(self.data_home).exists())

    def test_plan_snapshot_has_negative_claims_and_is_a_copy(self):
        plan = dsr.build_plan(self.record("register"))
        data = plan.as_dict()
        self.assertEqual(data["status"], "DESKTOP_SESSION_PLAN")
        self.assertEqual(data["entry_sha256"], plan.entry_sha256)
        for claim in ("executes_host_changes", "privileged", "session_started",
                      "display_manager_changed", "cinnamon_session_replaced",
                      "compositor_replaced", "package_installed",
                      "linux_mint_acceptance_proven", "owner_visual_approval"):
            self.assertIs(data[claim], False, claim)
        data["blockers"].append("mutated")
        self.assertEqual(plan.blockers, ())

    def test_register_plans_writes_only_onto_an_empty_target(self):
        plan = dsr.build_plan(self.record("register"))
        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertEqual([step.phase for step in plan.steps][-2:],
                         ["write-marker", "verify"])
        self.assertEqual(plan.steps[3].sha256, plan.marker_sha256)

    def test_register_refuses_occupied_or_unmanaged_target(self):
        for observed in (
            {"entry_sha256": self.entry_sha},
            {"marker_sha256": self.marker_sha},
            self.observations(),
        ):
            with self.subTest(observed=sorted(observed)):
                plan = dsr.build_plan(self.record("register", observed=observed))
                self.assertFalse(plan.safe)
                self.assertEqual(plan.remove_files, ())
                self.assertTrue(any("EXISTING OR UNMANAGED" in reason
                                    for reason in plan.blockers))

    # -- exact-byte unregister --------------------------------------------

    def test_unregister_removes_only_verified_owned_paths(self):
        plan = dsr.build_plan(self.record(
            "unregister", entry_text=False, observed=self.observations()))
        self.assertTrue(plan.safe)
        self.assertEqual(plan.blockers, ())
        self.assertEqual(plan.remove_files,
                         (plan.entry_relative, plan.marker_relative))
        self.assertEqual(plan.steps[1].status, "OK")
        self.assertEqual(plan.unwind[0].restore_files,
                         ((plan.entry_relative, self.entry_sha),))
        self.assertFalse(Path(self.data_home).exists())

    def test_unregister_entry_ownership_mismatch_blocks_all_removals(self):
        plan = dsr.build_plan(self.record(
            "unregister", entry_text=False,
            observed=self.observations(entry=digest(b"user edited"))))
        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertEqual(plan.steps[1].status, "BLOCKED")
        self.assertTrue(any("OWNERSHIP MISMATCH: session entry" in reason
                            for reason in plan.blockers))

    def test_unregister_marker_mismatch_blocks_all_removals(self):
        plan = dsr.build_plan(self.record(
            "unregister", entry_text=False,
            observed=self.observations(marker=digest(b"tampered marker"))))
        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertTrue(any("OWNERSHIP MISMATCH: ownership marker" in reason
                            for reason in plan.blockers))

    def test_unregister_without_recorded_hash_fails_closed(self):
        plan = dsr.build_plan(self.record(
            "unregister", entry_text=False,
            observed={"entry_sha256": self.entry_sha,
                      "marker_sha256": self.marker_sha}))
        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertTrue(any("MISSING recorded ownership hash" in reason
                            for reason in plan.blockers))

    def test_unregister_rejects_entry_text(self):
        with self.assertRaisesRegex(dsr.DesktopSessionRegistrationError,
                                    "does not accept entry text"):
            dsr.build_plan(self.record(
                "unregister", entry_text=True, observed=self.observations()))

    # -- rollback ---------------------------------------------------------

    def test_register_unwind_removes_only_byte_identical_new_entry(self):
        plan = dsr.build_plan(self.record("register"))
        decision = dsr.rollback_decision(
            plan, {"entry_sha256": self.entry_sha})
        self.assertTrue(decision.safe)
        self.assertEqual(decision.remove_files, (plan.entry_relative,))
        self.assertEqual(decision.restore_files, ())
        self.assertEqual(plan.unwind[0].verify_sha256, self.entry_sha)

    def test_register_unwind_refuses_modified_entry(self):
        plan = dsr.build_plan(self.record("register"))
        decision = dsr.rollback_decision(
            plan, {"entry_sha256": digest(b"changed after write")})
        self.assertFalse(decision.safe)
        self.assertEqual(decision.remove_files, ())
        self.assertTrue(any("OWNERSHIP MISMATCH" in reason
                            for reason in decision.blockers))

    def test_unregister_unwind_restores_exact_entry_only_when_absent(self):
        plan = dsr.build_plan(self.record(
            "unregister", entry_text=False, observed=self.observations()))
        decision = dsr.rollback_decision(plan, {"entry_sha256": None})
        self.assertTrue(decision.safe)
        self.assertEqual(decision.restore_files,
                         ((plan.entry_relative, self.entry_sha),))
        self.assertEqual(decision.remove_files, ())
        hostile = dsr.rollback_decision(
            plan, {"entry_sha256": digest(b"another user's file")})
        self.assertFalse(hostile.safe)
        self.assertEqual(hostile.restore_files, ())

    def test_unsafe_plan_never_authorizes_unwind(self):
        plan = dsr.build_plan(self.record(
            "unregister", entry_text=False,
            observed=self.observations(entry=digest(b"edited"))))
        decision = dsr.rollback_decision(plan, {"entry_sha256": None})
        self.assertFalse(decision.safe)
        self.assertEqual(decision.restore_files, ())
        self.assertEqual(decision.remove_files, ())
        self.assertIn("UNSAFE BASE PLAN", decision.blockers)

    # -- unsafe targets and metadata --------------------------------------

    def test_xdg_target_outside_home_refused(self):
        outside = str(Path(self.temp.name) / "outside-share")
        with self.assertRaisesRegex(dsr.DesktopSessionRegistrationError,
                                    "unsafe XDG session target"):
            dsr.build_plan(self.record(env={"XDG_DATA_HOME": outside}))

    @unittest.skipIf(os.name == "nt", "POSIX system root")
    def test_system_home_refused(self):
        with self.assertRaisesRegex(dsr.DesktopSessionRegistrationError,
                                    "system directory"):
            dsr.build_plan(self.record(home="/etc"))

    @unittest.skipIf(os.name != "nt", "Windows system root")
    def test_windows_system_home_refused(self):
        with self.assertRaisesRegex(dsr.DesktopSessionRegistrationError,
                                    "system directory"):
            dsr.build_plan(self.record(home="C:\\Windows"))

    def test_hostile_entry_names_refused(self):
        for name in ("../escaped.desktop", "/etc/passwd.desktop", "a/b.desktop",
                     "name.desktop/other", "..desktop", "with space.desktop",
                     "semi;colon.desktop"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                        dsr.DesktopSessionRegistrationError,
                        "entry name|target"):
                    dsr.build_plan(self.record(entry_name=name))

    def test_unsafe_session_entry_text_refused(self):
        for text in (
            self.entry_text.replace(self.exec_path, self.exec_path + " ; rm -rf /"),
            self.entry_text + "X-GNOME-Autostart=true\n",
            self.entry_text + "Exec=/bin/sh\n",
            self.entry_text.replace("Name=Canopy Classic\n", ""),
            "[Desktop Entry]\nType=Application\nName=Canopy\nExec=relative\n",
            " " * (dsr._session.MAX_ENTRY_BYTES + 1),
        ):
            with self.subTest(text=text[:40]):
                with self.assertRaisesRegex(
                        dsr.DesktopSessionRegistrationError,
                        "session entry"):
                    dsr.build_plan(self.record(entry_text=text))

    def test_symlinked_xdg_parent_refused(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        link = Path(self.home) / "linked-share"
        Path(self.home).mkdir()
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable on this host: " + str(exc))
        with self.assertRaisesRegex(dsr.DesktopSessionRegistrationError,
                                    "unsafe XDG session target"):
            dsr.build_plan(self.record(env={"XDG_DATA_HOME": str(link)}))

    # -- hostile wrong-type inputs ----------------------------------------

    def test_wrong_type_record_shapes_use_domain_error(self):
        for value in (None, 3, 3.5, True, [], (), b"record", object(),
                      {}, {"schema": dsr.SCHEMA}):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(dsr.DesktopSessionRegistrationError):
                    dsr.build_plan(value)

    def test_wrong_type_fields_never_leak_builtin_errors(self):
        base = self.record()
        hostile = (None, 3, 3.5, True, False, [], {}, b"x", object())
        for field in ("schema", "action", "home", "env", "entry_name",
                      "entry_text", "observed"):
            for value in hostile:
                if field in ("env", "observed") and value == {}:
                    continue  # an empty mapping is the legitimate default
                with self.subTest(field=field, value=type(value).__name__):
                    candidate = dict(base)
                    candidate[field] = value
                    try:
                        dsr.build_plan(candidate)
                    except dsr.DesktopSessionRegistrationError:
                        continue
                    except Exception as exc:  # pragma: no cover - regression guard
                        self.fail("raw %s escaped for %s: %s"
                                  % (type(exc).__name__, field, exc))
                    self.fail("hostile %s was accepted" % field)

    def test_wrong_type_environment_and_observed_values_use_domain_error(self):
        for value in (3, True, [], b"env", "text"):
            with self.subTest(env=type(value).__name__):
                with self.assertRaises(dsr.DesktopSessionRegistrationError):
                    dsr.build_plan(self.record(env=value))
        for value in (3, True, [], b"hash", "abc", "A" * 64, "g" * 64):
            with self.subTest(observed=type(value).__name__):
                with self.assertRaises(dsr.DesktopSessionRegistrationError):
                    dsr.build_plan(self.record(
                        observed={"entry_sha256": value}))
        with self.assertRaises(dsr.DesktopSessionRegistrationError):
            dsr.build_plan(self.record(observed={"unknown": None}))

    def test_wrong_type_rollback_arguments_use_domain_error(self):
        plan = dsr.build_plan(self.record("register"))
        for value in (None, 3, [], {}, "plan"):
            with self.subTest(plan=type(value).__name__):
                with self.assertRaises(dsr.DesktopSessionRegistrationError):
                    dsr.rollback_decision(value, {})
        for value in (None, 3, [], b"observed", {"extra": None}):
            with self.subTest(observed=type(value).__name__):
                with self.assertRaises(dsr.DesktopSessionRegistrationError):
                    dsr.rollback_decision(plan, value)

    def test_broken_plan_snapshot_is_refused(self):
        plan = dsr.build_plan(self.record("register"))
        hostile = dsr.SessionRegistrationPlan(
            action="register", safe=True, entry_relative=plan.entry_relative,
            marker_relative=plan.marker_relative, entry_sha256=[],  # type: ignore[arg-type]
            marker_sha256=plan.marker_sha256, steps=plan.steps,
            unwind=plan.unwind, remove_files=(), blockers=())
        with self.assertRaises(dsr.DesktopSessionRegistrationError):
            hostile.as_dict()

    def test_hostile_plan_relative_path_is_refused_on_snapshot(self):
        plan = dsr.build_plan(self.record("register"))
        hostile = dsr.SessionRegistrationPlan(
            action="register", safe=True, entry_relative=[],  # type: ignore[arg-type]
            marker_relative=plan.marker_relative,
            entry_sha256=plan.entry_sha256,
            marker_sha256=plan.marker_sha256, steps=plan.steps,
            unwind=plan.unwind, remove_files=(), blockers=())
        with self.assertRaises(dsr.DesktopSessionRegistrationError):
            hostile.as_dict()


if __name__ == "__main__":
    unittest.main()
