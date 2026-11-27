"""Pure unit tests for the stale-base / sibling-coverage gate.

No subprocess, no git and no repository reads happen here: the gate consumes an
already-collected snapshot. Real git blob collection is exercised separately in
``test_stale_base_gate_adapter.py``.
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tools.qa import stale_base_gate as gate


def _snap(**overrides):
    snap = {
        "schema": 1,
        "integration_tip": "a" * 40,
        "head": "b" * 40,
        "merge_base": "a" * 40,
        "siblings": [
            {
                "path": "tests/test_alpha.py",
                "tip_blob": "1" * 64,
                "head_blob": "1" * 64,
            },
            {
                "path": "tests/test_beta.py",
                "tip_blob": "2" * 64,
                "head_blob": "2" * 64,
            },
        ],
    }
    snap.update(overrides)
    return snap


class StaleBaseGateTests(unittest.TestCase):
    def test_current_head_with_intact_siblings_passes(self):
        report = gate.evaluate(_snap())
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["head_current"])
        self.assertEqual(report["counts"]["SIBLING_ABSENT"], 0)

    def test_stale_base_is_flagged(self):
        report = gate.evaluate(_snap(merge_base="c" * 40))
        self.assertEqual(report["verdict"], "FAIL")
        self.assertIn({"code": "STALE_BASE", "path": None}, report["findings"])
        self.assertFalse(report["head_current"])

    def test_no_common_ancestor_is_flagged_as_stale(self):
        report = gate.evaluate(_snap(merge_base=None))
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["counts"]["STALE_BASE"], 1)

    def test_absent_sibling_is_flagged(self):
        snap = _snap(siblings=[{
            "path": "tests/test_alpha.py",
            "tip_blob": "1" * 64,
            "head_blob": None,
        }])
        report = gate.evaluate(snap)
        self.assertEqual(
            report["findings"],
            [{"code": "SIBLING_ABSENT", "path": "tests/test_alpha.py"}],
        )

    def test_changed_sibling_is_flagged(self):
        snap = _snap(siblings=[{
            "path": "tests/test_alpha.py",
            "tip_blob": "1" * 64,
            "head_blob": "3" * 64,
        }])
        report = gate.evaluate(snap)
        self.assertEqual(
            report["findings"],
            [{"code": "SIBLING_CHANGED", "path": "tests/test_alpha.py"}],
        )

    def test_mixed_findings_are_sorted_and_deterministic(self):
        snap = _snap(
            merge_base="c" * 40,
            siblings=[
                {"path": "tests/test_zeta.py", "tip_blob": "9" * 64, "head_blob": None},
                {"path": "tests/test_alpha.py", "tip_blob": "1" * 64, "head_blob": "3" * 64},
                {"path": "tests/test_beta.py", "tip_blob": "2" * 64, "head_blob": "2" * 64},
            ],
        )
        report = gate.evaluate(snap)
        self.assertEqual(
            report["findings"],
            [
                {"code": "SIBLING_ABSENT", "path": "tests/test_zeta.py"},
                {"code": "SIBLING_CHANGED", "path": "tests/test_alpha.py"},
                {"code": "STALE_BASE", "path": None},
            ],
        )
        self.assertEqual(gate.evaluate(snap), report)

    def test_unknown_top_level_key_is_rejected(self):
        snap = _snap(extra="nope")
        with self.assertRaises(gate.StaleBaseGateError):
            gate.evaluate(snap)

    def test_wrong_value_types_are_rejected(self):
        for bad in (
            _snap(head=123),
            _snap(merge_base="zzz"),
            _snap(siblings={}),
            _snap(siblings=[{"path": "tests/test_a.py", "tip_blob": "1" * 64}]),
            _snap(siblings=[{
                "path": "tests/test_a.py",
                "tip_blob": "1" * 63,
                "head_blob": "1" * 64,
            }]),
        ):
            with self.subTest(bad=bad), self.assertRaises(gate.StaleBaseGateError):
                gate.evaluate(bad)

    def test_duplicate_sibling_paths_are_rejected(self):
        snap = _snap(siblings=[
            {"path": "tests/test_alpha.py", "tip_blob": "1" * 64, "head_blob": "1" * 64},
            {"path": "tests/test_alpha.py", "tip_blob": "1" * 64, "head_blob": None},
        ])
        with self.assertRaises(gate.StaleBaseGateError):
            gate.evaluate(snap)

    def test_unsafe_sibling_paths_are_rejected(self):
        for bad_path in (
            "tests/../tests/test_alpha.py",
            "/tests/test_alpha.py",
            "tests\\test_alpha.py",
            "tools/qa/stale_base_gate.py",
            "tests/test_alpha.txt",
            "tests//test_alpha.py",
        ):
            snap = _snap(siblings=[{
                "path": bad_path,
                "tip_blob": "1" * 64,
                "head_blob": "1" * 64,
            }])
            with self.subTest(path=bad_path), self.assertRaises(gate.StaleBaseGateError):
                gate.evaluate(snap)

    def test_unbounded_sibling_list_is_rejected(self):
        siblings = [
            {
                "path": "tests/test_%04d.py" % i,
                "tip_blob": "1" * 64,
                "head_blob": "1" * 64,
            }
            for i in range(gate.MAX_SIBLINGS + 1)
        ]
        with self.assertRaises(gate.StaleBaseGateError):
            gate.evaluate(_snap(siblings=siblings))

    def test_duplicate_json_keys_are_rejected(self):
        raw = json.dumps(_snap())[:-1] + ', "head": "d" * 40}'
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dup.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(raw)
            with self.assertRaises(gate.StaleBaseGateError):
                gate.load_snapshot(path)

    def test_oversized_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "big.json")
            with open(path, "wb") as handle:
                handle.write(b" " * (gate.MAX_SNAPSHOT_BYTES + 1))
            with self.assertRaises(gate.StaleBaseGateError):
                gate.load_snapshot(path)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pass_path = os.path.join(tmp, "pass.json")
            fail_path = os.path.join(tmp, "fail.json")
            bad_path = os.path.join(tmp, "bad.json")
            with open(pass_path, "w", encoding="utf-8") as handle:
                json.dump(_snap(), handle)
            with open(fail_path, "w", encoding="utf-8") as handle:
                json.dump(_snap(merge_base="c" * 40), handle)
            with open(bad_path, "w", encoding="utf-8") as handle:
                handle.write("{")

            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = gate.main(["--snapshot", pass_path])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["verdict"], "PASS")

            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = gate.main(["--snapshot", fail_path])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.getvalue())["verdict"], "FAIL")

            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = gate.main(["--snapshot", bad_path])
            self.assertEqual(code, 2)
            self.assertIn("MALFORMED_SNAPSHOT", err.getvalue())


if __name__ == "__main__":
    unittest.main()
