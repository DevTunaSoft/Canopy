"""Host-initiated, bounded test cycle over pinned-key SSH to disposable Mint VM.

Do not expose arbitrary remote shell, public ingress or privileged guest login.
A guest can lie: independent host checks and actual Cinnamon checks still needed.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from scripts.verify_test_plan import validate_plan

HOST = "canopy-test@127.0.0.1"
GUEST_REPO = "/home/canopy-test/Canopy"
GUEST_WORK = "/home/canopy-test/canopy-runs"
ID = re.compile(r"[a-f0-9]{32}\Z")


def ssh_args(identity, known_hosts, port):
    identity, known_hosts = Path(identity), Path(known_hosts)
    if not identity.is_file() or not known_hosts.is_file():
        raise ValueError("Explicit identity and pinned known_hosts files are required")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid host-loopback port")
    return ["ssh", "-F", "none", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + str(known_hosts.resolve()),
            "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=8",
            "-o", "ConnectionAttempts=1", "-i", str(identity.resolve()),
            "-p", str(port)]


def invoke(argv, *, runner=subprocess.run, timeout=180):
    try:
        result = runner(argv, capture_output=True, text=True, errors="replace",
                        check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Host transport unavailable: " + type(error).__name__) from error
    if len(result.stdout) + len(result.stderr) > 150000:
        raise RuntimeError("Host transport output exceeded cap")
    return result


def run_cycle(plan, run_id, identity, known_hosts, output, *,
              port=2222, runner=subprocess.run):
    plan = Path(plan).resolve()
    output = Path(output).resolve()
    if plan == output or not ID.fullmatch(run_id):
        raise ValueError("Invalid run identity or output path")
    if not plan.is_file() or plan.stat().st_size > 8192:
        raise ValueError("Missing or oversized approved plan")
    approved = validate_plan(json.loads(plan.read_text(encoding="utf-8")))
    base = ssh_args(identity, known_hosts, port)
    # Running tests is impossible until the guest is provisioned explicitly.
    # Do not silently accept a stale guest checkout or an unexpected account.
    remote_plan = GUEST_WORK + "/" + run_id + ".json"
    remote_report = GUEST_WORK + "/" + run_id + ".result.json"
    mkdir = invoke([*base, HOST, "mkdir -p " + GUEST_WORK], runner=runner, timeout=20)
    if mkdir.returncode:
        raise RuntimeError("Guest run directory unavailable")
    # SCP uses the same pinned known_hosts and explicit identity as SSH.
    scp = ["scp", "-F", "none", "-P", str(port), "-i", str(Path(identity).resolve()),
           "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "IdentitiesOnly=yes",
           "-o", "UserKnownHostsFile=" + str(Path(known_hosts).resolve())]
    copied = invoke([*scp, str(plan), HOST + ":" + remote_plan], runner=runner, timeout=30)
    if copied.returncode:
        raise RuntimeError("Approved plan upload failed")
    command = ("cd " + GUEST_REPO + " && PYTHONDONTWRITEBYTECODE=1 python3 -B -m scripts.run_approved_test_plan"
               " --plan " + remote_plan + " --checkout " + GUEST_REPO +
               " --output " + remote_report)
    execution = invoke([*base, HOST, command], runner=runner, timeout=180)
    # Collect report regardless of guest exit; do not trust its status alone.
    output.parent.mkdir(parents=True, exist_ok=True)
    copied_back = invoke([*scp, HOST + ":" + remote_report, str(output)],
                         runner=runner, timeout=30)
    if copied_back.returncode or not output.is_file() or output.stat().st_size > 300000:
        raise RuntimeError("Guest test report missing or oversized")
    data = json.loads(output.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise RuntimeError("Unexpected test report schema")
    status = data.get("status")
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        raise RuntimeError("Unknown guest test result")
    if (execution.returncode == 0) != (status == "PASS"):
        raise RuntimeError("Host-observed SSH exit contradicts guest result")
    names = [entry.get("name") for entry in data.get("checks", [])
             if isinstance(entry, dict)]
    if names != approved["checks"]:
        raise RuntimeError("Guest ran different checks from approved plan")
    return {"status": status, "host_observed_exit_code": execution.returncode,
            "commit": approved["commit"], "run_id": run_id, "report": str(output),
            "limitations": "Host observed transport exit, not proof of authentic guest GUI state"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run approved Canopy checks through pinned SSH")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--port", type=int, default=2222)
    args = parser.parse_args(argv)
    try:
        result = run_cycle(args.plan, args.run_id, args.identity,
                           args.known_hosts, args.output, port=args.port)
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
