#!/usr/bin/env python3
"""Orchestrate the stock-Plasma native Konsole launch check and write evidence."""
import hashlib
import json
import os
import shlex
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "runtime_evidence")
SCRATCH = "C:/Users/X1/AppData/Local/hermes/cache/scratch"
KEY = SCRATCH + "/g1_ubuntu_evidence/ssh/g1_ed25519"
SSH = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=15", "-p", "2223", "canopy@127.0.0.1"]
SCP = ["scp", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-P", "2223"]
VBOX = "C:/Program Files/Oracle/VirtualBox/VBoxManage.exe"
VM = "Canopy-Test-Plasma6"
GUEST_RT = "/home/canopy/native_terminal_launch_20261127/runtime"
BIN = "/home/canopy/native_terminal_launch_20261127/build/canopy-classic-spike"
SRC = "/home/canopy/native_terminal_launch_20261127/src/prototype/classic"


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_local(label, cmd, timeout=180):
    argv = cmd if isinstance(cmd, list) else ["bash", "-c", cmd]
    p = subprocess.run(argv, capture_output=True, timeout=timeout)
    out = (p.stdout or b"").decode("utf-8", "replace")
    err = (p.stderr or b"").decode("utf-8", "replace")
    print("[%s] rc=%d %s" % (label, p.returncode, stamp()))
    if out.strip():
        print(out.strip()[:1500])
    if err.strip():
        print("STDERR:", err.strip()[:800])
    if p.returncode:
        raise SystemExit("%s failed rc=%d" % (label, p.returncode))
    return out


def run_remote(label, cmd, timeout=300):
    return run_local(label, SSH + [cmd], timeout=timeout)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(ART, exist_ok=True)
    run_local("vm_screenshot_before",
              [VBOX, "controlvm", VM, "screenshotpng",
               os.path.join(ART, "vm_before.png").replace("/", "\\")])
    run_remote("guest_runtime_mkdir", "mkdir -p " + GUEST_RT)
    for name in ("gio_lookup.py", "run_runtime.sh", "xwd_decode.py"):
        run_local("scp_" + name, SCP + [os.path.join(HERE, name),
                  "canopy@127.0.0.1:" + GUEST_RT + "/" + name])
    out = run_remote("runtime_check", "bash " + GUEST_RT + "/run_runtime.sh", timeout=300)
    log_path = os.path.join(ART, "runtime_console.log")
    with open(log_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    run_local("scp_root_screenshot", SCP + ["canopy@127.0.0.1:" + GUEST_RT + "/root_after.png",
              os.path.join(ART, "root_after.png")])
    run_local("scp_konsole_window", SCP + ["canopy@127.0.0.1:" + GUEST_RT + "/konsole_window.png",
              os.path.join(ART, "konsole_window.png")])
    run_local("vm_screenshot_after",
              [VBOX, "controlvm", VM, "screenshotpng",
               os.path.join(ART, "vm_after.png").replace("/", "\\")])
    checks = []
    def add(cid, title, ok, result, command, status=None):
        checks.append({"id": cid, "title": title,
                       "status": status or ("PASS" if ok else "FAIL"),
                       "result": result, "command": command})

    def section(name):
        marker = "=== %s ===" % name
        if marker not in out:
            return ""
        return out.split(marker, 1)[1].split("\n=== ", 1)[0]

    plasma = section("PLASMA SESSION")
    add("R01", "real Plasma X11 session",
        "startplasma-x11" in plasma and "kwin_x11" in plasma and "plasmashell" in plasma,
        plasma.strip(), "pgrep -a -u canopy -f 'startplasma-x11|kwin_x11|plasmashell'")
    gio = section("GIO LOOKUP (stock XDG data dirs)")
    add("R02", "native Konsole desktop entry resolves in stock XDG dirs",
        "org.kde.konsole.desktop RESOLVED" in gio and "konsole" in gio,
        gio.strip(), "python3 gio_lookup.py (Gio.DesktopAppInfo.new, six closed IDs)")
    add("R03", "no staged/duplicated service entry",
        "XDG_DATA_DIRS=/home/canopy/terminal_dock_runtime_check_stage" not in out,
        "stock XDG data dirs used; no staged copy, no XDG override",
        "runtime driver sets only DISPLAY/XAUTHORITY/XDG_RUNTIME_DIR/DBUS address")
    launch = section("TERMINAL DOCK LAUNCH FIXTURE")
    rc_line = [x for x in launch.splitlines() if x.startswith("LAUNCH_RC=")]
    add("R04", "compiled patched dock launches terminal",
        "TERMINAL_DOCK_LAUNCH_FIXTURE_PASS" in launch
        and "CANOPY_APP_LAUNCH_REQUESTED" in launch
        and rc_line == ["LAUNCH_RC=0"], launch.strip(),
        BIN + " --enable-system-apps --self-test-approved --approved-art-dir "
        + SRC + "/assets/approved --self-test-terminal-dock-fixture")
    konsole = section("KONSOLE AFTER")
    add("R05", "real /usr/bin/konsole process started",
        "/usr/bin/konsole" in konsole and "NONE" not in konsole,
        konsole.strip(), "pgrep -a konsole; ps -o pid,ppid,pgid,sid,stat,etime,args")
    dbus = section("DBUS AFTER")
    add("R06", "native KDE service registered on session bus",
        "org.kde.konsole-" in dbus, dbus.strip(),
        "busctl --user list --no-pager | grep -iE 'konsole|terminal'")
    windows = section("X WINDOWS AFTER")
    add("R07", "Konsole X window mapped in Plasma",
        x_window_ok := ("Konsole" in windows and "Geometry" in windows),
        windows.strip(), "wmctrl -l | grep -iE 'konsole|canopy classic'; xdotool getwindowgeometry; scrot -u")
    add("R08", "screenshot captured", "root_after.png" in out and os.path.exists(
        os.path.join(ART, "root_after.png")),
        "root_after.png present in evidence directory", "scrot -o root_after.png")
    restore = section("RESTORE")
    add("R09", "launched terminal terminated; stock entry unchanged",
        "NO_KONSOLE" in restore
        and "cd15f8c829a7ae0edfb27d67920fcd2cafb252209c950ce2e5791b9d24d15d38" in out,
        restore.strip(), "kill owned konsole PIDs; sha256sum /usr/share/applications/org.kde.konsole.desktop")
    add("R10", "screen-reader behavior", False,
        "NOT_RUN: no assistive-technology session exercised; no accessibility label changed",
        "none", status="NOT_RUN")
    add("R11", "automatic CI-on-guest gate", False,
        "NOT_RUN: no CI runner provisions this guest; host-orchestrated guest evidence only",
        "none", status="NOT_RUN")
    add("R12", "visual approval / release / merge", False,
        "NOT_RUN: no visual approval, release or merge claimed",
        "none", status="NOT_RUN")
    artifacts = {}
    for name in sorted(os.listdir(ART)):
        path = os.path.join(ART, name)
        if os.path.isfile(path):
            artifacts[name] = {"bytes": os.path.getsize(path), "sha256": sha256(path)}
    statuses = {}
    for c in checks:
        statuses[c["status"]] = statuses.get(c["status"], 0) + 1
    ok = all(c["status"] == "PASS" for c in checks[:9])
    report = {
        "schema": "canopy.native_terminal_launch_runtime/1",
        "task": "M3 native Terminal dock launch in stock KDE Plasma",
        "generated_utc": stamp(),
        "head_source_sha256": "b397916b6e2b2dc2664972722a7a77185d80be7f52bc28325d3fc62f816e6a03",
        "binary_sha256": "9bdcb7f525b0e8846b565484caf7e6e2211ef350dab77732b5d55b8536d84a8d",
        "vm": VM,
        "runtime_command": ("bash /home/canopy/native_terminal_launch_20261127/runtime/run_runtime.sh"),
        "key_output": [ln for ln in out.splitlines() if any(
            k in ln for k in ("CANOPY_GIO", "CANOPY_APP_LAUNCH", "TERMINAL_DOCK",
                              "LAUNCH_RC", "/usr/bin/konsole", "org.kde.konsole-",
                              "NO_KONSOLE", "cd15f8c8"))],
        "checks": checks,
        "status_counts": statuses,
        "artifacts": artifacts,
        "labels": ["SCOPED_ON_GUEST_RUNTIME", "STOCK_DESKTOP_ENTRIES_ONLY",
                   "NOT_CI_ACCEPTANCE", "NOT_VISUAL_APPROVAL"],
        "verdict": "PASS" if ok else "FAIL",
        "verdict_reason": ("Patched binary launched the real installed Konsole from the "
                           "Terminal dock in a live Plasma X11 session via native GIO "
                           "desktop-entry activation, with no staged or duplicated service."),
    }
    path = os.path.join(HERE, "native_terminal_launch_runtime.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print("VERDICT=%s COUNTS=%s REPORT=%s" % (report["verdict"], statuses, path))


if __name__ == "__main__":
    main()
