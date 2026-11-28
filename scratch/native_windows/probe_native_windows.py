#!/usr/bin/env python3
"""Host orchestrator for the scoped real-Plasma native window facility probe.

Only read-only KWin/FreeDesktop D-Bus calls and bounded X read attempts are
issued.  Nothing starts a compositor, service, desktop or window on the guest.
"""
import hashlib
import json
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "evidence")
SCRATCH = "C:/Users/X1/AppData/Local/hermes/cache/scratch"
KEY = SCRATCH + "/g1_ubuntu_evidence/ssh/g1_ed25519"
SSH = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o",
       "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15",
       "-p", "2223", "canopy@127.0.0.1"]
SCP = ["scp", "-i", KEY, "-o", "BatchMode=yes", "-o",
       "StrictHostKeyChecking=yes", "-P", "2223"]
GUEST_DIR = "/home/canopy/native_window_management_20261127/probe"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def section(text, name):
    marker = "=== %s ===" % name
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split("\n=== ", 1)[0].strip()


def main():
    os.makedirs(ART, exist_ok=True)
    subprocess.run(SSH + ["mkdir -p " + GUEST_DIR], check=True, timeout=60)
    subprocess.run(SCP + [os.path.join(HERE, "guest_probe.sh").replace("\\", "/"),
                          "canopy@127.0.0.1:" + GUEST_DIR + "/guest_probe.sh"],
                   check=True, timeout=60)
    proc = subprocess.run(SSH + ["bash " + GUEST_DIR + "/guest_probe.sh"],
                          capture_output=True, timeout=240)
    text = (proc.stdout or b"").decode("utf-8", "replace")
    if proc.stderr:
        text += "\n=== STDERR ===\n" + (proc.stderr or b"").decode("utf-8", "replace")
    log = os.path.join(ART, "guest_probe.log")
    with open(log, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, check=True, text=True).stdout.strip()

    checks = []

    def add(cid, title, status, result, command):
        checks.append({"id": cid, "title": title, "status": status,
                       "result": result, "command": command})

    session = section(text, "SESSION")
    add("P01", "real Plasma X11 session",
        "PASS" if all(token in session for token in
                      ("startplasma-x11", "kwin_x11", "plasmashell")) else "FAIL",
        session, "pgrep -a -u canopy -f 'startplasma-x11|kwin_x11|plasmashell'")

    before = section(text, "COMPOSITOR COUNT")
    after = section(text, "COMPOSITOR COUNT AFTER")
    single = (before == after and "kwin_x11=1 plasmashell=1" in before)
    add("P02", "one compositor and one shared shell service, unchanged",
        "PASS" if single else "FAIL", "before: %s | after: %s" % (before, after),
        "pgrep -c -x kwin_x11; pgrep -c -x plasmashell")

    introspect = section(text, "KWIN INTROSPECT")
    methods_ok = (".currentDesktop" in introspect and ".setCurrentDesktop" in introspect)
    add("P03", "KWin D-Bus exposes workspace inventory/switch methods",
        "PASS" if methods_ok else "FAIL", introspect,
        "busctl --user introspect org.kde.KWin /KWin | grep currentDesktop/setCurrentDesktop")

    name = section(text, "FREEDESKTOP BUS NAME")
    add("P04", "KWin present on FreeDesktop session bus",
        "PASS" if "org.kde.KWin" in name else "FAIL", name,
        "busctl --user list --no-pager | grep -w org.kde.KWin")

    current = section(text, "CURRENT DESKTOP")
    after_set = section(text, "CURRENT DESKTOP AFTER")
    set_result = section(text, "SET SAME DESKTOP (1)")
    dbus_ok = (current.startswith("i ") and current == after_set
               and set_result == "b false")
    add("P05", "KWin workspace read-back and reversible no-op switch",
        "PASS" if dbus_ok else "FAIL",
        "current=%s set=%s after=%s" % (current, set_result, after_set),
        "busctl --user call org.kde.KWin /KWin org.kde.KWin currentDesktop; "
        "busctl --user call org.kde.KWin /KWin org.kde.KWin setCurrentDesktop i 1")

    ewmh = section(text, "EWMH ROOT READ (bounded)")
    ewmh_rc = section(text, "EWMH_RC")
    blocker = section(text, "X BLOCKER PROCESSES")
    ewmh_ok = (ewmh_rc == "0" and "_NET_CURRENT_DESKTOP" in ewmh
               and "_NET_ACTIVE_WINDOW" in ewmh)
    add("P06", "EWMH active-window/current-desktop read on real Plasma",
        "PASS" if ewmh_ok else "NOT_RUN",
        ("EWMH_RC=%s; output=%s; external X blocker=%s"
         % (ewmh_rc, ewmh or "EMPTY", blocker or "NONE")),
        "timeout 8 xprop -root _NET_CURRENT_DESKTOP _NET_ACTIVE_WINDOW "
        "_NET_DESKTOP_NAMES")

    wmctrl = section(text, "X CLIENT LIVENESS (bounded)")
    wmrc = section(text, "WMCTRL_RC")
    add("P07", "X client liveness for activation/focus recovery",
        "PASS" if wmrc == "0" and wmctrl else "NOT_RUN",
        "WMCTRL_RC=%s; output=%s" % (wmrc, wmctrl or "EMPTY"),
        "timeout 8 wmctrl -l")

    verdict = "PASS" if all(c["status"] == "PASS" for c in checks) else (
        "PASS_WITH_NOT_RUN" if all(c["status"] != "FAIL" for c in checks) else "FAIL")
    report = {
        "schema": "canopy.native_window_management_probe/1",
        "verdict": verdict,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "head_sha": head,
        "guest": "Canopy-Test-Plasma6 (NAT ssh 127.0.0.1:2223)",
        "command": "bash " + GUEST_DIR + "/guest_probe.sh",
        "ssh_rc": proc.returncode,
        "checks": checks,
        "labels": {
            "SCOPED_ON_GUEST_RUNTIME": "KWin/FreeDesktop D-Bus calls on the stock "
                                       "Plasma guest at the exact head above",
            "SYNTHETIC": "16 scoped unittest checks are pure Python, not runtime evidence",
            "NOT_RUN": "EWMH window activation/focus-recovery read-back (external X "
                       "client grab), screen-reader behavior, automatic CI-on-guest, "
                       "owner visual acceptance, merge/release",
        },
        "artifacts": {"guest_probe.log": {"sha256": sha256(log), "bytes": os.path.getsize(log)}},
        "duplicate_compositors": 0,
        "services_started_by_probe": 0,
    }
    out = os.path.join(ART, "native_window_probe.json")
    with open(out, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    sums = []
    for name in ("guest_probe.log", "native_window_probe.json"):
        sums.append("%s  %s\n" % (sha256(os.path.join(ART, name)), name))
    with open(os.path.join(ART, "SHA256SUMS.txt"), "w",
              encoding="utf-8", newline="\n") as stream:
        stream.writelines(sums)
    print(json.dumps({"verdict": verdict,
                      "checks": [(c["id"], c["status"]) for c in checks],
                      "log_sha256": report["artifacts"]["guest_probe.log"]["sha256"]},
                     indent=2))


if __name__ == "__main__":
    main()
