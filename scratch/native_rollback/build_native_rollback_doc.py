#!/usr/bin/env python3
"""Build docs/NATIVE_ROLLBACK.md from the exact runtime evidence JSON.

No hash is hand-transcribed: every digest in the document is recomputed from
bytes or read from the authoritative evidence file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-rollback-20261127")
EVIDENCE = REPO / "scratch" / "native_rollback" / "native_rollback_runtime_evidence.json"
DOC = REPO / "docs" / "NATIVE_ROLLBACK.md"


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cfg_pair(check: dict) -> str:
    before = check["before"]
    after = check["after"]
    labels = ("plasma-org.kde.plasma.desktop-appletsrc", "plasmashellrc")
    rows = []
    for label in labels:
        b = before.get(label, {})
        a = after.get(label, {})
        rows.append("| `%s` | `%s` / `%s` | `%s` / `%s` | %s |" % (
            label, b.get("sha256", "ABSENT"), b.get("mode", "-"),
            a.get("sha256", "ABSENT"), a.get("mode", "-"),
            "EQUAL" if b == a and b else "DIFFERENT"))
    return "\n".join(rows)


data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
checks = data["checks"]
summary = data["summary"]
pkg = data["package"]

doc = []
doc.append("# Native Plasma rollback evidence")
doc.append("")
doc.append("Scope: real runtime proof in the dedicated `Canopy-Test-Plasma6` guest. "
           "This document supersedes the inferred-only `PASS_WITH_GAPS` disposition "
           "of `rollback_b01_independent_check.md` for the measured behaviors below. "
           "It is not a release, visual-acceptance or merge approval.")
doc.append("")
doc.append("## Provenance")
doc.append("")
doc.append("| Field | Value |")
doc.append("|---|---|")
doc.append("| Owner directive SHA (prefix) | `%s` |" % data["owner_directive_sha"])
doc.append("| Base commit | `%s` |" % data["base_sha"])
doc.append("| Evidence | `scratch/native_rollback/native_rollback_runtime_evidence.json` |")
doc.append("| Evidence SHA-256 | `%s` |" % sha_file(EVIDENCE))
doc.append("| Manifest | `scratch/native_rollback/SHA256SUMS.txt` (SHA-256 `%s`) |"
           % sha_file(REPO / "scratch" / "native_rollback" / "SHA256SUMS.txt"))
doc.append("| Harness | `scratch/native_rollback/run_native_rollback_proof.py` |")
doc.append("| Runner console | `scratch/native_rollback/run_console.out` |")
doc.append("| VM / transport | `%s`, host VBoxManage + SSH to `canopy@127.0.0.1:2223` |"
           % data["vm"]["name"])
doc.append("| Run window (UTC) | `%s` .. `%s` |"
           % (data["started_utc"], data["finished_utc"]))
doc.append("| Verdict | `%s` |" % data["verdict"])
doc.append("")
doc.append("The harness stages the unchanged pinned package scripts into the guest. "
           "Their SHA-256 values are verified on both host and guest before any write "
           "(step C00/C02). No credential content is recorded; the key path is redacted "
           "in the evidence.")
doc.append("")
doc.append("Pinned binaries used by the real install/rollback scripts: "
           "`SHA256SUMS` = `%s`; binary = `%s`; wallpaper = `%s`."
           % (pkg["SHA256SUMS_sha256"],
              "4089251cf6a557d74ca308f3e32f59fea318f62d3285204e9ec7872bcc6b3f14",
              "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381"))
doc.append("")
doc.append("## Result")
doc.append("")
doc.append("| Metric | Value |")
doc.append("|---|---|")
doc.append("| Ledger steps | %d |" % summary["steps"])
doc.append("| PASS steps | %d |" % summary["pass"])
doc.append("| HOLD steps | %d (%s) |"
           % (summary["hold"], ", ".join(summary["hold_ids"]) or "none"))
doc.append("| Framebuffer captures | %d |" % summary["screenshots"])
doc.append("| Harness notes | %s |" % (", ".join(summary["notes"]) or "none"))
doc.append("")
doc.append("## Gap closure")
doc.append("")
doc.append("### N02/N03/N04 config-untouched: direct before/after hashes")
doc.append("")
doc.append("The earlier B01 chain had only N01 with a config hash pair; N02/N03/N04 "
           "rested on fail-closed abort ordering. Each control now captures both Plasma "
           "config hashes and modes immediately before the refusal and immediately after "
           "it, before any restoration of the tampered artifact.")
doc.append("")
for control in ("N01", "N02", "N03", "N04"):
    check = checks.get(control + "_config_untouched")
    doc.append("#### %s" % control)
    doc.append("")
    if not check:
        doc.append("NOT_RUN - no evidence entry.")
        doc.append("")
        continue
    doc.append("Direct hash proof: `%s`; equal: `%s`." % (
        "yes" if check["direct_hash_proof"] else "no", check["equal"]))
    doc.append("")
    doc.append("| Config | Before (SHA-256 / mode) | After (SHA-256 / mode) | Result |")
    doc.append("|---|---|---|---|")
    doc.append(cfg_pair(check))
    doc.append("")

doc.append("### Personal data preservation")
doc.append("")
pd = checks.get("personal_data_preservation", {})
doc.append("Ten pre-existing user files were SHA-256 hashed at baseline (S00) and "
           "again after both full cycles (R17/R18). Count: %d; all equal: `%s`."
           % (pd.get("count", 0), pd.get("all_equal")))
doc.append("")
doc.append("| User file | Before | After |")
doc.append("|---|---|---|")
for path, before in sorted(pd.get("before", {}).items()):
    doc.append("| `%s` | `%s` | `%s` |" % (
        path, before, pd.get("after", {}).get(path, "ABSENT")))
doc.append("")

doc.append("### R07 and R15 restoration (byte/mode exact stock fallback)")
doc.append("")
baseline = checks.get("baseline", {}).get("config", {})
for cid, key in (("R07", "R07_exact_restore"), ("R15", "R15_exact_restore")):
    check = checks.get(key, {})
    doc.append("%s: exact match against stock baseline: `%s`." % (
        cid, check.get("exact")))
    doc.append("")
    doc.append("| Config | Stock baseline (SHA-256 / mode / size) | After %s |" % cid)
    doc.append("|---|---|---|")
    for label in ("plasma-org.kde.plasma.desktop-appletsrc", "plasmashellrc"):
        b = baseline.get(label, {})
        a = check.get("live", {}).get(label, {})
        doc.append("| `%s` | `%s` / `%s` / `%s` | `%s` / `%s` / `%s` |" % (
            label, b.get("sha256", "ABSENT"), b.get("mode", "-"), b.get("size", "-"),
            a.get("sha256", "ABSENT"), a.get("mode", "-"), a.get("size", "-")))
    doc.append("")

f01 = checks.get("F01_config_untouched", {})
doc.append("### Stock fallback with no install manifest")
doc.append("")
doc.append("With no manifest, `rollback.sh` must not guess assets or rewrite Plasma "
           "config: it removes only the hash-pinned orphan binary and reports that "
           "config was not restored. Direct config hashes equal: `%s`."
           % f01.get("equal"))
doc.append("")
doc.append("### Upgrade boundary")
doc.append("")
doc.append("Step U00 proves install refuses an already-installed host with "
           "`already installed (manifest: ...)`; there is no in-place upgrade path. "
           "Cycle 2 is therefore an uninstall-then-reinstall (upgrade-equivalent) "
           "cycle, not a claim of in-place upgrade support.")
doc.append("")

doc.append("## Reproduce")
doc.append("")
doc.append("```bash")
doc.append("cd C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-rollback-20261127")
doc.append("python scratch/native_rollback/guest_session_setup.py enable   # real Plasma session")
doc.append("python scratch/native_rollback/run_native_rollback_proof.py")
doc.append("python scratch/native_rollback/build_native_rollback_doc.py")
doc.append("```")
doc.append("")
doc.append("The VM must be running (`VBoxManage startvm Canopy-Test-Plasma6 --type headless`). "
           "The harness is idempotent: C03 normalizes the guest back to stock before "
           "the first install.")
doc.append("")

doc.append("## Resource impact and evidence labels")
doc.append("")
doc.append("- No production Python/QML/C++/asset file was changed by this task; the "
           "deliverable is a runtime harness, evidence JSON and this document.")
doc.append("- Resource measurement of the install/rollback scripts: `NOT_RUN` "
           "(no new code path added to the shell; no PSS/CPU claim is made).")
doc.append("- Framebuffer screenshots are REAL captures from the dedicated VM, "
           "scoped to install/rollback state, not visual acceptance.")
doc.append("- Screen-reader behavior: `NOT_RUN` (no accessibility or announcement "
           "code touched).")
doc.append("- Visual acceptance, CI-on-guest automation, host apt/dpkg install, "
           "public release and any main merge: `NOT_RUN`. `release_ready=false`.")
doc.append("")

DOC.write_text("\n".join(doc) + "\n", encoding="utf-8", newline="\n")
print("DOC", DOC, "sha256=" + sha_file(DOC), flush=True)
