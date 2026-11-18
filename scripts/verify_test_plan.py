"""Fail-closed test plan for a future isolated Mint VM worker.

Validates an explicit immutable commit ID against the locally checked-out tree.
Does not fetch code, authenticate to GitHub, or execute the approved code.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

REPO = "DevTunaSoft/Canopy"
CHECKS = frozenset({"unit", "syntax", "gtk"})
SHA = re.compile(r"[0-9a-f]{40}\Z")


def validate_plan(data):
    if not isinstance(data, dict) or set(data) != {"version", "repository", "commit", "checks"}:
        raise ValueError("Unexpected plan keys")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("Unsupported plan version")
    if data["repository"] != REPO:
        raise ValueError("Repository must be DevTunaSoft/Canopy")
    if not isinstance(data["commit"], str) or not SHA.fullmatch(data["commit"]):
        raise ValueError("Commit must be full lowercase SHA-1")
    checks = data["checks"]
    if not isinstance(checks, list) or not checks or len(checks) != len(set(
            value for value in checks if isinstance(value, str))):
        raise ValueError("Checks must be unique nonempty list")
    if any(not isinstance(value, str) or value not in CHECKS for value in checks):
        raise ValueError("Disallowed test check")
    return data


def verify_checkout(plan, checkout, *, executor=subprocess.run):
    plan = validate_plan(plan)
    checkout = Path(checkout).resolve()
    if not checkout.is_dir():
        raise ValueError("Checkout directory is missing")
    result = executor(
        ["git", "-C", str(checkout), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != plan["commit"]:
        raise ValueError("Checkout HEAD does not match approved commit")
    return {"status": "PASS", "repository": REPO, "commit": plan["commit"],
            "checks": list(plan["checks"]), "note": "Local commit equality only; not remote provenance"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a manually approved immutable test plan")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.plan.read_text(encoding="utf-8"))
        result = verify_checkout(data, args.checkout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
