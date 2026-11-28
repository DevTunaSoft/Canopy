#!/usr/bin/env python3
"""Real Plasma-guest proof for the exact scripts/binary shipped in the dev bundle.

Run from the dev-artifact worktree:

    python scratch/native_dev_artifact/generate_shipped_rollback_proof.py

The harness extracts the committed archive (no rebuilt/substituted bytes),
verifies every inner hash on host and guest, stages the extracted KPackage
root unchanged into the dedicated Canopy-Test-Plasma6 guest, and records a
bounded install / in-place-upgrade / uninstall / reinstall ledger with exact
script and binary hashes. It writes SHIPPED_ROLLBACK_PROOF.json next to the
archive. It never writes production source, merges, approves or releases.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
ARCHIVE = OUT / "canopy-native-dev-artifact-20261128.tar.gz"
BUNDLE_ARCHIVE = "binary/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz"
PROOF = OUT / "SHIPPED_ROLLBACK_PROOF.json"

SCRATCH = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch")
KEY = str(SCRATCH / "g1_ubuntu_evidence" / "ssh" / "g1_ed25519")
KH = str(SCRATCH / "g1_ubuntu_evidence" / "ssh" / "known_hosts")
SSH_OPTS = ["-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KH,
            "-o", "ConnectTimeout=15", "-p", "2223"]
SCP_OPTS = ["-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KH,
            "-o", "ConnectTimeout=15", "-P", "2223"]
REMOTE = "canopy@127.0.0.1"
ENV = ("export HOME=/home/canopy USER=canopy DISPLAY=:0 XAUTHORITY=/tmp/xauth_FRFiEY "
       "XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
       "XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=KDE LANG=C.UTF-8; ")
GDIR = "/home/canopy/native_dev_shipped_proof"
CFG = "/home/canopy/.config/plasma-org.kde.plasma.desktop-appletsrc"
PACKAGE_ID = "org.kde.plasma.canopyclassic"

EXPECTED = {
    "install.sh": "a4f7ca9ca8fd6a2d4e0a68798b97bacc6a14806553f9829f591640f06c7ff5c2",
    "uninstall.sh": "94324c5eb7708fa884fc9f3c392ece6c0692b20d5246107ab922b5a61d03c9dc",
    "verify.sh": "ffa210cd22807db08dfbb7faafd21ef129eb5cca4d928f86f67c496119b7bb61",
    "metadata.json": "3f3207c50f87d3c68a0760676392b0e4825ea3512d531387e0ec86e03b278cbe",
    "contents/bin/canopy-classic-spike":
        "4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32",
    BUNDLE_ARCHIVE: "ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35",
}
PERSONAL = [
    "/home/canopy/.config/kwinoutputconfig.json",
    "/home/canopy/g2_g4_copy_hashes.txt",
    "/home/canopy/g2_g4_final_status.txt",
    "/home/canopy/g2_g4_manifest_check.txt",
    "/home/canopy/g2_g4_retry_status.txt",
    "/home/canopy/g2_g4_status.txt",
]


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def run(argv: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.SubprocessError as exc:
        return 124, "HARNESS_EXCEPTION: %s" % type(exc).__name__
    return proc.returncode, clean(proc.stdout) + (
        ("\n[stderr]\n" + clean(proc.stderr)) if proc.stderr.strip() else "")


def guest(command: str, timeout: int = 300) -> tuple[int, str]:
    return run(["ssh", *SSH_OPTS, REMOTE, ENV + command], timeout)


def host(command: str, timeout: int = 300) -> tuple[int, str]:
    return run(["bash", "-c", command], timeout)


ledger: list[dict] = []


def record(cid: str, stage: str, command: str, rc: int, output: str,
           expect: int = 0, contains: tuple[str, ...] = (),
           forbids: tuple[str, ...] = (), extra: dict | None = None) -> None:
    problems = []
    if rc != expect:
        problems.append("rc=%s expected=%s" % (rc, expect))
    for token in contains:
        if token not in output:
            problems.append("missing:%s" % token)
    for token in forbids:
        if token in output:
            problems.append("forbidden:%s" % token)
    row = {"cid": cid, "stage": stage, "command": command,
           "rc": rc, "expected_rc": expect, "result": "PASS" if not problems else "FAIL",
           "output": output[:4000]}
    if problems:
        row["problems"] = problems
    if extra:
        row.update(extra)
    ledger.append(row)


def wallclock() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    if not ARCHIVE.is_file():
        print("SHIPPED_PROOF_FAIL: archive missing: %s" % ARCHIVE, file=sys.stderr)
        return 2
    artifact_sha = sha_file(ARCHIVE)
    with tempfile.TemporaryDirectory(prefix="shipped_proof_") as tmp:
        root = Path(tmp) / "bundle"
        root_bash = root.as_posix().replace("C:/", "/c/")
        root_native = root.as_posix()
        with tarfile.open(ARCHIVE, "r:gz") as bundle:
            bundle.extractall(root, filter="data")
        pkg_root = root / "package"
        with tarfile.open(root / BUNDLE_ARCHIVE, "r:gz") as package:
            package.extractall(pkg_root, filter="data")
        inner_sums = {}
        for line in (pkg_root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split(None, 1)
            inner_sums[name.strip()] = digest.strip()
        inner_sums_sha = sha_file(pkg_root / "SHA256SUMS")
        hashes = {name: sha_file(root / name if name == BUNDLE_ARCHIVE else pkg_root / name)
                  for name in EXPECTED}
        mismatch = {name: (digest, hashes.get(name)) for name, digest in EXPECTED.items()
                    if hashes.get(name) != digest}
        record("C00", "host-identity",
               "sha256 of exact shipped scripts/binary/archive",
               0 if not mismatch else 1, json.dumps(hashes, sort_keys=True),
               extra={"expected": EXPECTED, "mismatch": mismatch})
        pkg_bash = pkg_root.as_posix().replace("C:/", "/c/")
        pkg_native = pkg_root.as_posix()
        rc, out = host("cd '%s' && sha256sum -c SHA256SUMS" % pkg_bash)
        for name in ("install.sh", "uninstall.sh", "verify.sh"):
            r2, o2 = host("bash -n '%s'" % (pkg_bash + "/" + name))
            rc, out = rc + r2, out + "\n" + o2
        record("C01", "host-verify", "inner SHA256SUMS -c and bash -n on shipped root",
               rc, out, contains=("install.sh: OK", "uninstall.sh: OK", "verify.sh: OK"))
        rc, out = guest("mkdir -p %s && rm -f %s/*.sh %s/SHA256SUMS" % (GDIR, GDIR, GDIR))
        record("C02", "guest-stage", "prepare staging directory", rc, out)
        rc, out = run(["scp", *SCP_OPTS, "-r", pkg_native + "/.", REMOTE + ":" + GDIR + "/"],
                      timeout=600)
        record("C03a", "guest-stage", "scp exact shipped package root to guest", rc, out)
        rc2, out2 = run(["scp", *SCP_OPTS, (root / BUNDLE_ARCHIVE).as_posix(),
                         REMOTE + ":" + GDIR + "/" + Path(BUNDLE_ARCHIVE).name],
                        timeout=600)
        record("C03b", "guest-stage", "scp exact shipped KPackage archive to guest", rc2, out2)
        rc, out = guest("cd %s && sha256sum -c SHA256SUMS && "
                        "for f in install.sh uninstall.sh verify.sh; do bash -n \"$f\" || exit 1; done "
                        "&& sha256sum install.sh uninstall.sh verify.sh metadata.json "
                        "contents/bin/canopy-classic-spike %s" % (GDIR, Path(BUNDLE_ARCHIVE).name))
        guest_hashes_ok = all(token in out for token in EXPECTED.values())
        record("C04", "guest-identity",
               "guest sha256sum -c, bash -n and exact shipped script/binary hashes",
               rc if guest_hashes_ok else 1, out,
               contains=("install.sh: OK", "uninstall.sh: OK", "verify.sh: OK",
                         EXPECTED["install.sh"], EXPECTED["uninstall.sh"],
                         EXPECTED["verify.sh"], EXPECTED["contents/bin/canopy-classic-spike"]))
        rc, out = guest("kpackagetool6 --type Plasma/Applet --list 2>/dev/null "
                        "| grep -Fxq %s && echo PACKAGE_PRESENT || echo PACKAGE_ABSENT" % PACKAGE_ID)
        record("C05", "preflight", "package absent before proof", rc, out,
               contains=("PACKAGE_ABSENT",), forbids=("PACKAGE_PRESENT",))
        rc, out = guest("sha256sum %s | awk '{print $1}' > %s/config.baseline.sha256; "
                        "cp -p %s %s/config.baseline; cat %s/config.baseline.sha256" %
                        (CFG, GDIR, CFG, GDIR, GDIR))
        baseline = clean(out).splitlines()[-1] if out.strip() else ""
        record("C06", "baseline", "capture Plasma config baseline bytes/hash", rc, out)
        rc, out = guest("for f in %s; do sha256sum \"$f\" 2>/dev/null || true; done" %
                        " ".join(PERSONAL))
        personal_before = dict((line.split(None, 1)[1], line.split(None, 1)[0])
                               for line in out.splitlines() if "  " in line)
        record("C07", "baseline", "capture personal-file hashes", rc, out)
        rc, out = guest("cd %s && bash install.sh %s/%s %s/state1" %
                        (GDIR, GDIR, Path(BUNDLE_ARCHIVE).name, GDIR), timeout=600)
        record("I01", "install", "exact shipped install.sh on fresh host", rc, out,
               contains=("INSTALL_PASS",))
        rc, out = guest("cd %s && bash verify.sh %s/state1" % (GDIR, GDIR), timeout=600)
        record("I02", "install", "exact shipped verify.sh after install", rc, out,
               contains=("VERIFY_PASS", "METADATA_IDENTITY_OK"))
        rc, out = guest("kpackagetool6 --type Plasma/Applet --list 2>/dev/null "
                        "| grep -Fxq %s && echo PACKAGE_PRESENT" % PACKAGE_ID)
        record("I03", "install", "package listed after install", rc, out,
               contains=("PACKAGE_PRESENT",))
        rc, out = guest("sha256sum %s | awk '{print $1}'" % CFG)
        after_install = clean(out).splitlines()[-1] if out.strip() else ""
        record("I04", "install", "install changes Plasma config (wallpaper key)", rc, out,
               extra={"changed": after_install != baseline, "baseline": baseline,
                      "after_install": after_install})
        rc, out = guest("cd %s && bash install.sh %s/%s %s/state2" %
                        (GDIR, GDIR, Path(BUNDLE_ARCHIVE).name, GDIR), timeout=600)
        record("U01", "upgrade", "second install of same archive uses shipped --upgrade path",
               rc, out, contains=("INSTALL_PASS",))
        rc, out = guest("cd %s && bash verify.sh %s/state2" % (GDIR, GDIR), timeout=600)
        record("U02", "upgrade", "verify after in-place upgrade", rc, out,
               contains=("VERIFY_PASS", "METADATA_IDENTITY_OK"))
        rc, out = guest("cd %s && bash uninstall.sh %s/state1" % (GDIR, GDIR), timeout=600)
        record("R01", "rollback", "exact shipped uninstall.sh restores install-time snapshot",
               rc, out, contains=("UNINSTALL_PASS",))
        rc, out = guest("kpackagetool6 --type Plasma/Applet --list 2>/dev/null "
                        "| grep -Fxq %s && echo PACKAGE_PRESENT || echo PACKAGE_ABSENT" % PACKAGE_ID)
        record("R02", "rollback", "package absent after uninstall", rc, out,
               contains=("PACKAGE_ABSENT",), forbids=("PACKAGE_PRESENT",))
        rc, out = guest("sha256sum %s | awk '{print $1}'" % CFG)
        after_rollback = clean(out).splitlines()[-1] if out.strip() else ""
        record("R03", "rollback", "config byte-for-byte restored to baseline",
               0 if after_rollback == baseline else 1,
               "%s\nbaseline=%s" % (after_rollback, baseline),
               extra={"baseline": baseline, "after_rollback": after_rollback})
        rc, out = guest("for f in %s; do sha256sum \"$f\" 2>/dev/null || true; done" %
                        " ".join(PERSONAL))
        personal_after = dict((line.split(None, 1)[1], line.split(None, 1)[0])
                              for line in out.splitlines() if "  " in line)
        equal = personal_before == personal_after and len(personal_before) >= 5
        record("R04", "rollback", "personal files unchanged", 0 if equal else 1,
               json.dumps({"before": personal_before, "after": personal_after},
                          sort_keys=True), extra={"equal": equal})
        rc, out = guest("cd %s && bash install.sh %s/%s %s/state3" %
                        (GDIR, GDIR, Path(BUNDLE_ARCHIVE).name, GDIR), timeout=600)
        record("I05", "reinstall", "reinstall exact pinned archive after rollback", rc, out,
               contains=("INSTALL_PASS",))
        rc, out = guest("cd %s && bash verify.sh %s/state3" % (GDIR, GDIR), timeout=600)
        record("I06", "reinstall", "verify after reinstall", rc, out,
               contains=("VERIFY_PASS", "METADATA_IDENTITY_OK"))
        rc, out = guest("cd %s && bash uninstall.sh %s/state3" % (GDIR, GDIR), timeout=600)
        record("R05", "cleanup", "final uninstall restores guest baseline", rc, out,
               contains=("UNINSTALL_PASS",))
        rc, out = guest("kpackagetool6 --type Plasma/Applet --list 2>/dev/null "
                        "| grep -Fxq %s && echo PACKAGE_PRESENT || echo PACKAGE_ABSENT" % PACKAGE_ID)
        record("R06", "cleanup", "guest package absent at end", rc, out,
               contains=("PACKAGE_ABSENT",), forbids=("PACKAGE_PRESENT",))
        rc, out = guest("sha256sum %s | awk '{print $1}'" % CFG)
        final_cfg = clean(out).splitlines()[-1] if out.strip() else ""
        record("R07", "cleanup", "guest config hash equals captured baseline",
               0 if final_cfg == baseline else 1, "%s\nbaseline=%s" % (final_cfg, baseline))

    passed = sum(1 for row in ledger if row["result"] == "PASS")
    proof = {
        "schema": "canopy.native.dev_artifact.shipped_rollback_proof/1",
        "verdict": "PASS" if passed == len(ledger) else "FAIL",
        "evidence_class": "REAL_GUEST_SCOPED",
        "scope": "DEVELOPMENT_ARTIFACT_ONLY;NO_RELEASE;NO_VISUAL_ACCEPTANCE;NO_CI_CLAIM",
        "generated_utc": wallclock(),
        "vm": "Canopy-Test-Plasma6",
        "artifact_sha256": artifact_sha,
        "shipped_hashes": hashes,
        "inner_sums_sha256": inner_sums_sha,
        "ledger": ledger,
        "ledger_steps": len(ledger),
        "pass_steps": passed,
        "owner_directive_sha_prefix": "1fba4b1e",
        "prior_67_step_rollback_proof": "SUPERSEDED_POINT_IN_TIME: different script/binary identity; not proof of this bundle",
        "notes": [
            "Exact scripts/binary were extracted from the committed artifact, not rebuilt or substituted.",
            "In-place --upgrade is exercised for the same package id; rollback still starts with uninstall.",
            "Visual acceptance, CI-on-guest automation, approval, merge and release: NOT_RUN.",
        ],
    }
    PROOF.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n",
                     encoding="utf-8", newline="\n")
    print("SHIPPED_PROOF_%s: %d/%d steps sha=%s" %
          (proof["verdict"], passed, len(ledger), artifact_sha))
    return 0 if proof["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
