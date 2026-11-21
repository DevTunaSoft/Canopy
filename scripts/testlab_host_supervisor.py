"""One-shot, host-owned unattended Mint test supervisor.

Designed for a Windows scheduled task invoked under a dedicated least-privilege
host account. Does not accept public PR events, deploy code, or reset VMs.
A successful unit/GTK run is NOT real Mint release acceptance.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from scripts.audit_test_evidence import audit, read_report
from scripts.testlab_run_ledger import advance, new_run, record_artifact
from scripts.testlab_ssh_cycle import run_cycle
from scripts.vbox_lab_controller import inspect_vm, operate
from scripts.verify_test_plan import validate_plan

VM_UUID = re.compile(r"[0-9a-fA-F-]{36}\Z")


@contextmanager
def host_lock(path):
    """OS-owned nonblocking file lock, released if the process crashes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("Another Canopy test supervisor is already running") from error
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise RuntimeError("Another Canopy test supervisor is already running") from error
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def store(path, content):
    """Small atomic host-local report replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".canopy-",
                                     suffix=".tmp", delete=False, encoding="utf-8") as f:
        temporary = Path(f.name)
        try:
            json.dump(content, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def require_config(config):
    if not isinstance(config, dict) or set(config) != {
        "vboxmanage", "expected_vm_uuid", "ssh_key",
        "known_hosts", "plan", "evidence_directory", "ssh_port"
    }:
        raise ValueError("Unexpected host-supervisor configuration")
    if not isinstance(config["expected_vm_uuid"], str) or not VM_UUID.fullmatch(
            config["expected_vm_uuid"]):
        raise ValueError("Dedicated VM UUID required")
    if type(config["ssh_port"]) is not int or not 1 <= config["ssh_port"] <= 65535:
        raise ValueError("Invalid SSH loopback port")
    for key in ("vboxmanage", "ssh_key", "known_hosts", "plan"):
        if not isinstance(config[key], str) or not Path(config[key]).is_file():
            raise ValueError(f"Missing host-only file: {key}")
    if not isinstance(config["evidence_directory"], str):
        raise ValueError("Evidence directory required")
    return config


def choose_action(previous, digest):
    """No repeated successful work; bounded three attempts for a failed plan."""
    if not isinstance(previous, dict) or previous.get("plan_sha256") != digest:
        return "RUN", 1
    state = previous.get("status")
    attempts = previous.get("attempts")
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError("Corrupt host attempts counter")
    if state == "PASS_TEST_SUITE_NOT_RELEASE":
        return "SKIP_ALREADY_GREEN", attempts
    if attempts >= 3:
        return "BLOCKED_ATTEMPT_LIMIT", attempts
    if state not in ("FAIL", "INCONCLUSIVE", "BLOCKED"):
        raise ValueError("Unknown previous host verdict")
    return "RUN", attempts + 1


def cycle(config, *, inspect=inspect_vm, operation=operate, guest_cycle=run_cycle,
          evidence_audit=audit):
    config = require_config(config)
    evidence_dir = Path(config["evidence_directory"]).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with host_lock(evidence_dir / ".supervisor.lock"):
        plan_path = Path(config["plan"]).resolve()
        raw = plan_path.read_bytes()
        if len(raw) > 8192:
            raise ValueError("Approved plan too large")
        plan = validate_plan(json.loads(raw))
        digest = hashlib.sha256(raw).hexdigest()
        state_file = evidence_dir / "supervisor-state.json"
        previous = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
        action, attempts = choose_action(previous, digest)
        if action != "RUN":
            return {"status": action, "attempts": attempts, "release_certified": False}

        vbox = config["vboxmanage"]
        vm = inspect(vbox)
        if vm["uuid"].lower() != config["expected_vm_uuid"].lower():
            raise ValueError("Observed VM identity does not match expected disposable UUID")
        if vm["state"] == "poweroff":
            result = operation(vbox, "start")
            if result["vm"]["uuid"].lower() != vm["uuid"].lower():
                raise RuntimeError("VM identity changed on startup")
        elif vm["state"] != "running":
            raise RuntimeError("Dedicated Mint VM is not in a safe executable state")

        ledger = new_run(plan["commit"])
        advance(ledger, "RUNNING")
        report_path = evidence_dir / (ledger["run_id"] + "-guest.json")
        outcome = "INCONCLUSIVE"
        reason = ""
        try:
            observed = guest_cycle(plan_path, ledger["run_id"], config["ssh_key"],
                                   config["known_hosts"], report_path, port=config["ssh_port"])
            if observed["commit"] != plan["commit"] or observed["run_id"] != ledger["run_id"]:
                raise RuntimeError("Guest transport returned conflicting commit/run identity")
            record_artifact(ledger, "received-guest", report_path)
            if observed["status"] == "PASS":
                checked = evidence_audit(read_report(report_path), plan["checks"])
                if checked["status"] != "PASS":
                    raise RuntimeError("Independent report audit did not pass")
                outcome = "PASS"
            else:
                outcome = "FAIL" if observed["status"] == "FAIL" else "BLOCKED"
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            reason = str(error)[:500]
        advance(ledger, outcome)
        result = {"plan_sha256": digest, "commit": plan["commit"],
                  "attempts": attempts, "run_id": ledger["run_id"],
                  "status": ("PASS_TEST_SUITE_NOT_RELEASE" if outcome == "PASS" else outcome),
                  "reason": reason, "release_certified": False,
                  "ledger": ledger}
        store(evidence_dir / (ledger["run_id"] + "-host.json"), result)
        store(state_file, {"plan_sha256": digest, "attempts": attempts,
                           "status": result["status"], "commit": plan["commit"]})
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Host-supervised approved Canopy test cycle")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = cycle(config)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(json.dumps({k:v for k,v in result.items() if k != "ledger"}, indent=2))
    return 0 if result["status"] in ("PASS_TEST_SUITE_NOT_RELEASE", "SKIP_ALREADY_GREEN") else 1


if __name__ == "__main__":
    sys.exit(main())
