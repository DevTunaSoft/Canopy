#!/usr/bin/env python3
"""Real native Plasma guest proof for install/config-change/uninstall/rollback.

Closes the B01 evidence gaps: N02/N03/N04 "config untouched" is measured with
direct before/after SHA-256+mode captures, not inferred from abort ordering.

Runs only against the dedicated Canopy-Test-Plasma6 VM via host VBoxManage and
SSH. Credential contents are never printed or stored; the key path is redacted
in the evidence. Writes only under this repo's scratch/native_rollback/ and a
single staging directory inside the dedicated test guest.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

SCRATCH = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch")
REPO = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-rollback-20261127")
OUT = REPO / "scratch" / "native_rollback"
LOGS = OUT / "logs"
SHOTS = OUT / "screenshots"
PKG = SCRATCH / "native_classic_reversible_install"
HIST_DIR = SCRATCH / "native_classic_reversible_install_runtime"
EVIDENCE = OUT / "native_rollback_runtime_evidence.json"

VBOX = "C:/Program Files/Oracle/VirtualBox/VBoxManage.exe"
VM = "Canopy-Test-Plasma6"
KEY = str(SCRATCH / "g1_ubuntu_evidence" / "ssh" / "g1_ed25519")
KH = str(SCRATCH / "g1_ubuntu_evidence" / "ssh" / "known_hosts")
GDIR = "/home/canopy/native_rollback_rt"
REMOTE = "canopy@127.0.0.1"
SSH_OPTS = ["-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KH,
            "-o", "ConnectTimeout=15", "-p", "2223"]
SCP_OPTS = ["-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KH,
            "-o", "ConnectTimeout=15", "-P", "2223"]
ENV = ("export HOME=/home/canopy USER=canopy DISPLAY=:0 XAUTHORITY=/tmp/xauth_FRFiEY "
       "XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
       "XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=KDE LANG=C.UTF-8; ")
CFG1 = "/home/canopy/.config/plasma-org.kde.plasma.desktop-appletsrc"
CFG2 = "/home/canopy/.config/plasmashellrc"
BIN_SRC = "/home/canopy/g2_source_bundle/build/classic/canopy-classic-spike"
WALL_SRC = ("/home/canopy/g2_source_bundle/source/prototype/classic/assets/"
            "approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png")
BIN_DST = "/home/canopy/.local/bin/canopy-classic"
MANIFEST = "/home/canopy/.local/share/canopy-classic/install-manifest.env"
BACKUP = "/home/canopy/.local/share/canopy-classic/backup"
META = BACKUP + "/snapshot.meta"
BIN_HASH = "4089251cf6a557d74ca308f3e32f59fea318f62d3285204e9ec7872bcc6b3f14"
WALL_HASH = "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381"

CFG_CMD = (
    "for c in %s %s; do printf 'CFG %%s sha256=%%s mode=%%s size=%%s\\n' "
    "\"$(basename \"$c\")\" \"$(sha256sum \"$c\"|awk '{print $1}')\" "
    "\"$(stat -c '%%a' \"$c\")\" \"$(stat -c '%%s' \"$c\")\"; done" % (CFG1, CFG2)
)
SNAP_CMD = (
    "bash -c 'M=%s; echo META_SHA=$(sha256sum $M|awk \"{print \\$1}\"); "
    "while IFS=$(printf \"\\t\") read -r p mo sh; do [ -n \"$p\" ] && "
    "printf \"SNAP\\t%%s\\t%%s\\t%%s\\n\" \"$p\" \"$mo\" \"$sh\"; done < $M; "
    "echo MANIFEST_SHA=$(sha256sum %s|awk \"{print \\$1}\")'" % (META, MANIFEST)
)

for directory in (OUT, LOGS, SHOTS):
    directory.mkdir(parents=True, exist_ok=True)

ledger: list[dict] = []
notes: list[str] = []
screenshots: list[dict] = []
checks: dict[str, object] = {}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def run(argv: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - record and keep the ledger terminal
        return 124, "HARNESS_EXCEPTION: %s" % type(exc).__name__
    out = clean(proc.stdout)
    err = clean(proc.stderr)
    return proc.returncode, out + (("\n[stderr]\n" + err) if err else "")


def guest(cmd: str, timeout: int = 300) -> tuple[int, str]:
    return run(["ssh"] + SSH_OPTS + [REMOTE, ENV + cmd], timeout)


def host(cmd: str, timeout: int = 300) -> tuple[int, str]:
    return run(["bash", "-c", cmd], timeout)


def record(cid, stage, command, rc, output, expect=0, contains=None,
           forbids=None, extra=None, logname=None):
    contains = contains or []
    forbids = forbids or []
    ok = rc == expect
    if not ok:
        notes.append("%s: rc=%s expected=%s" % (cid, rc, expect))
    for token in contains:
        if token not in output:
            ok = False
            notes.append("%s: missing expected token %r" % (cid, token))
    for token in forbids:
        if token in output:
            ok = False
            notes.append("%s: forbidden token present %r" % (cid, token))
    label = "PASS" if ok else "HOLD"
    entry = {"id": cid, "stage": stage, "label": label,
             "command": command, "rc": rc, "expected_rc": expect,
             "log": "logs/" + (logname or cid.lower() + ".out")}
    if contains:
        entry["expected_tokens"] = contains
    if forbids:
        entry["forbidden_tokens"] = forbids
    if extra:
        entry.update(extra)
    path = LOGS / (logname or cid.lower() + ".out")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("ID: %s\nSTAGE: %s\nLABEL: %s\nCOMMAND: %s\nrc=%s\n%s\n"
                     % (cid, stage, label, command, rc, output))
    ledger.append(entry)
    print("%-5s %-5s rc=%-3s %s" % (cid, label, rc, stage), flush=True)
    return ok, output


def gstep(cid, stage, cmd, expect=0, contains=None, forbids=None,
          extra=None, logname=None, timeout=300):
    rc, out = guest(cmd, timeout)
    return record(cid, stage, "ssh <redacted-key> %s: %s%s" % (REMOTE, ENV, cmd),
                  rc, out, expect, contains, forbids, extra, logname)


def hstep(cid, stage, cmd, expect=0, contains=None, forbids=None,
          extra=None, logname=None, timeout=300):
    rc, out = host(cmd, timeout)
    return record(cid, stage, cmd, rc, out, expect, contains, forbids, extra, logname)


def parse_cfg(text: str) -> dict:
    result = {}
    for match in re.finditer(r"^CFG (\S+) sha256=(\w+) mode=(\d+) size=(\d+)$",
                             text, re.M):
        result[match.group(1)] = {"sha256": match.group(2),
                                  "mode": match.group(3), "size": match.group(4)}
    return result


def parse_state(text: str) -> dict:
    cfg = parse_cfg(text)
    users = {}
    for match in re.finditer(r"^USERFILE (\S+) sha256=(\w+)$", text, re.M):
        users[match.group(1)] = match.group(2)
    return {"config": cfg, "user_files": users}


def cfg_step(cid, stage, logname=None):
    ok, out = gstep(cid, stage, CFG_CMD, logname=logname or cid.lower() + ".out")
    return ok, parse_cfg(out)


def state_step(cid, stage):
    ok, out = gstep(cid, stage, "bash %s/guest_state.sh" % GDIR,
                    contains=["=== STATE DONE ==="],
                    logname=cid.lower() + "_state.out")
    return ok, parse_state(out), out


def cfg_unchanged(control, before, after):
    equal = before == after
    checks[control + "_config_untouched"] = {
        "before": before, "after": after, "direct_hash_proof": True,
        "equal": equal,
    }
    ok, _ = record(control + "P", "%s direct before/after config proof" % control,
                   "host-side map comparison of %sB and %sU" % (control, control),
                   0 if equal else 1, "before=%s\nafter=%s\nequal=%s"
                   % (json.dumps(before, sort_keys=True),
                      json.dumps(after, sort_keys=True), equal),
                   logname=control.lower() + "p_config_proof.out")
    return ok


def shot(name):
    dest = SHOTS / (name + ".png")
    rc, out = run([VBOX, "controlvm", VM, "screenshotpng",
                   str(dest).replace("/", "\\")])
    if rc == 0 and dest.exists() and dest.stat().st_size > 1000:
        screenshots.append({"path": "screenshots/" + dest.name,
                            "sha256": sha_file(dest), "bytes": dest.stat().st_size,
                            "label": "PASS",
                            "capture": "real VBoxManage framebuffer capture"})
    else:
        notes.append("screenshot %s failed rc=%s %s" % (name, rc, out[:160]))
    print("SHOT %-22s rc=%s" % (name, rc), flush=True)


def write_manifest():
    files = sorted([p.relative_to(OUT).as_posix() for p in LOGS.glob("*.out")]
                   + [p.relative_to(OUT).as_posix() for p in SHOTS.glob("*.png")]
                   + ["run_native_rollback_proof.py"])
    with open(OUT / "SHA256SUMS.txt", "w", encoding="utf-8", newline="\n") as handle:
        for rel in files:
            handle.write("%s  %s\n" % (sha_file(OUT / rel), rel))


started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
print("START", started, flush=True)
pkg_hashes: dict[str, str] = {}
sums_sha: str = ""

try:
    # C00: pinned package integrity on the host (the exact scripts used in guest).
    pkg_files = ["install.sh", "uninstall.sh", "verify.sh", "rollback.sh", "README.md"]
    pkg_hashes = {name: sha_file(PKG / name) for name in pkg_files}
    sums_sha = sha_file(PKG / "SHA256SUMS")
    hstep("C00", "host pinned-package integrity + syntax",
          'cd "%s" && sha256sum -c SHA256SUMS && for f in install.sh uninstall.sh '
          'verify.sh rollback.sh; do bash -n "$f" || exit 1; done'
          % str(PKG).replace("\\", "/"),
          contains=[n + ": OK" for n in pkg_files],
          extra={"package_file_sha256": pkg_hashes, "SHA256SUMS_sha256": sums_sha})

    # C01/C02: stage the exact pinned scripts into the dedicated guest.
    rc_mkdir, out_mkdir = guest("mkdir -p " + GDIR)
    files = [str(PKG / name).replace("\\", "/") for name in
             ["install.sh", "uninstall.sh", "verify.sh", "rollback.sh",
              "README.md", "SHA256SUMS"]]
    files.append(str(HIST_DIR / "guest_state.sh").replace("\\", "/"))
    rc_scp, out_scp = run(["scp"] + SCP_OPTS + files + ["%s:%s/" % (REMOTE, GDIR)])
    record("C01", "guest staging of exact pinned scripts",
           "ssh <redacted-key> mkdir -p %s ; scp <pinned files> %s:%s/"
           % (GDIR, REMOTE, GDIR), 0 if rc_mkdir == 0 and rc_scp == 0 else 1,
           "mkdir_rc=%s\nscp_rc=%s\n%s%s" % (rc_mkdir, rc_scp, out_mkdir, out_scp),
           logname="c01_staging.out")
    gstep("C02", "guest pinned-package integrity + syntax",
          "cd %s && chmod 755 *.sh guest_state.sh && sha256sum -c SHA256SUMS && "
          "for f in install.sh uninstall.sh verify.sh rollback.sh; do bash -n \"$f\" || exit 1; done"
          % GDIR, contains=[n + ": OK" for n in pkg_files])

    # C03: remove only known install-generated leftovers from a prior failed
    # attempt; never touches Plasma config files or personal data.
    gstep("C03", "preflight normalization to stock (idempotent reruns)",
          "if [ -f %s ]; then (cd %s && bash rollback.sh --restore-only --no-restart) || true; fi; "
          "rm -f %s %s; rm -rf %s; rm -rf %s; "
          "echo MANIFEST=$([ -f %s ]&&echo PRESENT||echo ABSENT); "
          "echo BIN_INSTALLED=$([ -f %s ]&&echo PRESENT||echo ABSENT); "
          "echo AUTOSTART=$([ -f %s ]&&echo PRESENT||echo ABSENT); "
          "echo BACKUP=$([ -d %s ]&&echo PRESENT||echo ABSENT)"
          % (MANIFEST, GDIR, BIN_DST,
             "/home/canopy/.config/autostart/canopy-classic.desktop",
             "/home/canopy/.local/share/canopy-classic/wallpapers", BACKUP,
             MANIFEST, BIN_DST,
             "/home/canopy/.config/autostart/canopy-classic.desktop", BACKUP),
          contains=["MANIFEST=ABSENT", "BIN_INSTALLED=ABSENT",
                    "AUTOSTART=ABSENT", "BACKUP=ABSENT"])

    # P00: source asset pins really live in the guest.
    gstep("P00", "guest source asset pins + stock preflight",
          "echo BIN_SHA=$(sha256sum %s|awk \"{print \\$1}\"); "
          "echo WALL_SHA=$(sha256sum %s|awk \"{print \\$1}\"); "
          "echo MANIFEST=$([ -f %s ]&&echo PRESENT||echo ABSENT); "
          "echo BIN_INSTALLED=$([ -f %s ]&&echo PRESENT||echo ABSENT)"
          % (BIN_SRC, WALL_SRC, MANIFEST, BIN_DST),
          contains=["BIN_SHA=" + BIN_HASH, "WALL_SHA=" + WALL_HASH,
                    "MANIFEST=ABSENT", "BIN_INSTALLED=ABSENT"])

    ok_baseline, baseline, _ = state_step("S00", "baseline stock state + user-file hashes")
    checks["baseline"] = baseline

    # ---- cycle 1: install -> user edit -> uninstall -> negative controls -> R07 ----
    gstep("R01", "cycle 1 install (exact pinned assets)",
          "cd %s && bash install.sh --binary %s --wallpaper %s"
          % (GDIR, BIN_SRC, WALL_SRC),
          contains=["manifest written", "wallpaper applied via plasma-apply-wallpaperimage"])
    gstep("R02", "cycle 1 verify installed",
          "cd %s && bash verify.sh" % GDIR,
          contains=["STATUS=INSTALLED_INTEGRITY_OK"])
    # Upgrade fail-closed proof: install refuses an already-installed host.
    gstep("U00", "upgrade fail-closed: install refuses existing manifest",
          "cd %s && bash install.sh --binary %s --wallpaper %s"
          % (GDIR, BIN_SRC, WALL_SRC),
          expect=1, contains=["already installed (manifest:"],
          logname="u00_upgrade_refused.out")
    ok_snap, snap1 = gstep("R03", "cycle 1 snapshot manifest capture",
                           SNAP_CMD,
                           contains=["META_SHA=", "MANIFEST_SHA=", "SNAP\t"],
                           extra={"parsed": {}})
    out_snap1 = (LOGS / "r03.out").read_text(encoding="utf-8")
    checks["cycle1_snapshot"] = {
        "meta_sha256": re.search(r"META_SHA=(\w+)", out_snap1).group(1)
        if re.search(r"META_SHA=(\w+)", out_snap1) else None,
        "manifest_sha256": re.search(r"MANIFEST_SHA=(\w+)", out_snap1).group(1)
        if re.search(r"MANIFEST_SHA=(\w+)", out_snap1) else None,
        "rows": [line.split("\t")[1:] for line in out_snap1.splitlines()
                 if line.startswith("SNAP\t")],
    }
    gstep("R04", "cycle 1 user config edit after install",
          "printf '\\n# native-rollback-proof cycle1 user edit\\n' >> %s; "
          "echo CFG_EDITED_SHA=$(sha256sum %s|awk \"{print \\$1}\")" % (CFG1, CFG1),
          contains=["CFG_EDITED_SHA="])
    _, edit1 = cfg_step("R04X", "cycle 1 edited config hash")
    checks["cycle1_edited_config"] = edit1
    gstep("R05", "cycle 1 uninstall preserving user settings",
          "cd %s && bash uninstall.sh" % GDIR,
          contains=["preserving user settings", "kept manifest and snapshot",
                    "removed hash-verified Canopy binary, wallpaper and autostart entry"])
    _, preserved1 = cfg_step("R05P", "cycle 1 post-uninstall preservation proof")
    checks["cycle1_preserved_config"] = preserved1
    gstep("R06", "cycle 1 verify pending restore",
          "cd %s && bash verify.sh" % GDIR,
          contains=["STATUS=UNINSTALLED_PENDING_RESTORE",
                    "restore-only available: rollback.sh --restore-only"])

    # N01: tampered snapshot backup; direct config hashes too.
    gstep("N01SET", "N01 setup: corrupt one snapshot backup",
          "cp -p %s/$(basename %s) %s/n01_appletsrc.bak && printf 'CORRUPT' >> "
          "%s/$(basename %s) && echo TAMPERED_SHA=$(sha256sum "
          "%s/$(basename %s)|awk \"{print \\$1}\")"
          % (BACKUP, CFG1, GDIR, BACKUP, CFG1, BACKUP, CFG1),
          contains=["TAMPERED_SHA="])
    _, n01_before = cfg_step("N01B", "N01 config before refusal")
    gstep("N01", "N01 negative control: unhashed snapshot refused",
          "cd %s && bash rollback.sh --restore-only --no-restart" % GDIR,
          expect=1, contains=["snapshot hash mismatch"])
    _, n01_after = cfg_step("N01U", "N01 config after refusal")
    cfg_unchanged("N01", n01_before, n01_after)
    gstep("N01R", "N01 restore snapshot bytes",
          "cp -p %s/n01_appletsrc.bak %s/$(basename %s) && echo RESTORED_SHA=$(sha256sum "
          "%s/$(basename %s)|awk \"{print \\$1}\")" % (GDIR, BACKUP, CFG1, BACKUP, CFG1),
          contains=["RESTORED_SHA="])

    # N02/N03/N04: the actual historical evidence gap - direct before/after hashes.
    gstep("N02SET", "N02 setup: unhashed binary at installed path",
          "printf 'unknown-source-native-rollback' > %s && chmod 755 %s && "
          "echo PRESENT_SHA=$(sha256sum %s|awk \"{print \\$1}\")"
          % (BIN_DST, BIN_DST, BIN_DST), contains=["PRESENT_SHA="])
    _, n02_before = cfg_step("N02B", "N02 config before refusal")
    gstep("N02", "N02 negative control: unknown installed source refused",
          "cd %s && bash rollback.sh --no-restart" % GDIR,
          expect=1, contains=["installed binary present but not hash-pinned",
                              "refusing unknown asset"])
    _, n02_after = cfg_step("N02U", "N02 config after refusal")
    cfg_unchanged("N02", n02_before, n02_after)
    gstep("N02R", "N02 remove unknown source",
          "rm -f %s; echo BIN_AFTER=$([ -e %s ]&&echo PRESENT||echo ABSENT)"
          % (BIN_DST, BIN_DST), contains=["BIN_AFTER=ABSENT"])

    gstep("N03SET", "N03 setup: unknown snapshot asset row",
          "cp -p %s %s/n03_meta.bak && printf '/home/canopy/.config/unknown-source.conf\\t600\\t%s\\n' "
          "\"$(sha256sum %s|awk \"{print \\$1}\")\" >> %s && tail -1 %s"
          % (META, GDIR, BIN_HASH, META, META, META),
          contains=["unknown-source.conf"])
    _, n03_before = cfg_step("N03B", "N03 config before refusal")
    gstep("N03", "N03 negative control: unknown snapshot asset refused",
          "cd %s && bash rollback.sh --no-restart" % GDIR,
          expect=1, contains=["unknown snapshot asset refused"])
    _, n03_after = cfg_step("N03U", "N03 config after refusal")
    cfg_unchanged("N03", n03_before, n03_after)
    gstep("N03R", "N03 restore snapshot metadata bytes",
          "cp -p %s/n03_meta.bak %s && echo META_RESTORED_SHA=$(sha256sum %s|awk \"{print \\$1}\")"
          % (GDIR, META, META), contains=["META_RESTORED_SHA="])

    gstep("N04SET", "N04 setup: tamper manifest binary pin",
          "cp -p %s %s/n04_manifest.bak && sed -i 's|^CANOPY_BINARY_SHA256=.*|CANOPY_BINARY_SHA256=%s|' "
          "%s && grep '^CANOPY_BINARY_SHA256=' %s"
          % (MANIFEST, GDIR, "0" * 64, MANIFEST, MANIFEST),
          contains=["CANOPY_BINARY_SHA256=0000"])
    _, n04_before = cfg_step("N04B", "N04 config before refusal")
    gstep("N04", "N04 negative control: tampered manifest pin refused",
          "cd %s && bash rollback.sh --no-restart" % GDIR,
          expect=1, contains=["manifest binary pin mismatch", "refusing unknown asset"])
    _, n04_after = cfg_step("N04U", "N04 config after refusal")
    cfg_unchanged("N04", n04_before, n04_after)
    gstep("N04R", "N04 restore manifest bytes",
          "cp -p %s/n04_manifest.bak %s && echo MANIFEST_RESTORED_SHA=$(sha256sum %s|awk \"{print \\$1}\")"
          % (GDIR, MANIFEST, MANIFEST), contains=["MANIFEST_RESTORED_SHA="])

    # R07: automatic restore-only path after uninstall.
    gstep("R07", "cycle 1 auto restore-only rollback",
          "cd %s && bash rollback.sh --no-restart" % GDIR,
          contains=["restored stock config:", "removed manifest and snapshot",
                    "restore-only complete"])
    ok_r07s, r07_state, _ = state_step("R07S", "cycle 1 post-restore state")
    _, r07_cfg = cfg_step("R07X", "cycle 1 byte/mode-exact stock restore proof")
    checks["R07_exact_restore"] = {
        "live": r07_cfg, "baseline": baseline["config"],
        "exact": r07_cfg == baseline["config"]}
    record("R07C", "R07 exact-restore assertion",
           "host-side comparison of R07X config map against S00 baseline",
           0 if checks["R07_exact_restore"]["exact"] else 1,
           "R07=%s\nBASE=%s\nexact=%s"
           % (json.dumps(r07_cfg, sort_keys=True),
              json.dumps(baseline["config"], sort_keys=True),
              checks["R07_exact_restore"]["exact"]),
           logname="r07c_exact_assertion.out")
    shot("r07_stock"
         )
    gstep("R08", "cycle 1 verify stock after restore",
          "cd %s && bash verify.sh" % GDIR, contains=["STATUS=NOT_INSTALLED"])

    # ---- cycle 2: reinstall (upgrade path) -> edit -> uninstall -> explicit R15 ----
    gstep("R09", "cycle 2 reinstall (upgrade path)",
          "cd %s && bash install.sh --binary %s --wallpaper %s"
          % (GDIR, BIN_SRC, WALL_SRC),
          contains=["manifest written", "wallpaper applied via plasma-apply-wallpaperimage"])
    gstep("R10", "cycle 2 verify installed",
          "cd %s && bash verify.sh" % GDIR,
          contains=["STATUS=INSTALLED_INTEGRITY_OK"])
    gstep("R11", "cycle 2 snapshot manifest capture", SNAP_CMD,
          contains=["META_SHA=", "MANIFEST_SHA=", "SNAP\t"])
    gstep("R12", "cycle 2 user config edit after install",
          "printf '\\n# native-rollback-proof cycle2 user edit\\n' >> %s; "
          "echo CFG_EDITED_SHA=$(sha256sum %s|awk \"{print \\$1}\")" % (CFG1, CFG1),
          contains=["CFG_EDITED_SHA="])
    _, edit2 = cfg_step("R12X", "cycle 2 edited config hash")
    checks["cycle2_edited_config"] = edit2
    gstep("R13", "cycle 2 uninstall preserving user settings",
          "cd %s && bash uninstall.sh" % GDIR,
          contains=["preserving user settings", "kept manifest and snapshot"])
    _, preserved2 = cfg_step("R13P", "cycle 2 post-uninstall preservation proof")
    checks["cycle2_preserved_config"] = preserved2
    gstep("R14", "cycle 2 verify pending restore",
          "cd %s && bash verify.sh" % GDIR,
          contains=["STATUS=UNINSTALLED_PENDING_RESTORE"])
    gstep("R15", "cycle 2 explicit restore-only rollback",
          "cd %s && bash rollback.sh --restore-only --no-restart" % GDIR,
          contains=["restored stock config:", "removed manifest and snapshot",
                    "restore-only complete"])
    _, r15_cfg = cfg_step("R15X", "cycle 2 byte/mode-exact stock restore proof")
    checks["R15_exact_restore"] = {
        "live": r15_cfg, "baseline": baseline["config"],
        "exact": r15_cfg == baseline["config"]}
    record("R15C", "R15 exact-restore assertion",
           "host-side comparison of R15X config map against S00 baseline",
           0 if checks["R15_exact_restore"]["exact"] else 1,
           "R15=%s\nBASE=%s\nexact=%s"
           % (json.dumps(r15_cfg, sort_keys=True),
              json.dumps(baseline["config"], sort_keys=True),
              checks["R15_exact_restore"]["exact"]),
           logname="r15c_exact_assertion.out")
    shot("r15_stock"
         )
    gstep("R16", "cycle 2 verify final stock",
          "cd %s && bash verify.sh" % GDIR, contains=["STATUS=NOT_INSTALLED"])

    # Personal data preservation across both full cycles.
    ok_final, final_state, _ = state_step("R17", "final state before staging cleanup")
    user_equal = baseline["user_files"] == final_state["user_files"] and len(baseline["user_files"]) == 10
    checks["personal_data_preservation"] = {
        "count": len(baseline["user_files"]), "before": baseline["user_files"],
        "after": final_state["user_files"], "all_equal": user_equal}
    record("R18", "personal data preservation (10 user files)",
           "host-side comparison of USERFILE hashes from S00 and R17",
           0 if user_equal else 1,
           "before=%s\nafter=%s\nall_equal=%s"
           % (json.dumps(baseline["user_files"], sort_keys=True),
              json.dumps(final_state["user_files"], sort_keys=True), user_equal),
           logname="r18_user_files.out")

    # Stock fallback with no manifest: hash-pinned orphan cleanup, no config writes.
    gstep("F01SET", "stock fallback setup: pinned orphan binary, no manifest",
          "echo MANIFEST=$([ -f %s ]&&echo PRESENT||echo ABSENT); "
          "cp -p %s %s && chmod 755 %s && "
          "echo ORPHAN_SHA=$(sha256sum %s|awk \"{print \\$1}\")"
          % (MANIFEST, BIN_SRC, BIN_DST, BIN_DST, BIN_DST),
          contains=["MANIFEST=ABSENT", "ORPHAN_SHA=" + BIN_HASH])
    _, f01_before = cfg_step("F01B", "stock fallback config before")
    gstep("F01", "stock fallback with no manifest (orphan cleanup only)",
          "cd %s && bash rollback.sh --no-restart" % GDIR,
          contains=["WARN manifest missing", "removed orphan binary (SHA-256 matched pin)",
                    "WARN stock Plasma config was NOT restored",
                    "rollback orphan cleanup complete"])
    _, f01_after = cfg_step("F01U", "stock fallback config after")
    cfg_unchanged("F01", f01_before, f01_after)
    gstep("F01C", "stock fallback orphan removed",
          "echo BIN_AFTER=$([ -e %s ]&&echo PRESENT||echo ABSENT)" % BIN_DST,
          contains=["BIN_AFTER=ABSENT"])

    # Cleanup guest staging, then re-read state without depending on staging.
    gstep("R20", "remove guest staging created by this proof",
          "rm -rf %s; echo STAGING=$([ -e %s ]&&echo PRESENT||echo ABSENT)"
          % (GDIR, GDIR), contains=["STAGING=ABSENT"])
    script = (HIST_DIR / "guest_state.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    try:
        proc = subprocess.run(["ssh"] + SSH_OPTS + [REMOTE, ENV + "bash -s"],
                              input=script.encode("utf-8"), capture_output=True,
                              timeout=300)
        out = clean(proc.stdout.decode("utf-8", "replace"))
        err = clean(proc.stderr.decode("utf-8", "replace"))
        combined = out + (("\n[stderr]\n" + err) if err else "")
        record("R21", "final stock state after staging cleanup (inline probe)",
               "ssh <redacted-key> 'bash -s' < guest_state.sh (host inline)",
               proc.returncode, combined, contains=["=== STATE DONE ==="],
               logname="r21_state.out")
    except Exception as exc:  # noqa: BLE001
        record("R21", "final stock state after staging cleanup (inline probe)",
               "ssh <redacted-key> 'bash -s' < guest_state.sh (host inline)",
               124, "HARNESS_EXCEPTION: %s" % type(exc).__name__,
               logname="r21_state.out")
    hstep("R22", "VM state after proof",
          '"%s" showvminfo %s --machinereadable | grep -E "^(VMState|Forwarding)"'
          % (VBOX, VM), contains=['VMState="running"'], logname="r22_vm_state.out")
    checks["final_state"] = parse_state(combined) if "combined" in locals() else {}

except Exception as exc:  # noqa: BLE001 - keep a terminal evidence file on any harness error
    notes.append("HARNESS_FATAL: %s: %s" % (type(exc).__name__, exc))
finally:
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    holds = [row["id"] for row in ledger if row["label"] != "PASS"]
    n02_ok = checks.get("N02_config_untouched", {}).get("equal") is True
    n03_ok = checks.get("N03_config_untouched", {}).get("equal") is True
    n04_ok = checks.get("N04_config_untouched", {}).get("equal") is True
    r07_ok = checks.get("R07_exact_restore", {}).get("exact") is True
    r15_ok = checks.get("R15_exact_restore", {}).get("exact") is True
    data_ok = checks.get("personal_data_preservation", {}).get("all_equal") is True
    f01_ok = checks.get("F01_config_untouched", {}).get("equal") is True
    gap_closed = n02_ok and n03_ok and n04_ok and data_ok
    fatal = any(n.startswith("HARNESS_FATAL") or n.startswith("HARNESS_EXCEPTION")
                for n in notes)
    verdict = ("PASS" if (not holds and not fatal and r07_ok and r15_ok and f01_ok
                          and gap_closed) else "FAIL")
    report = {
        "schema_version": "native_rollback_runtime_evidence/1",
        "task": "M4 close B01 rollback evidence gaps with real native Plasma guest runtime proof",
        "owner_directive_sha": "79e30d79",
        "base_sha": "ec910d7a7275296ecbc8b5e5c459d356205165d1",
        "started_utc": started, "finished_utc": finished,
        "vm": {"name": VM, "state": "running", "guest_user": "canopy",
               "transport": "host VBoxManage + SSH on forwarded port 2223",
               "credential_note": "key path redacted; no credential content recorded"},
        "scope": ("real dedicated test VM runtime; no main merge, no release, "
                  "no visual approval, no host apt/dpkg changes"),
        "package": {"path": "C:/Users/X1/AppData/Local/hermes/cache/scratch/native_classic_reversible_install",
                    "SHA256SUMS_sha256": sums_sha, "files": pkg_hashes},
        "summary": {"steps": len(ledger), "pass": sum(1 for r in ledger if r["label"] == "PASS"),
                    "hold": len(holds), "hold_ids": holds,
                    "screenshots": len(screenshots), "notes": notes},
        "checks": checks, "ledger": ledger, "screenshots": screenshots,
        "gap_disposition": {
            "B01_PASS_WITH_GAPS": "superseded by this real-runtime pass for the measured scope",
            "N02_config_untouched": "DIRECT before/after hashes" if n02_ok else "NOT_PROVEN",
            "N03_config_untouched": "DIRECT before/after hashes" if n03_ok else "NOT_PROVEN",
            "N04_config_untouched": "DIRECT before/after hashes" if n04_ok else "NOT_PROVEN",
            "personal_data_preservation": "10 user files hashed before/after" if data_ok else "NOT_PROVEN",
            "R07_restoration": "byte/mode exact vs baseline" if r07_ok else "NOT_PROVEN",
            "R15_restoration": "byte/mode exact vs baseline" if r15_ok else "NOT_PROVEN",
            "stock_fallback_no_manifest": "config unchanged, pinned orphan removed" if f01_ok else "NOT_PROVEN",
        },
        "verdict": verdict,
        "release_ready": False,
    }
    with open(EVIDENCE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    write_manifest()
    print("EVIDENCE", EVIDENCE, "sha256=" + sha_file(EVIDENCE), flush=True)
    print("VERDICT", verdict, "steps=%d hold=%d" % (len(ledger), len(holds)), flush=True)
