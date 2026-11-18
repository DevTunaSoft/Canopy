"""Independent scenario/quorum gate for future Linux Mint acceptance.

Requires independent, fresh, matching-commit observations per scenario.
Does not run GUI tests or grant VM access.
"""
import argparse
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"[0-9a-f]{40}\Z")
STATUSES = frozenset({"PASS", "FAIL", "BLOCKED", "NOT_RUN", "INCONCLUSIVE"})
SCENARIOS = {
    "gtk-boot": ("runner", "window-observer"),
    "launcher-keyboard": ("widget-interaction", "window-observer"),
    "dock-narrow": ("geometry", "image-inspection"),
    "settings-corruption": ("filesystem-before-after", "recovery-ui"),
    "session-fallback": ("mint-session-manager", "reboot-login-check"),
    "resource-idle": ("proc-sampler", "independent-process-observer"),
    "vm-reset": ("host-snapshot-controller", "mint-boot-health"),
}


def baseline():
    return {"schema_version": 1, "scenarios": [
        {"id": key, "state": "NOT_RUN", "observations": []}
        for key in SCENARIOS]}


def evaluate(report, *, approved_commit, run_id):
    if not isinstance(approved_commit, str) or not SHA.fullmatch(approved_commit):
        raise ValueError("Expected immutable approved commit SHA")
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid run identifier")
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("Invalid test matrix schema")
    entries = report.get("scenarios")
    if not isinstance(entries, list) or len(entries) != len(SCENARIOS):
        raise ValueError("Missing or unexpected scenario coverage")
    seen = set()
    verdicts = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Malformed scenario")
        scenario = entry.get("id")
        if scenario not in SCENARIOS or scenario in seen:
            raise ValueError("Unknown or duplicated scenario")
        seen.add(scenario)
        state = entry.get("state")
        if state not in STATUSES:
            raise ValueError("Unknown scenario state")
        observations = entry.get("observations")
        if not isinstance(observations, list):
            raise ValueError("Missing observations")
        if len(observations) > 20:
            raise ValueError("Unbounded observation count")
        required = set(SCENARIOS[scenario])
        oracle_states = {}
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError("Malformed observation")
            oracle = observation.get("oracle")
            status = observation.get("status")
            if oracle not in required or oracle in oracle_states or status not in STATUSES:
                raise ValueError("Unknown, duplicate or malformed oracle observation")
            if observation.get("commit") != approved_commit or observation.get("run_id") != run_id:
                raise ValueError("Stale, unrelated or different-commit observation")
            proof = observation.get("artifact_sha256")
            if not isinstance(proof, str) or not re.fullmatch(r"[0-9a-f]{64}", proof):
                raise ValueError("Missing independently verifiable artifact digest")
            oracle_states[oracle] = status
        if state == "PASS":
            if set(oracle_states) != required or any(value != "PASS" for value in oracle_states.values()):
                raise ValueError(f"{scenario} claimed PASS without independent agreement")
            verdicts[scenario] = "PASS"
        elif state == "NOT_RUN":
            if observations:
                raise ValueError("NOT_RUN scenario has contradictory observations")
            verdicts[scenario] = "NOT_RUN"
        else:
            if state == "FAIL" and "FAIL" not in oracle_states.values():
                raise ValueError("FAIL scenario lacks a failing observation")
            if state == "BLOCKED" and "BLOCKED" not in oracle_states.values():
                raise ValueError("BLOCKED scenario lacks blocked evidence")
            verdicts[scenario] = state
    if seen != set(SCENARIOS):
        raise ValueError("Missing scenario")
    outcome = ("FAIL" if "FAIL" in verdicts.values() else
               "INCONCLUSIVE" if "INCONCLUSIVE" in verdicts.values() else
               "BLOCKED" if "BLOCKED" in verdicts.values() else
               "NOT_RUN" if "NOT_RUN" in verdicts.values() else "PASS")
    return {"status": outcome, "scenario_status": verdicts,
            "required_oracles": {key: list(value) for key, value in SCENARIOS.items()},
            "note": "Structural quorum only; artifacts and independent identities must be verified externally"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Multi-oracle Mint scenario acceptance gate")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    if args.baseline:
        print(json.dumps(baseline(), indent=2))
        return 0
    if not (args.report and args.commit and args.run_id):
        parser.error("Provide --report, --commit and --run-id together")
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        result = evaluate(report, approved_commit=args.commit, run_id=args.run_id)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
