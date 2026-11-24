"""Contract tests for the offline PR dependency-order gate.

Run: python -m unittest tests.test_c100_pr_dependency_gate -v
"""
import ast
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tools.qa import pr_dependency_gate as gate

BASE = "integration/canopy-classic-20261123"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def check(name="foundation", state="COMPLETED", conclusion="SUCCESS", sha=SHA_A):
    return {"name": name, "state": state, "conclusion": conclusion, "headSha": sha}


def pull(number=375, state="OPEN", base=BASE, head=SHA_A, checks=None):
    return {
        "number": number, "state": state, "baseRefName": base,
        "headRefOid": head,
        "statusCheckRollup": ([check(sha=head), check("qt-evidence", sha=head)]
                              if checks is None else checks),
    }


def snapshot(pulls=None, dependencies=None, release=False, visual=False):
    return {
        "schema": 1,
        "integration_branch": BASE,
        "pulls": ([pull(375), pull(377, head=SHA_B)] if pulls is None else pulls),
        "dependencies": ({"377": 375} if dependencies is None else dependencies),
        "release_hold": release,
        "visual_hold": visual,
    }


NEGATIVE_CLAIMS = (
    "release_approved", "linux_mint_acceptance_proven", "owner_visual_approval",
    "merge_performed", "network_accessed", "process_launched",
)


class RealStackedPrTests(unittest.TestCase):
    def test_377_held_while_375_open(self):
        out = gate.evaluate(snapshot())
        self.assertEqual(out["status"], "MERGE_ORDER_COMPUTED")
        self.assertEqual(out["pr_count"], 2)
        self.assertEqual(out["held_pr_numbers"], (377,))
        self.assertEqual(out["merge_order"], (375,))
        self.assertEqual(out["hold_reasons"], ("DEPENDENCY_HOLD",))

    def test_377_ready_once_375_merged(self):
        pulls = [pull(375, state="MERGED"), pull(377, head=SHA_B)]
        out = gate.evaluate(snapshot(pulls=pulls))
        self.assertEqual(out["held_count"], 0)
        self.assertEqual(out["merge_order"], (377,))
        self.assertEqual(out["hold_reasons"], ())

    def test_missing_prerequisite(self):
        out = gate.evaluate(snapshot(dependencies={"377": 999}))
        self.assertEqual(out["hold_reasons"], ("MISSING_PREREQUISITE",))
        self.assertEqual(out["held_pr_numbers"], (377,))

    def test_unmet_exact_sha_check(self):
        stale = [check(sha=SHA_C), check("qt-evidence", sha=SHA_C)]
        pulls = [pull(375), pull(377, head=SHA_B, checks=stale)]
        out = gate.evaluate(snapshot(pulls=pulls))
        self.assertIn("UNMET_SHA_CHECKS", out["hold_reasons"])
        self.assertEqual(out["held_pr_numbers"], (377,))

    def test_pending_check_held(self):
        checks = [check(state="PENDING", conclusion=None), check("qt-evidence")]
        out = gate.evaluate(snapshot(pulls=[pull(375, checks=checks),
                                            pull(377, head=SHA_B)]))
        self.assertIn("UNMET_SHA_CHECKS", out["hold_reasons"])

    def test_failed_check_held(self):
        checks = [check(conclusion="FAILURE"), check("qt-evidence")]
        out = gate.evaluate(snapshot(pulls=[pull(375, checks=checks)],
                                      dependencies={}))
        self.assertIn("UNMET_SHA_CHECKS", out["hold_reasons"])

    def test_forbidden_base(self):
        pulls = [pull(375, base="feat/side-branch"), pull(377, head=SHA_B)]
        out = gate.evaluate(snapshot(pulls=pulls))
        self.assertIn("FORBIDDEN_BASE", out["hold_reasons"])
        self.assertIn(375, out["held_pr_numbers"])

    def test_not_open_state(self):
        pulls = [pull(375, state="CLOSED"), pull(377, head=SHA_B)]
        out = gate.evaluate(snapshot(pulls=pulls))
        self.assertIn("NOT_OPEN", out["hold_reasons"])

    def test_release_and_visual_holds(self):
        out = gate.evaluate(snapshot(release=True, visual=True))
        self.assertEqual(set(out["hold_reasons"]),
                         {"DEPENDENCY_HOLD", "RELEASE_HOLD", "VISUAL_HOLD"})
        self.assertEqual(out["held_count"], 2)

    def test_all_negative_claims_hardcoded(self):
        out = gate.evaluate(snapshot())
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_deterministic_bytes(self):
        snap = snapshot()
        self.assertEqual(json.dumps(gate.evaluate(snap), sort_keys=True),
                         json.dumps(gate.evaluate(snap), sort_keys=True))

    def test_no_raw_value_echo(self):
        snap = snapshot(dependencies={},
                        pulls=[pull(375, base="SECRET_BASE_MARKER",
                                    head="d" * 40,
                                    checks=[check(name="SECRET_CHECK_MARKER")])])
        out = gate.evaluate(snap)
        rendered = json.dumps(out, sort_keys=True)
        for marker in ("SECRET_BASE_MARKER", "SECRET_CHECK_MARKER", "d" * 40):
            self.assertNotIn(marker, rendered)

    def test_empty_snapshot(self):
        out = gate.evaluate(snapshot(pulls=[], dependencies={}))
        self.assertEqual(out["pr_count"], 0)
        self.assertEqual(out["held_count"], 0)
        self.assertEqual(out["merge_order"], ())


class BoundaryTests(unittest.TestCase):
    def test_bad_wrapper(self):
        for bad in (None, 7, [], "x", {}, dict(snapshot(), extra=1)):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(gate.DependencyGateError):
                gate.evaluate(bad)

    def test_wrong_schema(self):
        for bad in (0, 2, "1", True, None, []):
            snap = snapshot()
            snap["schema"] = bad
            with self.subTest(bad=bad), self.assertRaises(gate.DependencyGateError):
                gate.evaluate(snap)

    def test_wrong_integration_branch(self):
        for bad in ("main", "SECRET_BRANCH", 7, None, []):
            snap = snapshot()
            snap["integration_branch"] = bad
            with self.subTest(bad=str(bad)[:20]), \
                    self.assertRaises(gate.DependencyGateError):
                gate.evaluate(snap)

    def test_wrong_hold_flags(self):
        for field in ("release_hold", "visual_hold"):
            for bad in (0, 1, "yes", None, []):
                snap = snapshot()
                snap[field] = bad
                with self.subTest(field=field, bad=bad), \
                        self.assertRaises(gate.DependencyGateError):
                    gate.evaluate(snap)

    def test_bad_pull_container(self):
        for bad in (None, 7, "x", {}, [pull()] * 65):
            snap = snapshot()
            snap["pulls"] = bad
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(gate.DependencyGateError):
                gate.evaluate(snap)

    def test_duplicate_pull_number(self):
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate(snapshot(pulls=[pull(375), pull(375)]))

    def test_bad_pull_fields(self):
        for field, bad in (
            ("number", 0), ("number", True), ("state", "MERGED "),
            ("baseRefName", 7), ("headRefOid", "A" * 40),
            ("headRefOid", "abc"), ("statusCheckRollup", {}),
        ):
            p = pull()
            p[field] = bad
            with self.subTest(field=field), self.assertRaises(gate.DependencyGateError):
                gate.evaluate(snapshot(pulls=[p]))

    def test_bad_check_fields(self):
        for field, bad in (
            ("name", 7), ("state", "DONE"), ("conclusion", "GREEN"),
            ("headSha", "z" * 40),
        ):
            c = check()
            c[field] = bad
            with self.subTest(field=field), \
                    self.assertRaises(gate.DependencyGateError):
                gate.evaluate(snapshot(pulls=[pull(375, checks=[c])]))

    def test_check_key_set(self):
        c = check()
        c["extra"] = 1
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate(snapshot(pulls=[pull(375, checks=[c])]))

    def test_unhashable_check_state_fails_closed(self):
        c = check()
        c["state"] = []
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate(snapshot(pulls=[pull(375, checks=[c])]))

    def test_bad_dependency_map(self):
        for bad in ({375: 377}, {"abc": 375}, {"377": "375"},
                    {"377": 0}, {"377": 377}, {"999": 375}, None, []):
            snap = snapshot()
            snap["dependencies"] = bad
            with self.subTest(bad=str(bad)[:30]), \
                    self.assertRaises(gate.DependencyGateError):
                gate.evaluate(snap)

    def test_dependency_on_unmerged_pr_is_held(self):
        pulls = [pull(375, state="OPEN"), pull(377, head=SHA_B),
                 pull(378, head=SHA_C)]
        deps = {"377": 375, "378": 377}
        out = gate.evaluate(snapshot(pulls=pulls, dependencies=deps))
        self.assertEqual(out["held_count"], 2)
        self.assertEqual(out["hold_reasons"], ("DEPENDENCY_HOLD",))

    def test_dependency_cycle_never_yields_false_pass(self):
        # A two-member cycle where one member is already MERGED used to emit
        # merge_order=(377,) with zero holds: a clean PASS for a graph that
        # could never have been built in dependency order.
        pulls = [pull(375, state="MERGED"), pull(377, head=SHA_B)]
        cyclic = snapshot(pulls=pulls, dependencies={"375": 377, "377": 375})
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate(cyclic)

    def test_dependency_cycle_all_open_is_refused(self):
        pulls = [pull(375), pull(377, head=SHA_B), pull(378, head=SHA_C)]
        cyclic = snapshot(pulls=pulls,
                          dependencies={"375": 377, "377": 378, "378": 375})
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate(cyclic)


class JsonFileTests(unittest.TestCase):
    def test_json_bytes_and_text(self):
        text = json.dumps(snapshot())
        self.assertEqual(gate.evaluate_json(text)["pr_count"], 2)
        self.assertEqual(gate.evaluate_json(text.encode("utf-8"))["pr_count"], 2)

    def test_json_wrong_types(self):
        for bad in (None, 7, [], {}):
            with self.subTest(bad=bad), self.assertRaises(gate.DependencyGateError):
                gate.evaluate_json(bad)

    def test_json_empty_oversized_deep_nonfinite(self):
        cases = ["", "x" * (gate.MAX_SNAPSHOT_BYTES + 1),
                 "[" * 4000 + "]" * 4000,
                 json.dumps(snapshot()).replace('"schema": 1', '"schema": NaN', 1)]
        for text in cases:
            with self.subTest(size=len(text)), \
                    self.assertRaises(gate.DependencyGateError):
                gate.evaluate_json(text)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, payload, name="snapshot.json"):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_file(self):
        path = self._write(snapshot())
        self.assertEqual(gate.evaluate_file(path)["pr_count"], 2)

    def test_relative_path_rejected(self):
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate_file(Path("relative.json"))

    def test_missing_file_rejected(self):
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate_file(self.root / "nope.json")

    def test_directory_rejected(self):
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate_file(self.root)

    def test_symlink_final_rejected(self):
        target = self._write(snapshot(), "target.json")
        link = self.root / "link.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(gate.DependencyGateError):
            gate.evaluate_file(link)

    def test_posix_fdopen_failure_translated(self):
        with mock.patch.object(gate.os, "open", return_value=999), \
                mock.patch.object(gate.os, "fdopen",
                                  side_effect=IsADirectoryError("is a dir")):
            with self.assertRaises(gate.DependencyGateError) as ctx:
                gate.evaluate_file(self.root / "anything.json")
        self.assertIsInstance(ctx.exception.__cause__, IsADirectoryError)

    def test_main_success(self):
        path = self._write(snapshot())
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "MERGE_ORDER_COMPUTED")

    def test_main_failure_marker(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = gate.main([str(self.root / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("QT_PR_DEPENDENCY_FAIL:", err.getvalue())


class PurityTests(unittest.TestCase):
    def test_no_network_process_or_repo_io(self):
        source = Path(gate.__file__).resolve().read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = {"argparse", "json", "os", "pathlib", "re", "stat", "sys"}
        forbidden = {
            "time", "random", "subprocess", "socket", "threading", "datetime",
            "multiprocessing", "ctypes", "importlib", "urllib", "requests",
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
                                                  "urlopen", "geteuid"})


if __name__ == "__main__":
    unittest.main()
