"""Contract tests for the bounded offline release-readiness gate.

Run: python -m unittest tests.test_c100_canopy_release_gate -v
"""
import ast
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tools.qa import canopy_release_gate as gate

SHA_A = "a" * 40


def dependency(held=0, reasons=()):
    return {
        "status": "MERGE_ORDER_COMPUTED", "schema": 1,
        "pr_count": 2, "held_count": held, "ready_count": 2 - held,
        "held_pr_numbers": (377,) if held else (),
        "merge_order": (375, 377) if not held else (375,),
        "hold_reasons": tuple(reasons),
        "release_approved": False, "linux_mint_acceptance_proven": False,
        "owner_visual_approval": False, "merge_performed": False,
        "network_accessed": False, "process_launched": False,
    }


def gates(**overrides):
    values = {
        "R047": "BLOCKED", "R050": "BLOCKED", "R066": "PASS_NUMERIC_SCOPED",
        "R073": "PASS", "R074": "PASS_SCOPED", "R078": "PARTIAL_SCOPED",
        "R086": "NOT_RUN",
    }
    values.update(overrides)
    return values


def verdict(gates_map=None, integrity="PASS", release_ready=False,
            label="SECRET_VERDICT_MARKER"):
    return {
        "schema": 1, "verdict": "PARTIAL_SCOPED", "integrity": integrity,
        "release_ready": release_ready,
        "gates": gates() if gates_map is None else gates_map,
        "label": label,
    }


def verdict_record(gates_map=None, integrity="PASS", release_ready=False):
    """Exactly the pinned verdict keys (no extra label field)."""
    out = verdict(gates_map, integrity, release_ready)
    out.pop("label")
    return out


def snapshot(dep=None, verd=None):
    return {
        "schema": 1,
        "dependency_report": dependency() if dep is None else dep,
        "acceptance_verdict": verdict_record() if verd is None else verd,
    }


NEGATIVE_CLAIMS = (
    "release_approved", "linux_mint_acceptance_proven", "owner_visual_approval",
    "real_mint_run_proven", "runner_proven", "merge_performed",
    "network_accessed", "process_launched",
)


class RealVerdictTests(unittest.TestCase):
    def test_agent_c_verdict_shape_reports_blockers(self):
        out = gate.evaluate(snapshot())
        self.assertEqual(out["status"], "RELEASE_READINESS_REPORTED")
        self.assertEqual(out["schema"], 1)
        self.assertIs(out["release_ready"], False)
        self.assertEqual(out["gates_checked"], 7)
        tokens = set(out["blocker_tokens"])
        self.assertTrue({"VISUAL_HOLD", "MINT_HOLD", "RUNNER_HOLD",
                         "R086_HOLD", "P0_HOLD"} <= tokens)

    def test_stacked_pr_is_a_blocker(self):
        dep = dependency(held=1, reasons=("DEPENDENCY_HOLD",))
        out = gate.evaluate(snapshot(dep=dep))
        self.assertIn("STACKED_PR_HOLD", out["blocker_tokens"])
        self.assertEqual(out["held_pr_count"], 1)
        self.assertEqual(out["dependency_hold_reasons"], ("DEPENDENCY_HOLD",))

    def test_all_gates_pass_and_no_held_prs_reports_no_blockers(self):
        all_pass = gates(**{name: "PASS" for name in gate.GATE_IDS})
        out = gate.evaluate(snapshot(verd=verdict_record(all_pass)))
        self.assertEqual(out["blocker_count"], 0)
        self.assertEqual(out["blocker_tokens"], ())
        # Even with zero blockers this gate never claims release approval.
        self.assertIs(out["release_ready"], False)

    def test_self_reported_release_true_is_never_trusted(self):
        all_pass = gates(**{name: "PASS" for name in gate.GATE_IDS})
        out = gate.evaluate(snapshot(
            verd=verdict_record(all_pass, release_ready=True)))
        self.assertIn("UNTRUSTED_RELEASE_CLAIM", out["blocker_tokens"])
        self.assertIs(out["release_ready"], False)

    def test_integrity_failure_is_a_blocker(self):
        out = gate.evaluate(snapshot(
            verd=verdict_record(integrity="FAIL")))
        self.assertIn("INTEGRITY_HOLD", out["blocker_tokens"])

    def test_unverified_visual_is_a_blocker(self):
        out = gate.evaluate(snapshot(verd=verdict_record(
            gates(R078="UNVERIFIED"))))
        self.assertIn("VISUAL_HOLD", out["blocker_tokens"])

    def test_mint_scoped_is_not_full_pass(self):
        out = gate.evaluate(snapshot(
            verd=verdict_record(gates(R073="PASS", R074="PASS_SCOPED"))))
        self.assertIn("MINT_HOLD", out["blocker_tokens"])

    def test_all_negative_claims_hardcoded(self):
        out = gate.evaluate(snapshot())
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_no_raw_value_echo(self):
        out = gate.evaluate(snapshot())
        rendered = json.dumps(out, sort_keys=True)
        for marker in ("R047", "R078", "MERGE_ORDER_COMPUTED",
                       "PARTIAL_SCOPED", SHA_A):
            self.assertNotIn(marker, rendered)

    def test_deterministic_bytes(self):
        snap = snapshot()
        self.assertEqual(json.dumps(gate.evaluate(snap), sort_keys=True),
                         json.dumps(gate.evaluate(snap), sort_keys=True))

    def test_blocker_tokens_sorted_and_unique(self):
        out = gate.evaluate(snapshot())
        self.assertEqual(out["blocker_tokens"],
                         tuple(sorted(set(out["blocker_tokens"]))))


class IntegrityTests(unittest.TestCase):
    def test_bad_wrapper(self):
        for bad in (None, 7, [], "x", {}, dict(snapshot(), extra=1)):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(gate.ReleaseGateError):
                gate.evaluate(bad)

    def test_wrong_schema(self):
        for bad in (0, 2, "1", True, None, []):
            snap = snapshot()
            snap["schema"] = bad
            with self.subTest(bad=bad), self.assertRaises(gate.ReleaseGateError):
                gate.evaluate(snap)

    def test_dependency_negative_claim_flip_rejected(self):
        dep = dependency()
        dep["merge_performed"] = True
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(dep=dep))

    def test_wrong_dependency_status(self):
        dep = dependency()
        dep["status"] = "APPROVED"
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(dep=dep))

    def test_unhashable_dependency_hold_token_fails_closed(self):
        dep = dependency(reasons=([],))
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(dep=dep))

    def test_bad_dependency_counts(self):
        for value in (-1, True, "1", None):
            dep = dependency()
            dep["held_count"] = value
            with self.subTest(value=value), self.assertRaises(gate.ReleaseGateError):
                gate.evaluate(snapshot(dep=dep))

    def test_wrong_gate_id_rejected(self):
        verd = verdict_record()
        del verd["gates"]["R078"]
        verd["gates"]["R999"] = "PASS"
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(verd=verd))

    def test_wrong_gate_status_rejected(self):
        verd = verdict_record()
        verd["gates"]["R078"] = "APPROVED"
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(verd=verd))

    def test_unhashable_gate_status_fails_closed(self):
        verd = verdict_record()
        verd["gates"]["R078"] = []
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(verd=verd))

    def test_wrong_integrity_token_rejected(self):
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(verd=verdict_record(integrity="APPROVED")))

    def test_wrong_verdict_token_rejected(self):
        verd = verdict_record()
        verd["verdict"] = "RELEASE_APPROVED"
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate(snapshot(verd=verd))

    def test_no_echo_in_errors(self):
        dep = dependency()
        dep["hold_reasons"] = ("SECRET_HOLD_MARKER",)
        with self.assertRaises(gate.ReleaseGateError) as ctx:
            gate.evaluate(snapshot(dep=dep))
        self.assertNotIn("SECRET_HOLD_MARKER", str(ctx.exception))


class JsonFileTests(unittest.TestCase):
    def test_json_text_and_bytes(self):
        text = json.dumps(snapshot())
        self.assertEqual(gate.evaluate_json(text)["status"],
                         "RELEASE_READINESS_REPORTED")
        self.assertEqual(gate.evaluate_json(text.encode("utf-8"))["schema"], 1)

    def test_json_wrong_types(self):
        for bad in (None, 7, [], {}):
            with self.subTest(bad=bad), self.assertRaises(gate.ReleaseGateError):
                gate.evaluate_json(bad)

    def test_json_empty_oversized_deep_nonfinite(self):
        cases = ["", "x" * (gate.MAX_SNAPSHOT_BYTES + 1),
                 "[" * 4000 + "]" * 4000,
                 json.dumps(snapshot()).replace('"schema": 1', '"schema": NaN', 1)]
        for text in cases:
            with self.subTest(size=len(text)), \
                    self.assertRaises(gate.ReleaseGateError):
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
        self.assertEqual(gate.evaluate_file(self._write(snapshot()))["schema"], 1)

    def test_relative_path_rejected(self):
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate_file(Path("relative.json"))

    def test_missing_file_rejected(self):
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate_file(self.root / "nope.json")

    def test_directory_rejected(self):
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate_file(self.root)

    def test_symlink_final_rejected(self):
        target = self._write(snapshot(), "target.json")
        link = self.root / "link.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(gate.ReleaseGateError):
            gate.evaluate_file(link)

    def test_posix_fdopen_failure_translated(self):
        with mock.patch.object(gate.os, "open", return_value=999), \
                mock.patch.object(gate.os, "fdopen",
                                  side_effect=IsADirectoryError("is a dir")):
            with self.assertRaises(gate.ReleaseGateError) as ctx:
                gate.evaluate_file(self.root / "anything.json")
        self.assertIsInstance(ctx.exception.__cause__, IsADirectoryError)

    def test_main_success(self):
        path = self._write(snapshot())
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "RELEASE_READINESS_REPORTED")

    def test_main_failure_marker(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = gate.main([str(self.root / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("CANOPY_RELEASE_GATE_FAIL:", err.getvalue())


class PurityTests(unittest.TestCase):
    def test_no_network_process_or_repo_io(self):
        source = Path(gate.__file__).resolve().read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = {"argparse", "json", "os", "pathlib", "stat", "sys"}
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

    def test_never_emits_approval(self):
        source = Path(gate.__file__).resolve().read_text(encoding="utf-8")
        self.assertIn('"release_ready": False', source)


if __name__ == "__main__":
    unittest.main()
