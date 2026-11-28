#!/usr/bin/env python3
"""Enable/restore a real Plasma X11 session in the dedicated Canopy-Test-Plasma6 VM.

Used only for the native rollback runtime proof. Writes one temporary SDDM
autologin drop-in inside the test guest, restarts SDDM, and waits for a real
plasmashell process. --restore removes the drop-in and restarts SDDM.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

SCRATCH = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch")
OUT = SCRATCH / "wt-native-rollback-20261127" / "scratch" / "native_rollback"
KEY = str(SCRATCH / "g1_ubuntu_evidence" / "ssh" / "g1_ed25519")
KH = str(SCRATCH / "g1_ubuntu_evidence" / "ssh" / "known_hosts")
SSH_OPTS = ["-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KH,
            "-o", "ConnectTimeout=15", "-p", "2223"]
SCP_OPTS = ["-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KH,
            "-o", "ConnectTimeout=15", "-P", "2223"]
REMOTE = "canopy@127.0.0.1"
CONF_NAME = "91-native-rollback-proof.conf"
GUEST_CONF = "/etc/sddm.conf.d/" + CONF_NAME


def ssh(cmd, timeout=120):
    proc = subprocess.run(["ssh"] + SSH_OPTS + [REMOTE, cmd], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).replace("\r\n", "\n")


def scp(src, dest, timeout=120):
    proc = subprocess.run(["scp"] + SCP_OPTS + [src, REMOTE + ":" + dest],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).replace("\r\n", "\n")


mode = sys.argv[1] if len(sys.argv) > 1 else "enable"
if mode == "enable":
    local = OUT / CONF_NAME
    local.write_text("[Autologin]\nUser=canopy\nSession=plasmax11.desktop\n"
                     "Relogin=false\n", encoding="utf-8", newline="\n")
    rc, out = scp(str(local).replace("\\", "/"), "/tmp/" + CONF_NAME)
    print("SCP rc=%s %s" % (rc, out.strip()[:200]), flush=True)
    rc, out = ssh("sudo cp /tmp/%s %s && sudo rm -f /tmp/%s && "
                  "sudo systemctl restart sddm && echo SDDM_RESTARTED"
                  % (CONF_NAME, GUEST_CONF, CONF_NAME))
    print("ENABLE rc=%s %s" % (rc, out.strip()[:400]), flush=True)
    for attempt in range(1, 13):
        rc, out = ssh("echo PLASMA=$(pgrep -c -x plasmashell) "
                      "KWIN=$(pgrep -c -x kwin_x11)")
        print("PROBE %02d rc=%s %s" % (attempt, rc, out.strip()[:200]), flush=True)
        if "PLASMA=" in out:
            count = out.split("PLASMA=", 1)[1].split()[0]
            if count.isdigit() and int(count) >= 1:
                print("SESSION_READY", flush=True)
                break
        time.sleep(10)
    else:
        print("SESSION_NOT_READY", flush=True)
elif mode == "restore":
    # Remove the temporary drop-in only; do not restart SDDM, so the live
    # session (and the post-run state captured by the proof) stays intact.
    rc, out = ssh("sudo rm -f %s && echo CONF_REMOVED=$([ -e %s ]&&echo PRESENT||echo ABSENT)"
                  % (GUEST_CONF, GUEST_CONF))
    print("RESTORE rc=%s %s" % (rc, out.strip()[:400]), flush=True)
else:
    print("usage: guest_session_setup.py [enable|restore]")
    raise SystemExit(2)
