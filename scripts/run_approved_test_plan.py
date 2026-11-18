"""Execute strictly allowlisted checks after verifying an approved clean checkout.

This is an integration helper, NOT a trusted approval or remote-code sandbox.
The machine owner must approve the plan and isolate the runner beforehand.
"""
import argparse
import json
from pathlib import Path
import sys

from scripts.mint_testlab import execute
from scripts.verify_test_plan import validate_plan, verify_checkout


def run_plan(plan_path, checkout, report_path, *, validator=verify_checkout,
             executor=execute):
    plan_path = Path(plan_path).resolve()
    checkout = Path(checkout).resolve()
    report_path = Path(report_path).resolve()
    # A plan or output located inside the checkout can invalidate the clean-tree
    # check and let untrusted test code overwrite the authorization evidence.
    for path in (plan_path, report_path):
        if path == checkout or checkout in path.parents:
            raise ValueError("Approval plan and output must be outside the source checkout")
    if plan_path == report_path:
        raise ValueError("Plan and output paths must differ")
    plan = validate_plan(json.loads(plan_path.read_text(encoding="utf-8")))
    verification = validator(plan, checkout)
    if verification.get("status") != "PASS":
        raise ValueError("Checkout verification did not pass")
    result = executor(checkout, report_path, list(plan["checks"]))
    return {"approved_commit": plan["commit"], "status": result["status"],
            "report": str(report_path), "checks": list(plan["checks"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Execute test-only approved Mint plan")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        outcome = run_plan(args.plan, args.checkout, args.output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(json.dumps(outcome, indent=2))
    return 0 if outcome["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
