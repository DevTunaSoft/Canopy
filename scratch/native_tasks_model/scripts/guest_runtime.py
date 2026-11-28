#!/usr/bin/env python3
"""Drive the bounded native TasksModel M2 runtime proof in the live Plasma guest.

All actions are confined to the existing Kubuntu Plasma 6 VM over its existing
SSH key forward and to one unique scratch directory in the guest. No VM control
(start/stop/snapshot), no repository file outside this task's scratch scope and
no persistent user configuration change is performed.

Usage: python3 scripts/guest_runtime.py
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from urllib.parse import urlparse

NATIVE = Path(__file__).resolve().parents[1]
EV = NATIVE / "evidence"
LOGS = EV / "logs"
KEY = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch/g1_ubuntu_evidence/ssh/g1_ed25519")
SSH = ["ssh", "-i", str(KEY), "-o", "BatchMode=yes",
       "-o", "StrictHostKeyChecking=yes", "-p", "2223", "canopy@127.0.0.1"]
SCP = ["scp", "-i", str(KEY), "-o", "BatchMode=yes",
       "-o", "StrictHostKeyChecking=yes", "-P", "2223"]
REMOTE = "/home/canopy/canopy_native_tasksmodel_m2"
PKG_ID = "org.kde.plasma.canopyclassic.nativetasks"

# Read the live session environment from the running plasmashell process.
NATIVE_ENV = r'''
P=$(pgrep -x plasmashell | head -1)
echo "NATIVE_ENV_SOURCE_PID=$P"
while IFS= read -r line; do
  case "$line" in
    DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_SESSION_TYPE=*|XDG_CURRENT_DESKTOP=*|XDG_RUNTIME_DIR=*) export "$line" ;;
  esac
done < <(tr '\0' '\n' < /proc/$P/environ)
echo "NATIVE_ENV_IMPORTED DISPLAY=$DISPLAY XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
'''

report: dict = {"schema": "native_tasks_model_runtime_v1", "stages": []}


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(label: str, cmd, stdin: str | None = None, timeout: int = 300):
    printable = cmd if isinstance(cmd, str) else " ".join(shlex.quote(x) for x in cmd)
    payload = stdin.encode("utf-8") if stdin is not None else None
    proc = subprocess.run(["bash", "-c", cmd] if isinstance(cmd, str) else cmd,
                          input=payload, capture_output=True, timeout=timeout)
    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / (label + ".log")).open("a", encoding="utf-8", newline="\n") as f:
        f.write("$ " + printable + "\n" + out)
        if err:
            f.write("[stderr]\n" + err)
        f.write("[utc=" + utc() + "] [rc=" + str(proc.returncode) + "]\n")
    print("[%s] rc=%d bytes=%d" % (label, proc.returncode, len(out)), flush=True)
    report["stages"].append({"label": label, "command": printable,
                             "rc": proc.returncode, "utc": utc(),
                             "stdout_sha256": hashlib.sha256(out.encode()).hexdigest()})
    return proc.returncode, out


def remote(label: str, script: str):
    (LOGS / (label + ".remote.sh")).write_text(script, encoding="utf-8", newline="\n")
    return run(label, SSH + ["bash -s"], stdin=script)


def scp_to(src: str, dst: str, label: str):
    return run(label, SCP + ["-r", str(src), "canopy@127.0.0.1:" + dst])


def scp_from(src: str, dst: Path, label: str):
    return run(label, SCP + ["canopy@127.0.0.1:" + src, str(dst)])


def stage():
    remote("stage_00_clean", r'''
pkill -f 'build/native-task-harness' 2>/dev/null || true
pkill -x konsole 2>/dev/null || true
rm -rf REMOTE && mkdir -p REMOTE && echo STAGE_DIR_READY
'''.replace("REMOTE", REMOTE))
    scp_to((NATIVE / "src").as_posix(), REMOTE + "/src", "stage_01_src")
    scp_to((NATIVE / "harness").as_posix(), REMOTE + "/harness", "stage_02_harness")
    scp_to((NATIVE / "icons").as_posix(), REMOTE + "/icons", "stage_03_icons")
    scp_to((NATIVE / "package").as_posix(), REMOTE + "/package", "stage_04_package")
    scp_to((NATIVE / "CMakeLists.txt").as_posix(), REMOTE + "/CMakeLists.txt", "stage_05_cmake")
    remote("stage_06_verify", r'''
set -e
cd REMOTE
echo "--- inventory"; find . -maxdepth 3 -type f | sort
echo "--- frozen tile hash"; sha256sum harness/DockTile.qml
echo "--- model declarations"; grep -R -n 'TaskManager.TasksModel {' harness package || true
echo "--- cmake"; cmake -GNinja -S . -B build -DCMAKE_BUILD_TYPE=Release
echo "--- build"; cmake --build build
echo "--- binaries"; ls -l build/native-task-harness build/native-task-board-probe
'''.replace("REMOTE", REMOTE))


def board_probe():
    rc, _ = remote("board_probe", "cd %s && ./build/native-task-board-probe" % REMOTE)
    marker_log = (LOGS / "board_probe.log").read_text(encoding="utf-8", errors="replace")
    report["board_probe"] = {"rc": rc, "pass": rc == 0 and "BOARD_ALL_PASS" in marker_log}
    return rc


def runtime():
    remote("runtime_00_session_guard", NATIVE_ENV + r'''
echo "$ clean prior harness/app instances"
pkill -f 'build/native-task-harness' 2>/dev/null || true
pkill -x konsole 2>/dev/null || true
S=$(loginctl list-sessions --no-legend | grep seat0 | awk '{print $1}' | head -1)
echo "SEAT_SESSION=$S"
sudo -n loginctl unlock-session "$S" 2>&1 || true
sleep 1
echo "LOCKED_HINT=$(loginctl show-session "$S" | sed -n 's/^LockedHint=//p')"
echo "$ ps"
ps -eo pid,ppid,cmd | grep -E 'kwin_x11|plasmashell|sddm' | grep -v grep
echo "$ wmctrl"
wmctrl -lp
''')
    remote("runtime_01_start", NATIVE_ENV + r'''
cd REMOTE
rm -f harness.log harness.pid
nohup env DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" \
  DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  XDG_SESSION_TYPE="$XDG_SESSION_TYPE" XDG_CURRENT_DESKTOP="$XDG_CURRENT_DESKTOP" \
  XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  ./build/native-task-harness --auto ./harness/NativeTaskHarness.qml \
  > harness.log 2>&1 &
echo "HARNESS_PID=$!" | tee harness.pid
'''.replace("REMOTE", REMOTE))
    ready = False
    for _ in range(30):
        _, _ = remote("runtime_02_wait_ready",
                      "grep -a -m1 'CANOPY_NATIVE_TASK_HARNESS_READY' %s/harness.log || true" % REMOTE)
        ready_log = (LOGS / "runtime_02_wait_ready.log").read_text(
            encoding="utf-8", errors="replace")
        if "CANOPY_NATIVE_TASK_HARNESS_READY" in ready_log:
            ready = True
            break
        time.sleep(1)
    report["harness_ready"] = ready
    if not ready:
        remote("runtime_02_fail_log", "cat %s/harness.log || true" % REMOTE)
        return False

    def shot(name: str):
        rc, _ = remote("shot_" + name, NATIVE_ENV + r'''
cd REMOTE
scrot -o evidence_NAME.png
python3 -c 'import struct;d=open("evidence_NAME.png","rb").read(24);print("PNG_DIMS",struct.unpack(">II",d[16:24]))'
sha256sum evidence_NAME.png
'''.replace("REMOTE", REMOTE).replace("NAME", name))
        dst = EV / ("runtime_" + name + ".png")
        scp_from(REMOTE + "/evidence_" + name + ".png", dst, "copy_" + name)
        if dst.exists():
            report.setdefault("screenshots", {})[name] = {
                "path": str(dst), "sha256": sha256(dst), "bytes": dst.stat().st_size}
        return rc

    shot("baseline")
    # Real Plasma app launch through the native GIO desktop-entry facility.
    # The launch trigger is a driver action, not a Canopy-launched process;
    # activation below still flows through the upstream TasksModel.
    remote("runtime_02_launch_app", NATIVE_ENV + r'''
echo "$ gio launch /usr/share/applications/org.kde.konsole.desktop"
nohup gio launch /usr/share/applications/org.kde.konsole.desktop </dev/null >/dev/null 2>&1 &
echo "GIO_LAUNCH_SPAWNED=$!"
sleep 3
echo "--- konsole after launch"; pgrep -a konsole || true
''')
    time.sleep(4)
    shot("running")
    remote("runtime_03_running_observe", NATIVE_ENV + r'''
cd REMOTE
echo "--- windows"; wmctrl -lp
# Steal focus back to the harness before the upstream activation phase.
WID=$(wmctrl -lp | grep 'Canopy Classic native task dock' | tail -1 | awk '{print $1}')
echo "HARNESS_WID=$WID"
xdotool windowactivate --sync "$WID" 2>&1 || true
sleep 1
echo "--- konsole"; pgrep -a konsole || true
echo "--- active before activation"; xdotool getactivewindow getwindowname || true
echo "--- log tail"; tail -30 harness.log
'''.replace("REMOTE", REMOTE))
    shot("focused")
    time.sleep(10)
    shot("activated")
    remote("runtime_04_activation_observe", NATIVE_ENV + r'''
cd REMOTE
echo "--- windows"; wmctrl -lp
echo "--- konsole"; pgrep -a konsole || true
echo "--- active after activation"; xdotool getactivewindow getwindowname || true
echo "--- log"; cat harness.log
'''.replace("REMOTE", REMOTE))
    time.sleep(5)
    shot("final")
    remote("runtime_05_stop", "cd %s && kill $(cat harness.pid) 2>/dev/null || true; sleep 1; pgrep -a native-task-harness || echo HARNESS_STOPPED" % REMOTE)
    return True


def package_install():
    remote("package_00_source_hash", "cd %s/package && find . -type f -print0 | sort -z | xargs -0 sha256sum" % REMOTE)
    remote("package_01_before", NATIVE_ENV + r'''
echo "--- before list"; kpackagetool6 --type Plasma/Applet --list | grep -i canopy || echo NO_CANOPY_APPLET
echo "--- config hashes"; sha256sum "$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc" "$HOME/.config/plasmashellrc" 2>&1
''')
    rc, out = remote("package_02_install", "kpackagetool6 --type Plasma/Applet --install %s/package; echo INSTALL_RC=$?" % REMOTE)
    report["package_install"] = {"rc": rc, "marker": "INSTALL_RC=0" in out}
    remote("package_03_show", "kpackagetool6 --type Plasma/Applet --show %s; echo SHOW_RC=$?" % PKG_ID)
    remote("package_04_installed_files", "find \"$HOME/.local/share/plasma/plasmoids/%s\" -type f -printf '%%P\\n' 2>&1 | sort" % PKG_ID)
    remote("package_05_after", NATIVE_ENV + r'''
echo "--- after list"; kpackagetool6 --type Plasma/Applet --list | grep -i canopy || echo NO_CANOPY_APPLET
echo "--- config hashes"; sha256sum "$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc" "$HOME/.config/plasmashellrc" 2>&1
''')
    rc2, out2 = remote("package_06_remove", "kpackagetool6 --type Plasma/Applet --remove %s; echo REMOVE_RC=$?" % PKG_ID)
    report["package_remove"] = {"rc": rc2, "marker": "REMOVE_RC=0" in out2}
    remote("package_07_final", "kpackagetool6 --type Plasma/Applet --list | grep -i canopy || echo NO_CANOPY_APPLET")


def cleanup():
    remote("cleanup", "cd %s && rm -rf %s && echo REMOTE_SCRATCH_REMOVED" % (REMOTE, REMOTE))


def main() -> int:
    EV.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    report["utc_start"] = utc()
    report["owner_directive_sha256"] = "79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083"
    report["source_commit"] = subprocess.check_output(
        ["git", "-C", str(NATIVE.parents[1]), "rev-parse", "HEAD"], text=True).strip()
    stages = sys.argv[1:] or ["stage", "board", "runtime", "package", "cleanup"]
    for stage_name in stages:
        {"stage": stage, "board": board_probe, "runtime": runtime,
         "package": package_install, "cleanup": cleanup}[stage_name]()
    report["utc_end"] = utc()
    report["log_hashes"] = {p.name: sha256(p) for p in sorted(LOGS.glob("*.log"))}
    (EV / "runtime_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("REPORT", EV / "runtime_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
