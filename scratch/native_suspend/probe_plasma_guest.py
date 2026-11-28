"""M4 real-Plasma-guest suspend/resume probe (host orchestration only).

This helper is evidence tooling, not product code: it never imports or changes
Canopy modules. It drives the dedicated headless VirtualBox guest
``Canopy-Test-Plasma6`` through explicit subcommands and records every host and
guest observation with UTC time, exit status and SHA-256 of each screenshot.

No credential is typed: guest sudo is used only with ``-n``. The only guest
mutation is the explicit ``suspend`` subcommand; ``wake`` sends an ACPI power
button from the host. All other subcommands are read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VB = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
VM = "Canopy-Test-Plasma6"
KEY = r"C:\Users\X1\AppData\Local\hermes\cache\scratch\g1_ubuntu_evidence\ssh\g1_ed25519"
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
LOG = EVIDENCE / "probe.jsonl"

OBSERVE = (
    'echo "UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; '
    'echo "UPTIME=$(cat /proc/uptime)"; '
    'echo "--- session65 ---"; '
    'loginctl show-session 65 -p Type -p Display -p Active -p State -p LockedHint 2>&1; '
    'echo "--- shell processes ---"; '
    'pgrep -a plasmashell 2>&1 | head -3; '
    'pgrep -a kwin_x11 2>&1 | head -3; '
    'echo "--- user units ---"; '
    'systemctl --user is-active plasma-plasmashell.service 2>&1; '
    'echo "--- logind capability ---"; '
    'busctl call org.freedesktop.login1 /org/freedesktop/login1 '
    'org.freedesktop.login1.Manager CanSuspend 2>&1; '
    'echo "--- X clients (bounded; X may be unresponsive) ---"; '
    'XAUTHORITY=/tmp/xauth_zdKrsq DISPLAY=:0 timeout 5 wmctrl -l 2>&1; '
    'echo "WMCTRL_RC=$?"; '
    'echo OBSERVE_DONE'
)


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(entry):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")
    print(json.dumps(entry, sort_keys=True))


def run(argv, label, timeout=40, capture=True):
    started = time.time()
    rc = None
    out = ""
    err = ""
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout,
                              shell=False)
        rc = proc.returncode
        out = proc.stdout.decode("utf-8", "replace")[:20000]
        err = proc.stderr.decode("utf-8", "replace")[:5000]
    except subprocess.TimeoutExpired as exc:
        rc = "TIMEOUT"
        out = (exc.stdout or b"").decode("utf-8", "replace")[:20000]
        err = (exc.stderr or b"").decode("utf-8", "replace")[:5000]
    except OSError as exc:
        rc = "OS_ERROR"
        err = str(exc)
    entry = {
        "utc": utc(), "label": label, "argv": argv, "rc": rc,
        "seconds": round(time.time() - started, 3),
        "stdout": out if capture else "<captured to file>", "stderr": err,
    }
    record(entry)
    return entry


def ssh(remote, label, timeout=35):
    return run([
        "ssh", "-i", KEY, "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=4",
        "-o", "ServerAliveCountMax=2", "-p", "2223",
        "canopy@127.0.0.1", remote,
    ], label, timeout=timeout)


def vbox(*args, label="vbox", timeout=60, capture=True):
    return run([VB, *args], label, timeout=timeout, capture=capture)


def state():
    entry = vbox("showvminfo", VM, "--machinereadable",
                 label="vm-state", timeout=30)
    lines = [line for line in entry["stdout"].splitlines()
             if line.lower().startswith(("vmstate=", "vmstatechangetime="))]
    return {"utc": utc(), "state_lines": lines}


def capture(tag):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / (tag + ".png")
    entry = vbox("controlvm", VM, "screenshotpng", str(path),
                 label="screenshot-" + tag, timeout=60,
                 capture=False)
    digest = None
    if path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"utc": utc(), "tag": tag, "path": str(path),
              "sha256": digest, "rc": entry["rc"]}
    record(result)
    return result


def observe(tag):
    entry = ssh(OBSERVE, "observe-" + tag, timeout=40)
    path = EVIDENCE / (tag + "_observe.txt")
    path.write_text(entry["stdout"], encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"utc": utc(), "tag": tag, "path": str(path),
              "sha256": digest, "ssh_rc": entry["rc"]}
    record(result)
    return result


def reachable(timeout=12):
    return ssh("echo M4_REACHABLE", "reachability", timeout=timeout)


def suspend():
    # Detached so the SSH channel returns before the guest freezes.
    return ssh(
        '(setsid sudo -n systemctl suspend >/tmp/m4_suspend.log 2>&1 </dev/null &) '
        '; echo M4_SUSPEND_LAUNCHED',
        "guest-suspend-launch", timeout=20)


def wake():
    return vbox("controlvm", VM, "acpipowerbutton",
                label="host-acpi-wake", timeout=30)


def wait_reachable(attempts, delay, label):
    for index in range(attempts):
        entry = reachable()
        if entry["rc"] == 0 and "M4_REACHABLE" in entry["stdout"]:
            record({"utc": utc(), "label": label, "attempt": index + 1,
                    "result": "REACHABLE"})
            return True
        time.sleep(delay)
    record({"utc": utc(), "label": label, "attempt": attempts,
            "result": "UNREACHABLE"})
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "pre", "suspend", "during", "wake", "post", "state", "reachable"))
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.command == "pre":
        capture("before")
        observe("before")
        print(json.dumps(state()))
    elif args.command == "suspend":
        print(json.dumps(suspend()))
    elif args.command == "during":
        print(json.dumps(state()))
        capture("suspended")
        print(json.dumps({"reachable": wait_reachable(2, 2, "during-unreachable")}))
    elif args.command == "wake":
        print(json.dumps(wake()))
        print(json.dumps({"recovered": wait_reachable(20, 3, "after-wake")}))
    elif args.command == "post":
        print(json.dumps(state()))
        capture("after")
        observe("after")
    elif args.command == "state":
        print(json.dumps(state()))
    elif args.command == "reachable":
        print(json.dumps(reachable()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
