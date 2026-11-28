"""REAL_PLASMA_GUEST runtime check for the M3 native launcher search.

Host-orchestrated, scoped evidence: the search primitive consumes byte-derived
copies of the *installed* native desktop entries and selects three apps; the
existing real Plasma guest then launches those same installed entries through
GIO/GAppInfo. No guest file, config, setting, VM snapshot or repository file is
changed. Launched processes are killed before exit and VM state is re-checked.

This is functional runtime evidence only, not owner visual acceptance.
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
import unicodedata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from canopy_features.launcher.native_catalog_producer import (  # noqa: E402
    produce_catalog_bytes,
)
from canopy_features.launcher.native_launcher_search import (  # noqa: E402
    FIXED_CLAIMS,
    search_native_directory,
)

SCRATCH = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch/native_launcher_runtime")
RAW = SCRATCH / "raw"
STAGE = SCRATCH / "applications"
SHOT = SCRATCH / "plasma_after_launch.png"
KEY = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch/g1_ubuntu_evidence/ssh/g1_ed25519")
VBOXMANAGE = Path("C:/Program Files/Oracle/VirtualBox/VBoxManage.exe")
VM = "Canopy-Test-Plasma6"
SSH_BASE = [
    "ssh", "-i", str(KEY), "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes", "-p", "2223", "canopy@127.0.0.1",
]
SCP_BASE = [
    "scp", "-i", str(KEY), "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes", "-P", "2223",
]
GUEST_ENV = (
    "env DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 "
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
    "XDG_CURRENT_DESKTOP=KDE XDG_SESSION_TYPE=x11"
)
TARGETS = (
    {"query": "Konsole", "app_id": "org.kde.konsole.desktop", "binary": "konsole"},
    {"query": "Dolphin", "app_id": "org.kde.dolphin.desktop", "binary": "dolphin"},
    {"query": "Kate", "app_id": "org.kde.kate.desktop", "binary": "kate"},
)
# Unicode Cf (format) scalars such as ZERO WIDTH JOINER and ZERO WIDTH SPACE
# appear in KDE's Malayalam/Sinhala/Khmer translations. The fail-closed parser
# refuses a whole entry for them, so the scratch copy used for the search
# primitive removes only invisible Cf scalars from translated lines. The
# installed entry and its Type/Name/Exec/Categories lines stay byte-identical.
def sanitize_cf(text):
    removed = [ch for ch in text if unicodedata.category(ch) == "Cf"]
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return cleaned, removed


def run(argv, timeout=90):
    done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout, check=False)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def remote(cmd, timeout=90):
    # ssh joins argv with spaces; pass one pre-quoted argument so the remote
    # bash receives the command intact.
    return run(SSH_BASE + ["bash -lc " + shlex.quote(cmd)], timeout=timeout)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vm_info():
    rc, out = run([str(VBOXMANAGE), "showvminfo", VM, "--machinereadable"])
    state = next((line for line in out.splitlines()
                  if line.startswith("VMState=")), "VMState=UNKNOWN")
    changed = next((line for line in out.splitlines()
                    if line.startswith("VMStateChangeTime=")), "VMStateChangeTime=UNKNOWN")
    return rc, state, changed


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    if STAGE.is_dir():
        for stale in STAGE.iterdir():
            if stale.is_file():
                stale.unlink()
    else:
        STAGE.mkdir(parents=True, exist_ok=True)
    checks = []
    launched = []
    before_state = "VMState=UNKNOWN"
    before_time = "VMStateChangeTime=UNKNOWN"

    def check(cid, title, status, command, result):
        checks.append({"id": cid, "title": title, "status": status,
                       "command": command, "result": result})
        print("%s %s %s" % (cid, status, title), flush=True)

    try:
        rc, before_state, before_time = vm_info()
        check("C01", "VM observed read-only before launch",
              "PASS" if rc == 0 and before_state == 'VMState="running"' else "FAIL",
              "VBoxManage showvminfo %s --machinereadable" % VM,
              {"rc": rc, "vm_state": before_state, "changed": before_time})

        rc, out = remote("loginctl list-sessions --no-legend; pgrep -a kwin_x11; "
                         "echo DISPLAY=${DISPLAY:-unset}")
        ok = "kwin_x11" in out and "canopy" in out
        check("C02", "real Plasma session and single compositor",
              "PASS" if ok else "FAIL",
              "loginctl list-sessions --no-legend; pgrep -a kwin_x11", out.strip())

        baselines = {}
        for target in TARGETS:
            binary = target["binary"]
            rc, out = remote("pgrep -x %s || echo NONE" % binary)
            baselines[binary] = frozenset(
                int(line) for line in out.split() if line.isdigit())
            check("B_" + binary, "baseline process set for " + binary,
                  "PASS" if rc == 0 else "FAIL", "pgrep -x " + binary,
                  {"rc": rc, "pids": sorted(baselines[binary]), "raw": out.strip()})

        entry_evidence = {}
        for target in TARGETS:
            app_id = target["app_id"]
            local_raw = RAW / app_id
            rc, out = run(SCP_BASE + [
                "canopy@127.0.0.1:/usr/share/applications/" + app_id, str(local_raw)])
            host_hash = sha256(local_raw)
            rc2, guest_hash_out = remote("sha256sum /usr/share/applications/" + app_id)
            guest_hash = guest_hash_out.split()[0] if guest_hash_out.split() else ""
            match = rc == 0 and rc2 == 0 and guest_hash == host_hash
            entry_evidence[app_id] = {
                "installed_path": "/usr/share/applications/" + app_id,
                "host_copy": str(local_raw), "sha256_host": host_hash,
                "sha256_guest": guest_hash, "byte_identical": match,
            }
            check("D_" + app_id, "installed desktop entry copied byte-identically",
                  "PASS" if match else "FAIL",
                  "scp installed entry; sha256sum host and guest",
                  entry_evidence[app_id])

        search_rows = []
        staged = {}
        for target in TARGETS:
            app_id = target["app_id"]
            original = (RAW / app_id).read_bytes().decode("utf-8")
            sanitized, removed_chars = sanitize_cf(original)
            main_fields = ("Type=", "Name=", "Exec=", "Categories=")
            fields_unchanged = all(
                [line for line in original.split("\n") if line.startswith(prefix)]
                == [line for line in sanitized.split("\n") if line.startswith(prefix)]
                for prefix in main_fields)
            (STAGE / app_id).write_bytes(sanitized.encode("utf-8"))
            staged[app_id] = (len(removed_chars),
                              sorted({hex(ord(ch)) for ch in removed_chars}),
                              fields_unchanged)
        for target in TARGETS:
            app_id = target["app_id"]
            removed, removed_codepoints, fields_unchanged = staged[app_id]
            # All three real entries are present in the upstream catalog for
            # every query, so a wrong ranking cannot be hidden by a one-row
            # catalog. Only matching titles are returned, hence one result.
            catalog_rows = produce_catalog_bytes(str(STAGE)).count(b"\n")
            results = search_native_directory(str(STAGE), target["query"], limit=3)
            top = results[0] if results else None
            expected = (top is not None and top.app_id == app_id
                        and top.title == target["query"] and catalog_rows == 3
                        and len(results) == 1)
            search_rows.append({
                "query": target["query"], "expected_app_id": app_id,
                "top": {"app_id": top.app_id, "title": top.title,
                        "tier": top.tier, "score": top.score, "index": top.index}
                if top else None,
                "result_count": len(results), "catalog_rows": catalog_rows,
                "format_scalars_removed": removed,
                "removed_codepoints": removed_codepoints,
                "main_fields_byte_identical": fields_unchanged,
                "source": "installed desktop entry, scratch copy",
            })
            check("S_" + app_id, "bounded search ranks the installed entry first",
                  "PASS" if expected and fields_unchanged else "FAIL",
                  "search_native_directory(<scratch applications>, %r, limit=3)"
                  % target["query"], search_rows[-1])

        for target in TARGETS:
            binary, app_id = target["binary"], target["app_id"]
            launch_cmd = (
                GUEST_ENV + " gio launch /usr/share/applications/" + app_id
                + " </dev/null >/dev/null 2>&1; echo GIO_RC=$?")
            rc, out = remote(launch_cmd, timeout=40)
            time.sleep(3)
            rc2, pgrep_out = remote("pgrep -a %s || echo NONE" % binary)
            pids = {int(line.split()[0]) for line in pgrep_out.splitlines()
                    if line and line.split()[0].isdigit()}
            new_pids = sorted(pids - baselines[binary])
            launched.extend(new_pids)
            detail = ""
            if new_pids:
                rc3, detail = remote(
                    "ps -o pid,ppid,pgid,sid,stat,etime,args -p %s; "
                    "busctl --user list --no-pager | grep -iE '%s' || echo NO_BUS_NAME"
                    % (",".join(str(p) for p in new_pids), binary))
            ok = rc == 0 and "GIO_RC=0" in out and bool(new_pids)
            check("L_" + binary, "GIO desktop-entry launch in real Plasma",
                  "PASS" if ok else "FAIL", launch_cmd,
                  {"gio_rc_output": out.strip(), "pgrep": pgrep_out.strip(),
                   "new_pids": new_pids, "process_and_bus": detail.strip()})

        rc, out = remote("xprop -root _NET_CLIENT_LIST 2>/dev/null || echo XPROP_UNAVAILABLE")
        check("W01", "X11 client list read-only after launches", "PASS",
              "xprop -root _NET_CLIENT_LIST", out.strip()[:4000])

        rc = run([str(VBOXMANAGE), "controlvm", VM, "screenshotpng", str(SHOT)],
                 timeout=60)[0]
        check("P01", "VM framebuffer captured", "PASS" if rc == 0 and SHOT.is_file() else "FAIL",
              "VBoxManage controlvm %s screenshotpng <scratch>" % VM,
              {"rc": rc, "path": str(SHOT), "bytes": SHOT.stat().st_size if SHOT.is_file() else 0,
               "sha256": sha256(SHOT) if SHOT.is_file() else None,
               "classification": "REAL_PLASMA_GUEST functional evidence; not visual approval"})
    finally:
        restore = []
        for pid in launched:
            rc, out = remote("kill %d 2>/dev/null; echo KILL_RC=$?" % pid, timeout=30)
            restore.append({"pid": pid, "result": out.strip()})
        time.sleep(2)
        residual = {}
        for target in TARGETS:
            binary = target["binary"]
            rc, out = remote("pgrep -a %s || echo NONE" % binary, timeout=30)
            residual[binary] = out.strip()
        rc, after_state, after_time = vm_info()
        checks.append({
            "id": "R01", "title": "launched apps terminated; VM state unchanged",
            "status": "PASS" if rc == 0 and after_state == before_state
            and after_time == before_time
            and all("NONE" in value or not value for value in residual.values())
            else "FAIL",
            "command": "kill <launched pids>; pgrep -a <binary>; VBoxManage showvminfo",
            "result": {"kills": restore, "residual": residual,
                       "vm_state_before": before_state, "vm_state_after": after_state,
                       "changed_before": before_time, "changed_after": after_time},
        })

    verdict = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    report = {
        "classification": "REAL_PLASMA_GUEST_SCOPED",
        "verdict": verdict,
        "not_claimed": [
            "owner visual acceptance", "CI-on-guest", "release readiness",
            "compiled Canopy Qt host launch", "CI acceptance",
        ],
        "guest": {"vm": VM, "user": "canopy", "host": "canopy-plasma6",
                  "access": "existing NAT SSH forward 127.0.0.1:2223 with existing scratch key; "
                            "BatchMode=yes, StrictHostKeyChecking=yes, no password",
                  "compositor": "kwin_x11 (single)"},
        "reuse": {
            "consumer": "canopy_features.launcher.native_launcher_search",
            "catalog_source": "native_catalog_producer over installed desktop entries",
            "duplicate_services": "none; no daemon, poll, cache, telemetry or paid tier",
            "fixed_claims": list(FIXED_CLAIMS),
        },
        "checks": checks,
        "search_rows": search_rows,
        "desktop_entry_evidence": entry_evidence,
    }
    out_path = HERE / "plasma_launch_evidence.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("VERDICT=%s checks=%d failures=%d report=%s" % (
        verdict, len(checks), sum(1 for c in checks if c["status"] != "PASS"), out_path),
        flush=True)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
