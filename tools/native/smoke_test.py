#!/usr/bin/env python3
"""Host driver: build, install, smoke-test and restore on the reference VM.

The driver never approves a PR, never merges, never changes a branch other than
its own worktree, never guesses credentials and never uses sudo. It uses an
existing scratch SSH key, starts the existing VM only when it is powered off,
and leaves the VM running afterwards for other workers.

Labels are literal: PASS / FAIL / BLOCKED / NOT_RUN. A PASS is limited to the
development baseline verified in this run; it is not a release or visual claim.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from baseline_common import (
    APPROVED_WALLPAPER_SHA256, SOURCE_COMMIT, canonical_sha256,
    is_hex40, path_string, sha256_file,
)

TOOL_FILES = ("__init__.py", "baseline_common.py", "build_baseline.py",
              "guest_smoke.sh", "smoke_test.py")
TEMPLATE_FILES = ("metadata.json.template", "main.qml", "install.sh",
                  "uninstall.sh", "verify.sh")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command, *, timeout=600):
    started = utc_now()
    completed = subprocess.run([str(part) for part in command],
                               capture_output=True, text=True,
                               errors="replace", timeout=timeout)
    record = {
        "command": " ".join(shlex.quote(str(part)) for part in command),
        "started_utc": started, "rc": completed.returncode,
        "stdout": completed.stdout, "stderr": completed.stderr,
    }
    return record


class Driver:
    def __init__(self, args):
        self.args = args
        self.key = Path(args.ssh_key).resolve()
        self.vm = args.vm
        self.vbox_path = args.vboxmanage
        self.target = "%s@%s" % (args.ssh_user, args.ssh_host)
        self.guest_root = args.guest_root.rstrip("/")
        self.commands: list[dict] = []
        self.notes: list[str] = []

    def record(self, entry: dict):
        summary = {k: v for k, v in entry.items() if k not in ("stdout", "stderr")}
        self.commands.append(summary)
        return entry

    def ssh(self, script: str, *, timeout=900) -> dict:
        command = ["ssh", "-i", path_string(self.key), "-o", "BatchMode=yes",
                   "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                   "-p", str(self.args.ssh_port), self.target, script]
        return self.record(run(command, timeout=timeout))

    def scp_to(self, sources: list[Path], destination: str, *, recursive=False) -> dict:
        command = ["scp", "-i", path_string(self.key), "-o", "BatchMode=yes",
                   "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                   "-P", str(self.args.ssh_port)]
        if recursive:
            command.append("-r")
        command.extend(path_string(source) for source in sources)
        command.append("%s:%s" % (self.target, destination))
        return self.record(run(command, timeout=900))

    def scp_from(self, remote: str, local: Path, *, recursive=False) -> dict:
        command = ["scp", "-i", path_string(self.key), "-o", "BatchMode=yes",
                   "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                   "-P", str(self.args.ssh_port)]
        if recursive:
            command.append("-r")
        command.append("%s:%s" % (self.target, remote))
        command.append(path_string(local))
        return self.record(run(command, timeout=900))

    def vbox(self, *arguments: str, timeout=180) -> dict:
        return self.record(run([self.vbox_path, *arguments], timeout=timeout))

    def vm_state(self) -> str:
        result = self.vbox("showvminfo", self.vm, "--machinereadable")
        if result["rc"] != 0:
            return "UNKNOWN"
        for line in result["stdout"].splitlines():
            if line.startswith('VMState='):
                return line.split("=", 1)[1].strip('"')
        return "UNKNOWN"

    def ssh_ready(self) -> bool:
        result = self.ssh("echo NATIVE_BASELINE_SSH_READY", timeout=40)
        return result["rc"] == 0 and "NATIVE_BASELINE_SSH_READY" in result["stdout"]

    def plasma_session_ready(self) -> tuple[bool, str]:
        script = (
            'for s in $(loginctl list-sessions --no-legend | awk \'$3=="canopy" {print $1}\'); do '
            't=$(loginctl show-session "$s" -p Type --value 2>/dev/null); '
            'c=$(loginctl show-session "$s" -p Class --value 2>/dev/null); '
            'a=$(loginctl show-session "$s" -p Active --value 2>/dev/null); '
            'd=$(loginctl show-session "$s" -p Display --value 2>/dev/null); '
            'if [ "$t" = x11 ] && [ "$c" = user ] && [ "$a" = yes ]; then '
            'echo "session=$s Type=$t Class=$c Active=$a Display=$d"; exit 0; fi; done; '
            'echo NO_NATIVE_X11_SESSION'
        )
        result = self.ssh(script, timeout=120)
        output = result["stdout"].strip()
        return result["rc"] == 0 and "NO_NATIVE_X11_SESSION" not in output, output

    def ensure_vm(self) -> tuple[str, str]:
        """Start only a powered-off VM; never reset, save or stop a shared VM."""
        state = self.vm_state()
        if state == "running":
            self.notes.append("VM already running; shared use, no VM state mutation by this driver.")
        elif state in ("poweroff", "saved"):
            started = self.vbox("startvm", self.vm, "--type", "headless")
            if started["rc"] != 0:
                return "BLOCKED", "startvm failed: %s" % started["stderr"].strip()
            self.notes.append("Started existing VM from %s." % state)
        else:
            return "BLOCKED", "unexpected VM state %s; no state change attempted" % state
        for _ in range(24):
            if self.ssh_ready():
                return "PASS", "SSH ready on port %s" % self.args.ssh_port
            time.sleep(5)
        return "BLOCKED", "SSH did not become ready after VM state %s" % state


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--vboxmanage",
                        default="C:/Program Files/Oracle/VirtualBox/VBoxManage.exe")
    parser.add_argument("--vm", default="Canopy-Test-Plasma6")
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--ssh-host", default="127.0.0.1")
    parser.add_argument("--ssh-port", type=int, default=2223)
    parser.add_argument("--ssh-user", default="canopy")
    parser.add_argument("--guest-root", default="/home/canopy/native_build_baseline")
    parser.add_argument("--source-sha", default=SOURCE_COMMIT)
    parser.add_argument("--tree-sha", required=True)
    parser.add_argument("--skip-build", action="store_true",
                        help="reuse the guest build from a prior run")
    args = parser.parse_args(argv)

    worktree = Path(args.worktree).resolve()
    evidence = Path(args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    driver = Driver(args)
    result: dict = {
        "schema": "canopy.native.smoke_result/1",
        "started_utc": utc_now(),
        "scope": "DEVELOPMENT_BASELINE_ONLY;NO_RELEASE;NO_VISUAL_APPROVAL;NO_MERGE",
        "source_commit": args.source_sha,
        "source_tree": args.tree_sha,
        "approved_wallpaper_sha256": APPROVED_WALLPAPER_SHA256,
        "verdict": "BLOCKED",
        "checks": {},
        "notes": driver.notes,
    }

    try:
        if not worktree.is_dir() or not driver.key.is_file():
            raise RuntimeError("missing worktree or SSH key")
        if not is_hex40(args.source_sha) or not is_hex40(args.tree_sha):
            raise RuntimeError("source/tree SHA must be 40-hex git identities")
        commit = run(["git", "-C", path_string(worktree), "rev-parse",
                      "%s^{commit}" % args.source_sha], timeout=60)
        tree = run(["git", "-C", path_string(worktree), "rev-parse",
                    "%s^{tree}" % args.tree_sha], timeout=60)
        driver.record(commit)
        driver.record(tree)
        if commit["rc"] or commit["stdout"].strip().lower() != args.source_sha.lower():
            raise RuntimeError("pinned source commit is absent from the worktree")
        if tree["rc"] or tree["stdout"].strip().lower() != args.tree_sha.lower():
            raise RuntimeError("pinned source tree does not match --tree-sha")
        result["checks"]["source_pin"] = "PASS"
    except Exception as error:
        result["verdict"] = "BLOCKED"
        result["blocker"] = str(error)
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("SMOKE_BLOCKED: %s" % error, file=sys.stderr)
        return 2

    vm_status, vm_detail = driver.ensure_vm()
    result["checks"]["vm_available"] = vm_status
    result["vm_detail"] = vm_detail
    result["notes"] = driver.notes
    if vm_status != "PASS":
        result["blocker"] = vm_detail
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("SMOKE_BLOCKED: %s" % vm_detail, file=sys.stderr)
        return 2

    # Copy the exact pinned source tree plus only our owned native tooling.
    root = driver.guest_root
    mkdirs = driver.ssh("mkdir -p %s %s %s %s" % (shlex.quote(root),
                                                  shlex.quote(root + "/tools/native"),
                                                  shlex.quote(root + "/tools/native/templates"),
                                                  shlex.quote(root + "/evidence")))
    if mkdirs["rc"] != 0:
        result["blocker"] = "guest mkdir failed"
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2
    source_archive = evidence / "source_baseline.tar.gz"
    archive_command = run(["git", "-C", path_string(worktree), "archive",
                           "--format=tar.gz", "--prefix=source/", args.source_sha],
                          timeout=600)
    driver.record({k: v for k, v in archive_command.items() if k != "stdout"})
    if archive_command["rc"] != 0:
        result["blocker"] = "git archive failed"
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2
    archived = subprocess.run(
        ["git", "-C", path_string(worktree), "archive", "--format=tar.gz",
         "--prefix=source/", args.source_sha],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    if archived.returncode != 0:
        result["blocker"] = "git archive (binary capture) failed"
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2
    source_archive.write_bytes(archived.stdout)
    result["source_archive_sha256"] = sha256_file(source_archive)
    write_text(evidence / "source_archive.sha256", result["source_archive_sha256"] + "\n")

    remote_archive = root + "/source_baseline.tar.gz"
    copy_source = driver.scp_to([source_archive], root + "/")
    tool_files = [worktree / "tools/native" / name for name in TOOL_FILES]
    template_files = [worktree / "tools/native/templates" / name
                      for name in TEMPLATE_FILES]
    copy_tools = driver.scp_to(tool_files, root + "/tools/native/")
    copy_templates = driver.scp_to(template_files, root + "/tools/native/templates/")
    if any(item["rc"] != 0 for item in (copy_source, copy_tools, copy_templates)):
        result["blocker"] = "scp of pinned source or native tooling failed"
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2
    unpack = driver.ssh("rm -rf %s && mkdir -p %s && tar -xzf %s -C %s" %
                        (shlex.quote(root + "/source"), shlex.quote(root + "/source"),
                         shlex.quote(remote_archive), shlex.quote(root)))
    if unpack["rc"] != 0:
        result["blocker"] = "guest source unpack failed: %s" % unpack["stderr"].strip()
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2

    if not args.skip_build:
        emit = driver.ssh(
            "cd %s && python3 tools/native/build_baseline.py --source %s "
            "--out %s --source-sha %s --tree-sha %s --emit-source-id %s" %
            (shlex.quote(root), shlex.quote(root + "/source"), shlex.quote(root + "/out"),
             shlex.quote(args.source_sha), shlex.quote(args.tree_sha),
             shlex.quote(root + "/source/SOURCE_ID.json")), timeout=300)
        if emit["rc"] != 0:
            result["blocker"] = "SOURCE_ID emission failed: %s" % emit["stderr"].strip()
            write_text(evidence / "SMOKE_RESULT.json",
                       json.dumps(result, indent=2, sort_keys=True) + "\n")
            return 2
        build = driver.ssh(
            "cd %s && python3 tools/native/build_baseline.py --source %s "
            "--out %s --source-sha %s --tree-sha %s" %
            (shlex.quote(root), shlex.quote(root + "/source"), shlex.quote(root + "/out"),
             shlex.quote(args.source_sha), shlex.quote(args.tree_sha)), timeout=1800)
        write_text(evidence / "build_stdout.log", build["stdout"] + build["stderr"])
        result["checks"]["guest_build"] = "PASS" if build["rc"] == 0 else "FAIL"
        if build["rc"] != 0:
            result["blocker"] = "guest build failed; see build_stdout.log"
            result["notes"] = driver.notes
            write_text(evidence / "SMOKE_RESULT.json",
                       json.dumps(result, indent=2, sort_keys=True) + "\n")
            print(build["stdout"][-2000:] + build["stderr"][-2000:], file=sys.stderr)
            return 1

    build_evidence = evidence / "build"
    build_evidence.mkdir(parents=True, exist_ok=True)
    fetch_manifest = driver.scp_from(root + "/out/MANIFEST.json", build_evidence)
    fetch_result = driver.scp_from(root + "/out/BUILD_RESULT.json", build_evidence)
    fetch_sums = driver.scp_from(root + "/out/SHA256SUMS", build_evidence)
    fetch_logs = driver.scp_from(root + "/out/*.log", build_evidence)
    if any(item["rc"] != 0 for item in (fetch_manifest, fetch_result,
                                        fetch_sums, fetch_logs)):
        result["checks"]["artifact_copy_back"] = "FAIL"
        result["blocker"] = "build artifact copy-back failed"
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2
    manifest = json.loads((build_evidence / "MANIFEST.json").read_text(encoding="utf-8"))
    archive_name = manifest["package"]["archive"]
    archive_sha = canonical_sha256(manifest["package"]["archive_sha256"])
    binary_sha = canonical_sha256(manifest["binary"]["sha256"])
    wallpaper_sha = canonical_sha256(manifest["approved_assets"]["wallpaper"]["sha256"])
    if not (archive_sha and binary_sha and wallpaper_sha == APPROVED_WALLPAPER_SHA256):
        result["checks"]["manifest_identity"] = "FAIL"
        result["blocker"] = "manifest SHAs invalid or wallpaper pin differs"
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2
    result["checks"]["manifest_identity"] = "PASS"
    result["archive_sha256"] = archive_sha
    result["binary_sha256"] = binary_sha
    (build_evidence / "dist").mkdir(parents=True, exist_ok=True)
    fetch_archive = driver.scp_from(
        "%s/out/dist/%s" % (root, archive_name), build_evidence / "dist")
    local_archive = build_evidence / "dist" / archive_name
    if fetch_archive["rc"] != 0 or not local_archive.is_file() or \
       sha256_file(local_archive) != archive_sha:
        result["checks"]["archive_sha256_copy_back"] = "FAIL"
        result["blocker"] = "archive copy-back hash mismatch"
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2
    result["checks"]["archive_sha256_copy_back"] = "PASS"

    session_ready, session_detail = False, "NOT_CHECKED"
    for _ in range(24):
        session_ready, session_detail = driver.plasma_session_ready()
        if session_ready:
            break
        time.sleep(5)
    result["checks"]["real_plasma_session"] = "PASS" if session_ready else "BLOCKED"
    result["session_detail"] = session_detail
    if not session_ready:
        result["blocker"] = "no active native Plasma X11 user session in the guest"
        result["notes"] = driver.notes
        write_text(evidence / "SMOKE_RESULT.json",
                   json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 2

    env = {
        "ARCHIVE": "%s/out/dist/%s" % (root, archive_name),
        "ARCHIVE_SHA": archive_sha,
        "STATE": root + "/smoke-state",
        "RESULTS": root + "/smoke-results",
        "SOURCE_SHA": args.source_sha,
        "BINARY_SHA": binary_sha,
        "WALLPAPER_SHA": wallpaper_sha,
    }
    env_prefix = " ".join("%s=%s" % (key, shlex.quote(value))
                          for key, value in sorted(env.items()))
    smoke = driver.ssh(
        "%s bash %s" % (env_prefix, shlex.quote(root + "/tools/native/guest_smoke.sh")),
        timeout=1800)
    write_text(evidence / "smoke_stdout.log", smoke["stdout"] + smoke["stderr"])
    smoke_dir = evidence / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    fetch_smoke = driver.scp_from(root + "/smoke-results/*", smoke_dir)
    result["checks"]["guest_smoke_exit"] = "PASS" if smoke["rc"] == 0 else "FAIL"
    result["checks"]["smoke_logs_copy_back"] = \
        "PASS" if fetch_smoke["rc"] == 0 else "FAIL"
    checks_file = smoke_dir / "checks.txt"
    if checks_file.is_file():
        for line in checks_file.read_text(encoding="utf-8").splitlines():
            parts = line.split("|")
            if len(parts) == 4 and parts[0] == "CHECK":
                result["checks"][parts[1]] = parts[2]
                result.setdefault("details", {})[parts[1]] = parts[3]
    result["finished_utc"] = utc_now()
    result["notes"] = driver.notes
    failures = [name for name, status in result["checks"].items() if status == "FAIL"]
    if smoke["rc"] == 0 and fetch_smoke["rc"] == 0 and not failures:
        result["verdict"] = "PASS"
    elif failures:
        result["verdict"] = "FAIL"
        result["failures"] = sorted(failures)
    else:
        result["verdict"] = "BLOCKED"
    write_text(evidence / "SMOKE_RESULT.json",
               json.dumps(result, indent=2, sort_keys=True) + "\n")
    write_text(evidence / "HOST_COMMANDS.json",
               json.dumps(driver.commands, indent=2) + "\n")
    print("SMOKE_%s: checks=%s" % (result["verdict"],
                                   json.dumps(result["checks"], sort_keys=True)))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
