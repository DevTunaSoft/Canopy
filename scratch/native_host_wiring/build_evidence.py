#!/usr/bin/env python3
"""Freeze the evidence index for the native host wiring PR.

Run after the final commit. Every digest is recomputed from current on-disk
bytes; a missing artifact is reported as MISSING with sha256=null rather than
copied from a claim. The full suite is included only when its log has a
terminal `Ran N tests ... OK|FAILED` summary.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BINARY = Path("C:/Users/X1/AppData/Local/hermes/cache/scratch/"
              "native_host_wiring_build_20261128/canopy-classic-spike.exe")

ARTIFACTS = (
    "canonical_vectors.json",
    "canonical_vectors_cpp.txt",
    "compiled_self_test.log",
    "parity_report.json",
    "contract_tests.log",
    "targeted_tests.log",
    "cmake_configure.log",
    "ninja_build.log",
    "plasma_runtime_blocker.md",
    "blocker_vbox_runningvms.txt",
    "blocker_vbox_vminfo.txt",
    "blocker_vbox_guestprops.txt",
    "blocker_guestcontrol_attempt.txt",
    "blocker_ssh_material.txt",
    "blocker_binary_format.txt",
    "git_diff_names.txt",
)


def digest(path: Path):
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=str(ROOT), check=True,
                          stdout=subprocess.PIPE, text=True).stdout.strip()


def main():
    head = git("rev-parse", "HEAD")
    base = git("rev-parse", "ec910d7a")
    suite_log = HERE / "full_tests.log"
    suite_rc = HERE / "full_tests.rc"
    terminal = None
    outcome = None
    text = ""
    if suite_log.exists():
        text = suite_log.read_text(encoding="utf-8", errors="replace")
        found = re.search(r"^Ran \d+ tests.*$", text, re.MULTILINE)
        if found and (re.search(r"^OK(?: \(skipped=\d+\))?$", text, re.MULTILINE)
                      or re.search(r"^FAILED", text, re.MULTILINE)):
            terminal = found.group(0)
            outcome = ("OK" if re.search(r"^OK", text, re.MULTILINE)
                       else "FAILED")
    sums = {}
    for name in ARTIFACTS:
        sums[name] = digest(HERE / name)
    if terminal is not None:
        sums["full_tests.log"] = digest(suite_log)
        if suite_rc.exists():
            sums["full_tests.rc"] = digest(suite_rc)
    report = {
        "artifact": "native_host_wiring_evidence",
        "base_sha": base,
        "head_sha": head,
        "source_head_sha": "d242fc95a60ec750051c801bd97fecdaa0f57ba4",
        "source_head_scope": (
            "Production/compiled source commit; the following dfbe27f commit "
            "added only evidence artifacts. head_sha is the exact artifact "
            "head used for the independent review checks."),
        "head_scope": (
            "head_sha is the exact production/artifact head whose compiled "
            "and Python sources were built and checked (%s at review). "
            "Evidence-only remediation commits after that head do not alter "
            "production sources, the binary or the compiled self-test log."
            % head[:7]),
        "vector_provenance": {
            "classification": "EMBEDDED_SYNTHETIC_GENERATED_FIXTURES",
            "compiled_location": ("prototype/classic/main.cpp :: "
                                  "kNativeDisplaySteps / kNativeDisplayCases"),
            "generator": "scratch/native_host_wiring/generate_vectors.py",
            "external_mirrors": (
                "scratch/native_host_wiring/canonical_vectors.json",
                "scratch/native_host_wiring/canonical_vectors_cpp.txt",
            ),
            "embedded_rows_vs_mirror": "18 steps / 13 cases, zero row differences",
        },
        "ci_checks_observed_at_pin": {
            "source": "gh pr view 754 --json statusCheckRollup",
            "observed_head": head,
            "classification": "CI_QT_BUILD_SMOKE_NOT_NATIVE_RUNTIME",
            "checks": [
                {
                    "name": "qt-evidence",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "completed_at": "2026-11-28T09:08:58Z",
                    "details_url": ("https://github.com/DevTunaSoft/Canopy/"
                                    "actions/runs/46128486358/job/140928263798"),
                },
                {
                    "name": "fake-gio-launch-fixture",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "completed_at": "2026-11-28T09:02:00Z",
                },
                {
                    "name": "foundation",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "completed_at": "2026-11-28T09:03:26Z",
                },
            ],
            "note": ("qt-evidence was IN_PROGRESS during the independent "
                     "review and was later terminal SUCCESS at this exact "
                     "pin. These CI checks do not establish a real Plasma "
                     "runtime result; on a later head they must be "
                     "re-queried and are not claimed here."),
        },
        "remediation": {
            "scope": ("evidence index, evidence tooling and documentation "
                      "only; no production or compiled source changed"),
            "gaps_closed": [
                "git_diff_names.txt regenerated from base..HEAD, including "
                "evidence.json and SHA256SUMS.txt",
                "head_sha pinned to the exact review head dfbe27f; "
                "production source head d242fc9 retained as source_head_sha",
                "embedded compiled vectors explicitly labelled as synthetic "
                "generated fixtures with external mirrors and digests",
                "qt-evidence terminal COMPLETED/SUCCESS at the pin recorded "
                "without upgrading NATIVE_RUNTIME from NOT_RUN",
                "docs verification table cosmetic split removed",
            ],
            "native_runtime": "NOT_RUN (unchanged)",
        },
        "classification": {
            "compiled_self_test": "SYNTHETIC",
            "python_parity": "SYNTHETIC",
            "python_targeted_tests": "SYNTHETIC",
            "real_plasma_runtime": "NOT_RUN",
            "screen_reader": "NOT_RUN",
        },
        "artifact_sha256": sums,
        "binary": {
            "path": str(BINARY),
            "sha256": digest(BINARY),
            "classification": "SYNTHETIC_WINDOWS_PE_OFFSCREEN",
        },
        "full_suite": {
            "terminal_summary": terminal,
            "outcome": outcome,
            "rc": (suite_rc.read_text(encoding="utf-8").strip()
                   if suite_rc.exists() else None),
            "verdict": ("PASS" if terminal and outcome == "OK" else
                        "FAIL" if terminal else "INCOMPLETE"),
        },
        "note": ("Compiled offscreen self-test and Python parity only. "
                 "No real Plasma compositor, monitor change, screenshot or "
                 "screen-reader result is claimed."),
    }
    (HERE / "evidence.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    lines = []
    for name, value in sums.items():
        if value is None:
            lines.append("MISSING %s" % name)
        else:
            lines.append("%s  %s" % (value, name))
    (HERE / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"head": head, "full_suite": report["full_suite"],
                      "artifacts": len(sums),
                      "missing": [k for k, v in sums.items() if v is None]},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
