"""Independent fail-closed consistency audit of a Canopy test-lab report.

Does not trust a top-level PASS or a process exit status by itself.
This is a consistency oracle, not a cryptographic attestation of VM behavior.
"""
import argparse
import json
from pathlib import Path
import re
import sys

KNOWN = frozenset({"unit", "syntax", "gtk"})
TEST_COUNT = re.compile(r"\bRan (\d+) tests? in\b")
SKIPS = re.compile(r"\bskipped\s*=\s*(\d+)\b")
UNSAFE = re.compile(r"\bFAILED\s*\(|\bERROR\s*:")


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def read_report(path):
    path = Path(path)
    if path.stat().st_size > 300_000:
        raise ValueError("Oversized report")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=reject_duplicate_keys)


def audit(report, required=("unit", "syntax", "gtk")):
    """Require independently verifiable evidence for every selected check."""
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("Unsupported report schema")
    if report.get("status") != "PASS":
        raise ValueError("The test runner did not report PASS")
    if not isinstance(report.get("checks"), list):
        raise ValueError("Missing test checks")
    if not required or len(set(required)) != len(required) or set(required) - KNOWN:
        raise ValueError("Invalid required check list")
    checks = report["checks"]
    if len(checks) != len(required):
        raise ValueError("Check count differs from approved plan")
    found = set()
    counts = {}
    for item in checks:
        if not isinstance(item, dict):
            raise ValueError("Malformed test result")
        name = item.get("name")
        if not isinstance(name, str) or name not in required or name in found:
            raise ValueError("Unexpected or duplicated test name")
        found.add(name)
        if item.get("status") != "PASS" or type(item.get("exit_code")) is not int or item["exit_code"] != 0:
            raise ValueError(f"{name}: result conflicts with successful process exit")
        if item.get("output_truncated") is not False:
            raise ValueError(f"{name}: truncated logs cannot establish complete evidence")
        duration = item.get("duration_seconds")
        if type(duration) not in (int, float) or not 0 <= duration <= 900:
            raise ValueError(f"{name}: invalid timing evidence")
        if name == "syntax":
            counts[name] = None
            continue
        output = item.get("output")
        if not isinstance(output, str) or len(output) > 80_000:
            raise ValueError(f"{name}: absent or oversized unittest output")
        match = TEST_COUNT.search(output)
        if not match or int(match.group(1)) < 1:
            raise ValueError(f"{name}: missing nonzero unittest count")
        if UNSAFE.search(output) or not re.search(r"(?m)^OK(?:\s*\([^\n]*\))?\s*$", output):
            raise ValueError(f"{name}: no successful unittest summary")
        if name == "gtk":
            if any(int(n) for n in SKIPS.findall(output)):
                raise ValueError("GTK report contained skipped tests")
            # GTK suite must be more comprehensive than pure runner unit tests.
            if int(match.group(1)) < 2:
                raise ValueError("GTK suite had insufficient tests")
        counts[name] = int(match.group(1))
    if found != set(required):
        raise ValueError("Required checks are missing")
    return {"status": "PASS", "validated_checks": sorted(found),
            "unittest_counts": counts,
            "limitation": "Output/process consistency only; cannot authenticate a compromised test runner"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independently audit bounded test-lab evidence")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--checks", nargs="+", choices=sorted(KNOWN),
                        default=["unit", "syntax", "gtk"])
    args = parser.parse_args(argv)
    try:
        result = audit(read_report(args.report), args.checks)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
