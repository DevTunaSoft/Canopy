"""Derive the M4 runtime verdict from frozen probe artifacts only.

No host, guest or network call is made here. Every fact is recomputed from the
JSONL probe log, observation text and PNG bytes in ``evidence/``; the verdict
itself is produced by the product contract ``runtime_outcome``.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from canopy_features.reliability.suspend_resume_native import (  # noqa: E402
    EVIDENCE_LABELS, OUTCOMES, runtime_outcome)

EVIDENCE = HERE / "evidence"
LOG = EVIDENCE / "probe.jsonl"
DIRECTIVE_SHA = (
    "79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_entries():
    return [json.loads(line) for line in
            LOG.read_text(encoding="utf-8").splitlines() if line.strip()]


def field(pattern, text):
    match = re.search(pattern, text, re.M)
    if match is None:
        raise AssertionError("missing observed field: " + pattern)
    return match.group(1)


def main():
    entries = load_entries()
    before_text = (EVIDENCE / "before_observe.txt").read_text(encoding="utf-8")
    after_text = (EVIDENCE / "after_observe.txt").read_text(encoding="utf-8")
    review = json.loads((EVIDENCE / "visual_review.json").read_text(
        encoding="utf-8"))

    before_png = digest(EVIDENCE / "before.png")
    during_png = digest(EVIDENCE / "suspended.png")
    after_png = digest(EVIDENCE / "after.png")
    assert before_png == review["before"]["sha256"]
    assert during_png == review["suspended"]["sha256"]
    assert after_png == review["after"]["sha256"]
    assert before_png == during_png == after_png, "framebuffer changed"

    before_uptime = float(field(r"^UPTIME=([0-9.]+)", before_text))
    after_uptime = float(field(r"^UPTIME=([0-9.]+)", after_text))
    before_shell = field(r"^(\d+) /usr/bin/plasmashell", before_text)
    after_shell = field(r"^(\d+) /usr/bin/plasmashell", after_text)
    before_kwin = field(r"^(\d+) /usr/bin/kwin_x11", before_text)
    after_kwin = field(r"^(\d+) /usr/bin/kwin_x11", after_text)
    assert before_shell == after_shell and before_kwin == after_kwin
    assert after_uptime >= before_uptime
    assert re.search(r"^Active=yes$", before_text, re.M)
    assert re.search(r"^Active=yes$", after_text, re.M)
    assert re.search(r"^State=active$", before_text, re.M)
    assert re.search(r"^State=active$", after_text, re.M)
    assert field(r"^WMCTRL_RC=(\d+)", before_text) == "124"
    assert field(r"^WMCTRL_RC=(\d+)", after_text) == "124"

    launch = [e for e in entries if e.get("label") == "guest-suspend-launch"]
    assert len(launch) == 1 and launch[0]["rc"] == 0
    assert "M4_SUSPEND_LAUNCHED" in launch[0]["stdout"]
    unreachable = [e for e in entries if e.get("label") == "reachability"
                   and e["rc"] == 255
                   and "banner exchange" in e["stderr"]]
    assert len(unreachable) >= 2, "guest did not stop answering during suspend"
    wake = [e for e in entries if e.get("label") == "host-acpi-wake"]
    assert len(wake) == 1 and wake[0]["rc"] == 0
    recovered = [e for e in entries if e.get("label") == "after-wake"
                 and e["result"] == "REACHABLE"]
    assert recovered, "guest did not answer after ACPI wake"
    assert recovered[0]["attempt"] == 1

    observation = {
        "evidence_label": "NATIVE RUNTIME",
        "before": {
            "shell_active": True,
            "dock_visible": review["before"]["dock_visible"],
            "launcher_visible": review["before"]["launcher_visible"],
            "window_visible": review["before"]["window_visible"],
        },
        "during": {
            "shell_active": None,
            "suspend_confirmed": True,
        },
        "after": {
            "shell_active": True,
            "dock_visible": review["after"]["dock_visible"],
            "launcher_visible": review["after"]["launcher_visible"],
            "window_visible": review["after"]["window_visible"],
            "resume_confirmed": True,
        },
    }
    outcome = runtime_outcome(observation)
    assert outcome.evidence_label in EVIDENCE_LABELS
    assert outcome.outcome in OUTCOMES

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                          stdout=subprocess.PIPE, check=True)
    report = {
        "directive_sha256": DIRECTIVE_SHA,
        "worktree_head_at_generation": head.stdout.decode().strip(),
        "guest": "Canopy-Test-Plasma6",
        "session": "65 (x11, active, unlocked before and after)",
        "evidence_labels": ["NATIVE RUNTIME", "SYNTHETIC", "NOT RUN"],
        "artifacts": {
            "probe.jsonl": {"sha256": digest(LOG), "label": "NATIVE RUNTIME"},
            "before.png": {"sha256": before_png, "label": "NATIVE RUNTIME"},
            "suspended.png": {"sha256": during_png, "label": "NATIVE RUNTIME"},
            "after.png": {"sha256": after_png, "label": "NATIVE RUNTIME"},
            "before_observe.txt": {
                "sha256": digest(EVIDENCE / "before_observe.txt"),
                "label": "NATIVE RUNTIME"},
            "after_observe.txt": {
                "sha256": digest(EVIDENCE / "after_observe.txt"),
                "label": "NATIVE RUNTIME"},
            "visual_review.json": {
                "sha256": digest(EVIDENCE / "visual_review.json"),
                "label": "NATIVE RUNTIME"},
        },
        "observed": {
            "before_uptime_seconds": before_uptime,
            "after_uptime_seconds": after_uptime,
            "plasmashell_pid": before_shell,
            "kwin_pid": before_kwin,
            "suspend_launch_rc": launch[0]["rc"],
            "suspend_unreachable_probes": len(unreachable),
            "suspend_blocker": "Connection timed out during banner exchange",
            "wake_rc": wake[0]["rc"],
            "wake_method": "host VBoxManage controlvm acpipowerbutton",
            "resume_probe_attempt": recovered[0]["attempt"],
            "wmctrl_rc_before_and_after": 124,
        },
        "observation": observation,
        "outcome": outcome.to_dict(),
        "sub_outcomes": {
            "guest_suspend_and_session_recovery": {
                "label": "NATIVE RUNTIME", "outcome": "PASS",
                "reason": "guest stopped answering SSH, resumed on first ACPI "
                          "wake with unchanged plasmashell/kwin PIDs, active "
                          "unlocked session and continuous uptime"},
            "dock_launcher_window_fresh_render_after_resume": {
                "label": "NATIVE RUNTIME", "outcome": "NOT RUN",
                "reason": "guest X clients fail before and after suspend "
                          "(wmctrl/xdpyinfo rc=124); post-resume PNG is "
                          "byte-identical to the pre-suspend frozen frame"},
        },
        "not_run": [
            "fresh post-resume dock/launcher/window X-client enumeration",
            "screen-reader and AT-SPI behavior",
            "multi-monitor and HiDPI suspend/resume",
            "real PSS/CPU measurement across suspend/resume",
            "owner final visual acceptance",
        ],
        "no_claim": ["release readiness", "merge authorization",
                     "self-approval", "compiled-shell wiring"],
    }
    path = EVIDENCE / "runtime_verdicts.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    print(json.dumps(outcome.to_dict(), sort_keys=True))
    print("SHA256 " + digest(path) + "  " + str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
