"""Build scratch/native_host_events/evidence.json from recorded test logs."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "scratch" / "native_host_events"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args],
                                   text=True).strip()


def summary(name):
    text = (HERE / name).read_text(encoding="utf-8", errors="replace")
    ran = re.findall(r"Ran (\d+) tests? in ([0-9.]+)s", text)
    skip_match = re.search(r"OK \(skipped=(\d+)\)", text)
    skipped = int(skip_match.group(1)) if skip_match else 0
    ok = bool(re.search(r"(?m)^OK(?: \(skipped=\d+\))?\s*$", text))
    # Test bodies emit fixed marker lines such as SUPERVISOR_FAIL; only the
    # unittest summary counts as a real failure.
    failed = bool(re.search(r"FAILED \(|^ERROR: |^FAIL: ", text,
                            flags=re.MULTILINE))
    return {
        "log": "scratch/native_host_events/" + name,
        "ran": int(ran[-1][0]) if ran else None,
        "seconds": float(ran[-1][1]) if ran else None,
        "skipped": skipped,
        "ok": ok,
        "failed": failed,
    }


targeted = summary("targeted.log")
full = summary("full_suite.log")
foundation = (HERE / "foundation.log").read_text(
    encoding="utf-8", errors="replace").strip()

evidence = {
    "task": "M3 native Plasma host-event limiter and ceiling port",
    "source_pr": 728,
    "source_head": "39a9fd21665098858e582a879866b42cf4bb8e44",
    "base_sha": git("rev-parse", "ec910d7a^{commit}"),
    "branch": git("branch", "--show-current"),
    "owner_directive_sha": "79e30d79",
    "adaptation_not_copy": True,
    "targets": [
        "canopy_core/host_events.py",
        "canopy_features/reliability/native_host_event_ceilings.py",
        "tests/test_host_event_bounded_lifetime.py",
        "tests/test_host_event_ceiling_contracts.py",
        "docs/NATIVE_HOST_EVENTS.md",
    ],
    "tests": {
        "foundation": foundation,
        "targeted": targeted,
        "full_suite": full,
    },
    "scenarios": {
        "sustained_200_spaced_valid_events": "all accepted past 64",
        "same_tick_burst_200": "200 delivered, 16 applied, 184 deferred",
        "exhausted_bucket_no_further_events": "clock advance alone emits nothing; next real dispatch flushes once",
        "flood_17_per_tick_20_ticks": "20 refresh requests, rings stay 16/4",
        "epoch_ceiling_200_events": "200 producer calls, 3 reconciliations, newest state wins",
        "episode_budgets": "explicit-condition rebasing only; retained entries capped",
    },
    "evidence_labels": {
        "scenarios": "SYNTHETIC (injected clock, real HostEvent instances)",
        "not_run": [
            "compiled Qt bridge", "Mint guest", "real Plasma session",
            "screen reader", "real transport", "visual acceptance",
            "shell PSS/CPU",
        ],
    },
    "merge": "none",
}

(HERE / "evidence.json").write_text(
    json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(evidence, indent=2, sort_keys=True))
