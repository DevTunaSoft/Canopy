#!/usr/bin/env python3
"""Synthetic verification for the eight initial first-party Shell Packs.

Metadata-only checks plus a bounded 100-round-trip immutable ledger smoke
test. This runs no shell, compositor, session, setting, network or Classic
asset access. Every result is SYNTHETIC; native/live switching is NOT_RUN.
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
from tools.check_shell_pack import (  # noqa: E402
    INITIAL_CATALOG,
    PackValidationError,
    validate_catalog,
    validate_pack,
)

CATALOG = ROOT / "tools" / "shell_packs"
REPORT = SCRATCH / "synthetic_verification.json"
SUMS = SCRATCH / "SHA256SUMS.txt"
BASE = "ec910d7a"
ROUND_TRIPS = 100
BANNED_MANIFEST = (
    "paid", "purchase", "subscription", "activation", "unlock", "telemetry",
    "http://", "https://", "dbus", "daemon",
)
QML_HOOKS = (
    "Timer", "NetworkRequest", "createQmlObject", "Process", "DBus",
    "Qt.createComponent", "WebSocket",
)
OWNED = (
    "tools/shell_packs/",
    "docs/NATIVE_MODERN_PACK.md",
    "scratch/native_modern_pack/",
    "canopy_features/settings/shell_pack_manifest.py",
    "tools/check_shell_pack.py",
    "tests/test_native_shell_packs_catalog.py",
)

results = {}


def record(name, fn):
    try:
        value = fn()
        results[name] = {"status": "PASS", "detail": value}
    except Exception as exc:  # fail closed and keep the evidence
        results[name] = {"status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}


def check_catalog_checker():
    descriptors = validate_catalog(CATALOG)
    ids = tuple(item["id"] for item in descriptors)
    assert ids == tuple(INITIAL_CATALOG[name] for name in sorted(INITIAL_CATALOG)), ids
    cli = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_shell_pack.py"),
         "--catalog", str(CATALOG)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert cli.returncode == 0, cli.stderr.strip()
    assert "SHELL_PACK_CATALOG_PASS: 7" in cli.stdout, cli.stdout
    return {"manifest_ids": list(ids), "cli": cli.stdout.strip()}


def check_inventory():
    snap = m.inventory_snapshot()
    assert not snap.problems, snap.problems
    assert tuple(item.builtin_id for item in snap.definitions) == m.INITIAL_PACK_IDS
    assert snap.checked_manifests == 7
    classic = snap.get(m.CLASSIC_BUILTIN_ID)
    assert classic is not None
    assert classic.manifest_id == m.CLASSIC_BUILTIN_ID
    assert classic.source == "built-in:approved-classic"
    assert classic.capabilities == frozenset()
    for builtin_id, manifest_id in m.CATALOG_IDS.items():
        item = snap.get(builtin_id)
        assert item is not None and item.manifest_id == manifest_id, builtin_id
        assert item.capabilities and item.capabilities <= frozenset(
            validate_pack(CATALOG / m.PACK_DIRS[builtin_id].name)["capabilities"]
        ), builtin_id
    assert all(item.free and item.tier == m.INCLUDED_TIER
               for item in snap.definitions)
    assert all(item.owned_services == frozenset() for item in snap.definitions)
    assert m.PAID_TIERS == frozenset()
    assert m.ACTIVATION_REQUIRED is False
    assert m.TELEMETRY_ENDPOINTS == frozenset()
    services = m.shared_core_snapshot()
    assert len(services) == len(m.SHARED_CORE_SERVICES)
    assert all(value == "host-owned" for value in services.values())
    return snap.as_dict()


def check_healthy_path():
    snap = m.inventory_snapshot()
    prepared = m.prepare_switch(
        snap, m.CLASSIC_BUILTIN_ID, m.HERITAGE_BUILTIN_ID
    )
    assert prepared.phase == "PREPARED"
    assert prepared.active_id == m.CLASSIC_BUILTIN_ID
    applied = m.apply_switch(prepared)
    assert applied.phase == "APPLIED" and applied.active_id == m.HERITAGE_BUILTIN_ID
    committed = m.verify_switch(applied, True)
    assert committed.committed_id == m.HERITAGE_BUILTIN_ID
    released = m.release_inactive(committed)
    assert released.phase == "RELEASED" and not released.rolled_back
    return released.as_dict()


def check_failure_rollback():
    snap = m.inventory_snapshot()
    applied = m.apply_switch(m.prepare_switch(
        snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID
    ))
    rolled = m.verify_switch(applied, False)
    assert rolled.phase == "ROLLED_BACK" and rolled.rolled_back is True
    assert rolled.active_id == m.CLASSIC_BUILTIN_ID
    explicit = m.rollback_switch(applied, "candidate unhealthy")
    assert explicit.phase == "ROLLED_BACK" and explicit.active_id == m.CLASSIC_BUILTIN_ID
    return {"verified_failure": rolled.as_dict(), "explicit_rollback": explicit.as_dict()}


def check_negative_controls():
    snap = m.inventory_snapshot()
    rejected = []
    for fn in (
        lambda: m.prepare_switch(snap, "org.canopy.unlisted", m.MODERN_BUILTIN_ID),
        lambda: m.prepare_switch(snap, m.CLASSIC_BUILTIN_ID, "../escape"),
        lambda: m.verify_switch(
            m.apply_switch(m.prepare_switch(
                snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID)), "yes"
        ),
        lambda: m.rollback_switch(m.verify_switch(
            m.apply_switch(m.prepare_switch(
                snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID)), True
        )),
        lambda: m.load_pack_definition(m.CLASSIC_BUILTIN_ID),
    ):
        try:
            fn()
        except m.ShellPackManifestError:
            rejected.append(True)
        else:
            raise AssertionError("a hostile or illegal transition was accepted")
    assert len(rejected) == 5
    return {"illegal_transitions_rejected": len(rejected)}


def check_hundred_round_trips():
    snap = m.inventory_snapshot()
    result = m.run_synthetic_round_trips(snap, ROUND_TRIPS)
    assert result["round_trips"] == 100
    assert result["transitions"] == 300
    assert result["pack_ids"] == list(m.INITIAL_PACK_IDS)
    assert len(result["sequence_sha256"]) == 64
    assert result["real_runtime_verified"] is False
    return result


def check_scope_and_classic_preservation():
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert status.returncode == 0, status.stderr.strip()
    changed = []
    for line in status.stdout.splitlines():
        changed.append(line[3:].strip().split(" -> ")[-1])
    alien = sorted(path for path in changed if not path.startswith(OWNED))
    assert not alien, f"changes outside owned paths: {alien}"
    classic_diff_status = "BASE_UNAVAILABLE"
    probe = subprocess.run(
        ["git", "cat-file", "-e", BASE + "^{commit}"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    if probe.returncode == 0:
        classic_diff = subprocess.run(
            ["git", "diff", "--name-only", BASE, "--", "prototype/classic",
             "docs/CLASSIC*", "canopy_features/settings/persisted_preferences.py"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        assert classic_diff.returncode == 0, classic_diff.stderr.strip()
        assert not classic_diff.stdout.strip(), classic_diff.stdout
        classic_diff_status = "EMPTY"
    return {
        "changed_paths": sorted(changed),
        "classic_paths_changed": 0,
        "classic_diff": classic_diff_status,
    }


def check_no_paid_or_runtime_hooks():
    for name in INITIAL_CATALOG:
        manifest_text = (CATALOG / name / "manifest.json").read_text(encoding="utf-8")
        hits = [token for token in BANNED_MANIFEST if token in manifest_text.lower()]
        assert not hits, (name, hits)
        qml = (CATALOG / name / "ui" / "Main.qml").read_text(encoding="utf-8")
        code = "\n".join(line for line in qml.splitlines()
                         if not line.lstrip().startswith("//"))
        for token in QML_HOOKS:
            assert token not in code, (name, token)
    try:
        m.PackDefinition(
            builtin_id=m.MODERN_BUILTIN_ID, manifest_id=m.MODERN_MANIFEST_ID,
            name="Paid", capabilities=frozenset({"dock"}), entrypoint="ui/Main.qml",
            source="tools/shell_packs/modern", tier="paid",
        )
    except m.ShellPackManifestError:
        pass
    else:
        raise AssertionError("a paid tier was accepted")
    return {"catalog_manifests_checked": len(INITIAL_CATALOG),
            "paid_tiers": [], "qml_runtime_hooks": []}


for label, fn in (
    ("catalog_manifests_pass_offline_checker", check_catalog_checker),
    ("first_party_inventory_all_eight", check_inventory),
    ("prepare_apply_verify_release", check_healthy_path),
    ("failed_verify_rollback", check_failure_rollback),
    ("illegal_transition_negative_controls", check_negative_controls),
    ("one_hundred_synthetic_round_trips", check_hundred_round_trips),
    ("owned_paths_and_classic_preserved", check_scope_and_classic_preservation),
    ("no_paid_tiers_activation_telemetry_or_runtime_hooks", check_no_paid_or_runtime_hooks),
):
    record(label, fn)

verdict = "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL"
head = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
    capture_output=True, text=True, timeout=60,
).stdout.strip()
report = {
    "label": "SYNTHETIC",
    "task": "M3 Shell Pack initial eight library",
    "base_sha": BASE,
    "head_sha": head,
    "initial_pack_ids": list(m.INITIAL_PACK_IDS),
    "checks": results,
    "verdict": verdict,
    "not_run": [
        "native Plasma/KWin session switch",
        "live Classic-to-any-pack switch preserving running applications",
        "compiled Qt/QML rendering and owner visual acceptance",
        "real PSS/CPU/GPU measurement",
        "screen-reader and real desktop keyboard verification",
        "install, rollback and upgrade on a disposable guest",
    ],
    "resource_impact": {
        "measured": "SYNTHETIC: bounded metadata validation, seven manifest checks, one eight-definition inventory and 300 immutable ledger transitions",
        "not_measured": "NOT_RUN: native runtime PSS, CPU, GPU, wakeups and frame times",
        "rationale": "No process, service, timer, compositor change or UI code is added or executed.",
    },
}
REPORT.write_text(
    json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
)
SUMS.write_bytes(
    (hashlib.sha256(REPORT.read_bytes()).hexdigest()
     + "  synthetic_verification.json\n").encode("ascii")
)
print(json.dumps({"verdict": verdict, "head_sha": head, "checks": {
    key: value["status"] for key, value in results.items()}}, indent=2))
raise SystemExit(0 if verdict == "PASS" else 1)
