"""Safe, optional Linux Mint guest runtime acceptance orchestrator.

Coordinates read-only host discovery and an opt-in guest run of the
repository's existing Mint preflight and Classic Qt self-test tools. Never
installs Linux, changes VM settings, alters images, reads passwords, or
declares Mint acceptance from anything but an authentic guest run with a
recorded command, exit status and logs.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from tools import mint_classic_qt_smoke as qt
from tools import mint_guest_preflight as preflight


SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 300
MAX_LOG_BYTES = 16384
MAX_VBOX_BYTES = 65536
MAX_PATH_LENGTH = 4096
VBOX_BIN = "VBoxManage"
SSH_BIN = "ssh"
ALLOWED_VBOX_SUBCOMMANDS = ("list", "showvminfo")
VM_LINE = re.compile(r'"([^"]+)"\s+\{([^}]+)\}')
STATE_LINE = re.compile(r'^VMState="([^"]+)"$', re.MULTILINE)
SMOKE_PASS_MARKER = "MINT_CLASSIC_QT_SMOKE_PASS"
HOST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,252}\Z")
USER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}\Z")
SHELL_META = set(";|&$`'\"<>()[]{}*?!~^#\\\r\n\t ")
NOT_RUN = "NOT_RUN"
BLOCKED = "BLOCKED"
DRY_RUN = "DRY_RUN"
FAIL = "FAIL"
EVIDENCE_PENDING = "EVIDENCE_PENDING_REVIEW"

_REPO_ROOT = Path(qt.__file__).resolve().parents[1]


class RuntimeSafetyError(ValueError):
    """Safety gate prevented an unsafe runner configuration."""


def _reject_constant(token):
    raise ValueError("non-finite JSON number rejected: " + token)


def _which(name):
    return shutil.which(name)


def _run(argv, timeout):
    if isinstance(argv, str):
        argv = [argv]
    return subprocess.run(
        list(argv), timeout=timeout, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )


def _bounded_text(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    if not isinstance(raw, (bytes, bytearray)):
        raw = b""
    truncated = len(raw) > MAX_LOG_BYTES
    text = bytes(raw[:MAX_LOG_BYTES]).decode("utf-8", "replace")
    return text, truncated


def validate_timeout(value):
    if type(value) is not int or not 1 <= value <= MAX_TIMEOUT:
        raise RuntimeSafetyError(
            "timeout must be an integer between 1 and " + str(MAX_TIMEOUT)
        )
    return value


def validate_guest_path(value, label):
    if not isinstance(value, str) or not value:
        raise RuntimeSafetyError(label + " must be a non-empty string")
    if "\x00" in value or len(value) > MAX_PATH_LENGTH:
        raise RuntimeSafetyError(label + " has a control character or bad length")
    if not value.startswith("/"):
        raise RuntimeSafetyError(label + " must be an absolute POSIX path")
    if any(char in SHELL_META for char in value):
        raise RuntimeSafetyError(label + " contains an unsafe path character")
    parts = value.split("/")
    if ".." in parts or any(len(part) > 255 for part in parts):
        raise RuntimeSafetyError(label + " contains an invalid path segment")
    return value


def validate_source_sha(value):
    if not isinstance(value, str) or not qt.SHA40.fullmatch(value):
        raise RuntimeSafetyError("source commit must be a 40-character lowercase SHA")
    return value


def vbox_command(subcommand, *args, binary=VBOX_BIN):
    if subcommand not in ALLOWED_VBOX_SUBCOMMANDS:
        raise RuntimeSafetyError("VBoxManage subcommand not allowed: " + str(subcommand))
    if not isinstance(binary, str) or not binary:
        raise RuntimeSafetyError("VBoxManage binary must be a non-empty string")
    return [binary, subcommand, *[str(arg) for arg in args]]


def ssh_command(host, user, remote_command, connect_timeout, binary=SSH_BIN):
    if not isinstance(host, str) or not HOST_RE.fullmatch(host):
        raise RuntimeSafetyError("invalid guest SSH host")
    if user is not None and (not isinstance(user, str) or not USER_RE.fullmatch(user)):
        raise RuntimeSafetyError("invalid guest SSH user")
    if not isinstance(remote_command, str) or not remote_command:
        raise RuntimeSafetyError("remote command required")
    validate_timeout(connect_timeout)
    if not isinstance(binary, str) or not binary:
        raise RuntimeSafetyError("ssh binary must be a non-empty string")
    target = host if user is None else user + "@" + host
    return [
        binary,
        "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", "ConnectTimeout=" + str(connect_timeout),
        target,
        "--",
        remote_command,
    ]


def guest_module_command(repo_dir, module, *args):
    validate_guest_path(repo_dir, "guest repository directory")
    if not hasattr(module, "__name__") or not module.__name__.startswith("tools."):
        raise RuntimeSafetyError("guest module must be a repository tool")
    tokens = ["cd", shlex.quote(repo_dir), "&&", "python3", "-m", module.__name__]
    tokens.extend(shlex.quote(str(arg)) for arg in args)
    return " ".join(tokens)


def build_commands(*, guest_host, guest_user, guest_repo_dir, binary, art_dir,
                   wallpaper, evidence_dir, source_sha, timeout,
                   connect_timeout, framing_review):
    validate_guest_path(guest_repo_dir, "guest repository directory")
    validate_guest_path(binary, "compiled Qt binary")
    validate_guest_path(art_dir, "approved art directory")
    validate_guest_path(wallpaper, "wallpaper")
    validate_guest_path(evidence_dir, "guest evidence directory")
    validate_source_sha(source_sha)
    connect_timeout = validate_timeout(connect_timeout)

    preflight_remote = guest_module_command(guest_repo_dir, preflight, "--json")
    smoke_args = [
        "--binary", binary,
        "--approved-art-dir", art_dir,
        "--landscape-wallpaper", wallpaper,
        "--output-dir", evidence_dir,
        "--source-sha", source_sha,
    ]
    if framing_review:
        smoke_args.append("--icon-framing-review")
    smoke_remote = guest_module_command(guest_repo_dir, qt, *smoke_args)
    return {
        "guest_preflight": ssh_command(
            guest_host, guest_user, preflight_remote, connect_timeout,
        ),
        "guest_smoke": ssh_command(
            guest_host, guest_user, smoke_remote, connect_timeout,
        ),
    }


def discover_host(*, which=None, runner=None, timeout=DEFAULT_TIMEOUT,
                  vbox_vm=None):
    which = which or _which
    runner = runner or _run
    host = {
        "vboxmanage": {"available": which(VBOX_BIN) is not None},
        "ssh": {"available": which(SSH_BIN) is not None},
        "vms": [],
        "errors": [],
    }
    if host["vboxmanage"]["available"]:
        argv = vbox_command("list", "vms")
        try:
            result = runner(argv, validate_timeout(timeout))
            output = getattr(result, "stdout", b"") or b""
            text, truncated = _bounded_text(output)
            if truncated or len(output) > MAX_VBOX_BYTES:
                host["errors"].append("VBoxManage output exceeded safe limit")
            else:
                for name, uuid in VM_LINE.findall(text):
                    item = {"name": name, "uuid": uuid, "state": None}
                    if vbox_vm == name:
                        info = vbox_command("showvminfo", name, "--machinereadable")
                        try:
                            info_result = runner(info, validate_timeout(timeout))
                            info_text, _ = _bounded_text(
                                getattr(info_result, "stdout", b"") or b""
                            )
                            state = STATE_LINE.search(info_text)
                            item["state"] = state.group(1) if state else "unknown"
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            host["errors"].append(
                                "showvminfo failed: " + exc.__class__.__name__
                            )
                    host["vms"].append(item)
        except (OSError, subprocess.TimeoutExpired) as exc:
            host["errors"].append("list vms failed: " + exc.__class__.__name__)
    return host


def _base_report(mode):
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "classic-mint-guest-runtime",
        "mode": mode,
        "status": NOT_RUN,
        "guest_runtime_acceptance": NOT_RUN,
        "mint_guest_acceptance": NOT_RUN,
        "real_application_launch": NOT_RUN,
        "visual_owner_approval": NOT_RUN,
        "authentic_logs_captured": False,
        "guest_ran_qt_binary": False,
        "host": None,
        "guest": None,
        "commands": None,
        "blockers": [],
        "execution": None,
        "notes": [],
    }


def finalize(report):
    report["notes"] = [
        "Read-only discovery and dry-run are the default; guest run is opt-in.",
        "Guest preflight and smoke data are self-reported hints, not provenance.",
        "Owner visual approval and independent Mint provenance stay separate gates.",
        "No passwords are read or accepted; SSH is forced non-interactive.",
    ]
    execution = report.get("execution")
    host = report.get("host") or {}
    missing = []
    if not host.get("vboxmanage", {}).get("available"):
        missing.append("VBoxManage not found on host")
    if not host.get("ssh", {}).get("available"):
        missing.append("ssh client not found on host")
    for error in host.get("errors", []):
        missing.append("host discovery error: " + error)
    blockers = list(report.get("blockers", []))
    if report["mode"] == "discover":
        report["status"] = DRY_RUN
        return report
    if report["mode"] != "execute":
        report["status"] = DRY_RUN
        return report
    if execution is None or not execution.get("attempted"):
        report["status"] = BLOCKED
        report["blockers"] = blockers + missing
        return report
    steps = {step["name"]: step for step in execution["steps"]}
    preflight_step = steps.get("guest_preflight", {})
    smoke_step = steps.get("guest_smoke", {})
    preflight_info = preflight_step.get("preflight") or {}
    guest_running_mint = (
        preflight_step.get("ok") is True
        and preflight_info.get("status") == "READY_FOR_TESTS"
        and preflight_info.get("mint_identified") is True
        and preflight_info.get("probe_only") is True
    )
    smoke_ok = (
        smoke_step.get("ok") is True
        and smoke_step.get("smoke_pass_marker") is True
    )
    report["guest_ran_qt_binary"] = smoke_ok
    report["authentic_logs_captured"] = (
        smoke_step.get("ok") is True
        and isinstance(smoke_step.get("command"), list)
        and smoke_step.get("exit_code") is not None
        and isinstance(smoke_step.get("stdout"), str)
    )
    if smoke_ok and guest_running_mint and report["authentic_logs_captured"]:
        report["status"] = EVIDENCE_PENDING
        report["guest_runtime_acceptance"] = EVIDENCE_PENDING
        report["real_application_launch"] = "PASS"
        report["mint_guest_acceptance"] = NOT_RUN
        report["notes"].append(
            "Guest Qt run evidence captured; Mint acceptance still NOT RUN "
            "pending independent provenance and owner visual review."
        )
    else:
        report["status"] = FAIL
        reasons = []
        if not guest_running_mint:
            reasons.append("no authentic READY_FOR_TESTS Mint preflight from guest")
        if not smoke_ok:
            reasons.append("no successful guest Qt self-test with pass marker")
        report["blockers"] = blockers + missing + reasons
    return report


def build_plan(*, guest_host, guest_user, guest_repo_dir, binary, art_dir,
               wallpaper, evidence_dir, source_sha, timeout=DEFAULT_TIMEOUT,
               connect_timeout=None, framing_review=False, vbox_vm=None,
               mode="dry-run", which=None, runner=None):
    if mode not in ("dry-run", "execute"):
        raise RuntimeSafetyError("mode must be dry-run or execute")
    connect_timeout = validate_timeout(
        connect_timeout if connect_timeout is not None else timeout
    )
    validate_timeout(timeout)
    commands = build_commands(
        guest_host=guest_host, guest_user=guest_user,
        guest_repo_dir=guest_repo_dir, binary=binary, art_dir=art_dir,
        wallpaper=wallpaper, evidence_dir=evidence_dir, source_sha=source_sha,
        timeout=timeout, connect_timeout=connect_timeout,
        framing_review=framing_review,
    )
    host = discover_host(which=which, runner=runner, timeout=timeout, vbox_vm=vbox_vm)
    report = _base_report(mode)
    report["host"] = host
    report["guest"] = {
        "host": guest_host,
        "user": guest_user,
        "repo_dir": guest_repo_dir,
        "vm": vbox_vm,
    }
    report["commands"] = commands
    report["blockers"] = []
    if vbox_vm is not None and not any(
        vm["name"] == vbox_vm for vm in host["vms"]
    ):
        report["blockers"].append("configured VM not found in VBoxManage inventory")
    return finalize(report)


def discover_report(*, which=None, runner=None, timeout=DEFAULT_TIMEOUT,
                    vbox_vm=None):
    report = _base_report("discover")
    report["host"] = discover_host(
        which=which, runner=runner, timeout=timeout, vbox_vm=vbox_vm,
    )
    return finalize(report)


def _parse_preflight(text):
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, TypeError):
        return None
    if type(data) is not dict:
        return None
    return {
        "status": data.get("status"),
        "mint_identified": data.get("mint_identified"),
        "probe_only": data.get("probe_only"),
        "session_type": data.get("session_type"),
    }


def _execute_step(name, argv, timeout, runner):
    step = {
        "name": name,
        "command": list(argv),
        "exit_code": None,
        "timed_out": False,
        "error": None,
        "stdout": "",
        "stderr": "",
        "logs_truncated": False,
        "ok": False,
        "smoke_pass_marker": False,
        "preflight": None,
    }
    try:
        result = runner(argv, timeout)
    except subprocess.TimeoutExpired:
        step["timed_out"] = True
        step["error"] = "command timed out"
        return step
    except OSError as exc:
        step["error"] = "command failed to start: " + exc.__class__.__name__
        return step
    step["exit_code"] = getattr(result, "returncode", None)
    stdout, out_truncated = _bounded_text(getattr(result, "stdout", b""))
    stderr, err_truncated = _bounded_text(getattr(result, "stderr", b""))
    step["stdout"] = stdout
    step["stderr"] = stderr
    step["logs_truncated"] = out_truncated or err_truncated
    step["ok"] = step["exit_code"] == 0
    full_stdout, _ = _bounded_text(getattr(result, "stdout", b""))
    step["smoke_pass_marker"] = SMOKE_PASS_MARKER in full_stdout
    if name == "guest_preflight":
        step["preflight"] = _parse_preflight(full_stdout)
    return step


def run_plan(report, *, runner=None, timeout=DEFAULT_TIMEOUT):
    runner = runner or _run
    if report.get("mode") != "execute":
        return finalize(report)
    validate_timeout(timeout)
    blockers = list(report.get("blockers", []))
    host = report.get("host") or {}
    if not host.get("vboxmanage", {}).get("available"):
        blockers.append("VBoxManage not found on host")
    if not host.get("ssh", {}).get("available"):
        blockers.append("ssh client not found on host")
    if blockers:
        report["blockers"] = blockers
        report["execution"] = {"attempted": False, "reasons": blockers, "steps": []}
        return finalize(report)

    execution = {"attempted": True, "reasons": [], "steps": []}
    report["execution"] = execution
    preflight_step = _execute_step(
        "guest_preflight", report["commands"]["guest_preflight"], timeout, runner,
    )
    execution["steps"].append(preflight_step)
    info = preflight_step.get("preflight") or {}
    ready = (
        preflight_step.get("ok") is True
        and info.get("status") == "READY_FOR_TESTS"
        and info.get("mint_identified") is True
        and info.get("probe_only") is True
    )
    if not ready:
        execution["reasons"].append(
            "guest preflight not ready; Qt self-test not attempted"
        )
        return finalize(report)
    smoke_step = _execute_step(
        "guest_smoke", report["commands"]["guest_smoke"], timeout, runner,
    )
    execution["steps"].append(smoke_step)
    return finalize(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guest-host")
    parser.add_argument("--guest-user")
    parser.add_argument("--guest-repo-dir")
    parser.add_argument("--binary")
    parser.add_argument("--approved-art-dir")
    parser.add_argument("--landscape-wallpaper")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--source-sha")
    parser.add_argument("--vbox-vm")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--connect-timeout", type=int)
    parser.add_argument("--icon-framing-review", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    options = parser.parse_args(argv)

    try:
        if options.discover_only:
            report = discover_report(
                timeout=options.timeout, vbox_vm=options.vbox_vm,
            )
        else:
            required = {
                "--guest-host": options.guest_host,
                "--guest-repo-dir": options.guest_repo_dir,
                "--binary": options.binary,
                "--approved-art-dir": options.approved_art_dir,
                "--landscape-wallpaper": options.landscape_wallpaper,
                "--evidence-dir": options.evidence_dir,
                "--source-sha": options.source_sha,
            }
            for flag, value in required.items():
                if value is None:
                    raise RuntimeSafetyError(flag + " is required")
            report = build_plan(
                guest_host=options.guest_host, guest_user=options.guest_user,
                guest_repo_dir=options.guest_repo_dir, binary=options.binary,
                art_dir=options.approved_art_dir,
                wallpaper=options.landscape_wallpaper,
                evidence_dir=options.evidence_dir,
                source_sha=options.source_sha, timeout=options.timeout,
                connect_timeout=options.connect_timeout,
                framing_review=options.icon_framing_review,
                vbox_vm=options.vbox_vm,
                mode="execute" if options.execute else "dry-run",
            )
            if options.execute:
                report = run_plan(report, timeout=options.timeout)
    except RuntimeSafetyError as exc:
        print("MINT_GUEST_RUNTIME_BLOCKED:", exc, file=sys.stderr)
        return 2
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("MINT_GUEST_RUNTIME_ERROR:", exc.__class__.__name__, file=sys.stderr)
        return 1

    if options.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("MINT_GUEST_RUNTIME_" + report["status"])
        print("GUEST_RUNTIME_ACCEPTANCE=" + report["guest_runtime_acceptance"])
        print("MINT_GUEST_ACCEPTANCE=" + report["mint_guest_acceptance"])
        for blocker in report["blockers"]:
            print("BLOCKED: " + blocker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
