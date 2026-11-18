"""Ensure the release acceptance contract can't silently lose core scenarios."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "MINT-BOOT", "MINT-CLASSIC-START", "MINT-LAUNCHER",
    "MINT-DOCK-SIZE", "MINT-SETTINGS", "MINT-INSTALL-ROLLBACK",
    "MINT-VM-RESET", "MINT-PERF-IDLE", "MINT-ACCESSIBILITY",
    "MINT-MULTIMONITOR", "MINT-SECURITY", "MINT-STABILITY",
}


def validate_policy(contract):
    if type(contract.get("schema_version")) is not int or contract["schema_version"] != 1:
        raise ValueError("Unsupported acceptance policy")
    if contract.get("release_gate") != "ALL_MANDATORY_WITH_INDEPENDENT_EVIDENCE":
        raise ValueError("Release gate must remain strict")
    cases = contract.get("requirements")
    if not isinstance(cases, list):
        raise ValueError("Missing acceptance requirements")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or len(ids) != len(set(ids)) or not REQUIRED <= set(ids):
        raise ValueError("Duplicate or missing acceptance requirements")
    for case in cases:
        if not isinstance(case.get("id"), str):
            raise ValueError("Invalid case ID")
        if case["id"] in REQUIRED and case.get("mandatory") is not True:
            raise ValueError("Mandatory acceptance gate was relaxed")
        methods = case.get("methods")
        if not isinstance(methods, list) or len(methods) < 2 or len(set(methods)) < 2:
            raise ValueError("Independent observations required")
        if not case.get("negative_control") or not case.get("evidence"):
            raise ValueError("Failure injection and evidence required")
    return len(cases)


class AcceptancePolicyTests(unittest.TestCase):
    def test_release_contract_is_complete(self):
        contract = json.loads((ROOT / "qa/mint-acceptance-v1.json").read_text())
        self.assertGreaterEqual(validate_policy(contract), 14)
        self.assertEqual(contract["mint_vm_status"], "NOT_RUN")

    def test_false_green_contract_changes_are_rejected(self):
        contract = json.loads((ROOT / "qa/mint-acceptance-v1.json").read_text())
        contract["release_gate"] = "ONE_PASS_IS_ENOUGH"
        with self.assertRaises(ValueError):
            validate_policy(contract)

    def test_missing_critical_requirement_fails(self):
        contract = json.loads((ROOT / "qa/mint-acceptance-v1.json").read_text())
        contract["requirements"] = [c for c in contract["requirements"] if c["id"] != "MINT-SECURITY"]
        with self.assertRaises(ValueError):
            validate_policy(contract)

    def test_missing_second_oracle_fails(self):
        contract = json.loads((ROOT / "qa/mint-acceptance-v1.json").read_text())
        contract["requirements"][0]["methods"] = ["one-check"]
        with self.assertRaises(ValueError):
            validate_policy(contract)


if __name__ == "__main__":
    unittest.main()
