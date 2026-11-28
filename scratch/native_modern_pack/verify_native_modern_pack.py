#!/usr/bin/env python3
"""Synthetic verification for the bounded first-party Modern Shell Pack.

Runs metadata-only checks and a pure switch-ledger smoke test. It does not
start a shell, touch a compositor, read Classic assets, write settings or
perform any network I/O. Results are labelled SYNTHETIC; real runtime work is
reported as NOT_RUN.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve()
SCRATCH = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from canopy_features.settings import shell_pack_manifest as m  # noqa: E402
from tools.check_shell_pack import PackValidationError, validate_pack  # noqa: E402

PACK = ROOT / "tools/shell_packs/modern"
REPORT = SCRATCH / "synthetic_verification.json"
SUMS = SCRATCH / "SHA256SUMS.txt"
BASE = "ec910d7a"
OWNED = (
    "tools/shell_packs/modern/",
    "docs/NATIVE_MODERN_PACK.md",
    "scratch/native_modern_pack/",
    "canopy_features/settings/shell_pack_manifest.py",
)

results = {}


def record(name, fn):
    try:
        value = fn()
        results[name] = {"status": "PASS", "detail": value}
    except Exception as exc:  # fail closed and keep the evidence
        results[name] = {"status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}


def check_manifest():
    descriptor = validate_pack(PACK)
    assert descriptor["id"] == m.MODERN_MANIFEST_ID, descriptor["id"]
    assert descriptor["permissions"] == []
    assert descriptor["kind"] == "presentation"
    assert descriptor["switch_strategy"] == "same-session"
    cli = subprocess.run(
        [sys.executable, str(ROOT / "tools/check_shell_pack.py"), str(PACK)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert cli.returncode == 0, cli.stderr.strip()
    assert "SHELL_PACK_MANIFEST_PASS" in cli.stdout, cli.stdout
    return {"id": descriptor["id"], "cli": cli.stdout.strip()}


def check_inventory():
    snap = m.inventory_snapshot()
    assert not snap.problems, snap.problems
    assert tuple(d.builtin_id for d in snap.definitions) == (
        m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID,
    )
    modern = snap.get(m.MODERN_BUILTIN_ID)
    classic = snap.get(m.CLASSIC_BUILTIN_ID)
    assert modern is not None and modern.manifest_id == m.MODERN_MANIFEST_ID
    assert classic is not None and classic.source == "built-in:approved-classic"
    assert all(d.free and d.tier == m.INCLUDED_TIER for d in snap.definitions)
    assert m.PAID_TIERS == frozenset()
    assert m.ACTIVATION_REQUIRED is False
    assert m.TELEMETRY_ENDPOINTS == frozenset()
    assert all(d.owned_services == frozenset() for d in snap.definitions)
    assert modern.capabilities <= frozenset(
        json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))["capabilities"]
    )
    services = m.shared_core_snapshot()
    assert len(services) == len(m.SHARED_CORE_SERVICES)
    assert all(v == "host-owned" for v in services.values())
    return snap.as_dict()


def check_healthy_path():
    snap = m.inventory_snapshot()
    prepared = m.prepare_switch(snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID)
    assert prepared.phase == "PREPARED"
    assert prepared.active_id == m.CLASSIC_BUILTIN_ID
    assert prepared.committed_id == m.CLASSIC_BUILTIN_ID
    applied = m.apply_switch(prepared)
    assert applied.phase == "APPLIED" and applied.active_id == m.MODERN_BUILTIN_ID
    committed = m.verify_switch(applied, True)
    assert committed.phase == "COMMITTED"
    assert committed.committed_id == m.MODERN_BUILTIN_ID
    released = m.release_inactive(committed)
    assert released.phase == "RELEASED" and not released.rolled_back
    return released.as_dict()


def check_failure_rollback():
    snap = m.inventory_snapshot()
    applied = m.apply_switch(
        m.prepare_switch(snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID)
    )
    rolled = m.verify_switch(applied, False)
    assert rolled.phase == "ROLLED_BACK" and rolled.rolled_back is True
    assert rolled.active_id == m.CLASSIC_BUILTIN_ID
    assert rolled.committed_id == m.CLASSIC_BUILTIN_ID
    explicit = m.rollback_switch(applied, "candidate unhealthy")
    assert explicit.phase == "ROLLED_BACK" and explicit.active_id == m.CLASSIC_BUILTIN_ID
    return {"verified_failure": rolled.as_dict(), "explicit_rollback": explicit.as_dict()}


def check_negative_controls():
    snap = m.inventory_snapshot()
    rejected = []
    for fn in (
        lambda: m.prepare_switch(snap, "org.canopy.heritage", m.MODERN_BUILTIN_ID),
        lambda: m.prepare_switch(snap, m.CLASSIC_BUILTIN_ID, "../escape"),
        lambda: m.verify_switch(
            m.apply_switch(
                m.prepare_switch(snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID)
            ), "yes",
        ),
        lambda: m.rollback_switch(
            m.verify_switch(
                m.apply_switch(
                    m.prepare_switch(snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID)
                ), True,
            )
        ),
    ):
        try:
            fn()
        except m.ShellPackManifestError:
            rejected.append(True)
        else:
            raise AssertionError("a hostile or illegal transition was accepted")
    assert len(rejected) == 4
    return {"illegal_transitions_rejected": len(rejected)}


def check_scope_and_classic_preservation():
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert status.returncode == 0, status.stderr.strip()
    changed = []
    for line in status.stdout.splitlines():
        path = line[3:].strip().split(" -> ")[-1]
        changed.append(path)
    alien = sorted(p for p in changed if not p.startswith(OWNED))
    assert not alien, f"changes outside owned paths: {alien}"
    classic_diff = subprocess.run(
        ["git", "diff", "--name-only", BASE, "--", "prototype/classic",
         "docs/CLASSIC*", "canopy_features/settings/persisted_preferences.py"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert classic_diff.returncode == 0, classic_diff.stderr.strip()
    assert not classic_diff.stdout.strip(), classic_diff.stdout
    return {"changed_paths": sorted(changed), "classic_paths_changed": 0}


def check_no_paid_or_runtime_hooks():
    manifest_text = (PACK / "manifest.json").read_text(encoding="utf-8")
    banned = ("paid", "purchase", "subscription", "activation", "unlock",
              "telemetry", "http://", "https://", "dbus", "daemon")
    lowered = manifest_text.lower()
    hits = [token for token in banned if token in lowered]
    assert not hits, hits
    qml = (PACK / "ui/Main.qml").read_text(encoding="utf-8")
    code = "\n".join(line for line in qml.splitlines()
                     if not line.lstrip().startswith("//"))
    for token in ("Timer", "NetworkRequest", "createQmlObject", "Process",
                  "DBus", "Qt.createComponent", "WebSocket"):
        assert token not in code, token
    return {"manifest_banned_tokens": [], "qml_runtime_hooks": []}


for label, fn in (
    ("manifest_passes_offline_checker", check_manifest),
    ("first_party_inventory", check_inventory),
    ("prepare_apply_verify_release", check_healthy_path),
    ("failed_verify_rollback", check_failure_rollback),
    ("illegal_transition_negative_controls", check_negative_controls),
    ("owned_paths_and_classic_preserved", check_scope_and_classic_preservation),
    ("no_paid_tiers_activation_telemetry_or_runtime_hooks", check_no_paid_or_runtime_hooks),
):
    record(label, fn)

verdict = "PASS" if all(v["status"] == "PASS" for v in results.values()) else "FAIL"
head = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
    capture_output=True, text=True, timeout=60,
).stdout.strip()
report = {
    "label": "SYNTHETIC",
    "task": "M3 Shell Pack Modern",
    "base_sha": BASE,
    "head_sha": head,
    "checks": results,
    "verdict": verdict,
    "not_run": [
        "native Plasma/KWin session switch",
        "live Classic-to-Modern switch preserving running applications",
        "compiled Qt/QML rendering and owner visual acceptance",
        "real PSS/CPU/GPU measurement",
        "screen-reader and real desktop keyboard verification",
        "install, rollback and upgrade on a disposable guest",
    ],
    "resource_impact": {
        "measured": "SYNTHETIC: metadata-only validation and immutable ledger transitions",
        "not_measured": "NOT_RUN: native runtime PSS, CPU, GPU, wakeups and frame times",
        "rationale": "No process, service, timer, compositor change or UI code is added or executed.",
    },
}
REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
SUMS.write_bytes(
    (hashlib.sha256(REPORT.read_bytes()).hexdigest()
     + "  synthetic_verification.json\n").encode("ascii")
)
print(json.dumps({"verdict": verdict, "checks": {
    k: v["status"] for k, v in results.items()}}, indent=2))
raise SystemExit(0 if verdict == "PASS" else 1)
