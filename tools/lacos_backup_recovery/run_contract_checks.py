"""Run bounded synthetic contract checks and emit deterministic evidence.

Usage (from the worktree root or anywhere)::

    PYTHONPATH=<worktree-root> python tools/lacos_backup_recovery/run_contract_checks.py

No guest, deployment, package manager or live owner-data path is touched.
Every check is either ``SYNTHETIC`` (fixture bytes) or ``NOT_RUN`` (real guest).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# Allow direct invocation without an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from canopy_features.backup_recovery import (  # noqa: E402
    ALLOW_STAGED,
    BLOCKED,
    INTEGRITY_FAILED,
    NOT_RUN,
    OK,
    OWNER_DATA_CONFLICT,
    PLANNING,
    REFUSE,
    ROLLBACK_IN_FLIGHT,
    TARGET_NOT_CONTAINED,
    BackupRecoveryError,
    RollbackCheckpointView,
    SourceSpec,
    build_plan,
    canonical_bytes,
    parse_bounded_document,
    valid_restore_root,
)
from canopy_features.backup_recovery.integrity import (  # noqa: E402
    MISMATCH,
    build_manifest,
    verify_manifest,
)
from canopy_features.backup_recovery.checkpoint import (  # noqa: E402
    CheckpointJournal,
    RESUME,
    WAIT_ROLLBACK,
)
from canopy_features.backup_recovery.restore import (  # noqa: E402
    CHECKPOINT_NOT_SEALED,
    CORE_MUTATION_REFUSED,
    DEPLOYMENT_CHANGED,
    GUEST_NOT_RUN,
    evaluate_restore,
)
from .synthetic_fixtures import (  # noqa: E402
    CAPTURED_AT,
    _FIXTURE_FILES,
    build_fixture,
    tamper_one,
    write_document,
)

BASE = Path(__file__).resolve().parents[2] / "scratch" / "lacos_backup_recovery"
_TARGET_ROOT = "restore/candidate_a"
_CURRENT = "deployment.20261128.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(base_dir=None) -> dict:
    """Run all checks and return an evidence dictionary (no wall clock)."""
    base = Path(base_dir) if base_dir is not None else BASE
    checks: dict = {}
    artifact_paths: list = []

    fixture = build_fixture(base / "fixture")
    for relative in _FIXTURE_FILES:
        artifact_paths.append(fixture.path_for(relative))

    plan_doc = fixture.plan.to_document()
    write_document(base / "plan.json", plan_doc)
    checks["plan_digest_is_canonical"] = (
        fixture.plan.digest() == hashlib.sha256(
            canonical_bytes(plan_doc)).hexdigest())
    artifact_paths.append(base / "plan.json")

    manifest_result = build_manifest(fixture.source_root, fixture.plan)
    checks["manifest_build_ok"] = (
        manifest_result.status == OK and manifest_result.manifest is not None)
    if manifest_result.manifest is None:
        return {"label": "SYNTHETIC", "checks": checks, "error": "manifest build failed"}
    manifest = manifest_result.manifest
    write_document(base / "manifest.json", manifest.to_document())
    artifact_paths.append(base / "manifest.json")
    checks["manifest_plan_digest_matches_plan"] = manifest.plan_digest == fixture.plan.digest()

    verified = verify_manifest(manifest, fixture.source_root)
    checks["manifest_verifies_synthetic"] = verified.verified

    journal = CheckpointJournal(fixture.state_dir)
    journal.path.unlink(missing_ok=True)
    journal.begin(fixture.plan, fixture.provenance, manifest.digest())
    record = journal.seal()
    artifact_paths.append(journal.path)
    checks["checkpoint_sealed"] = record.sealed and not record.rollback_in_flight
    checks["recover_resumes"] = journal.recover().action == RESUME

    baseline = evaluate_restore(
        checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT,
    )
    checks["restore_baseline_staged"] = (
        baseline.action == ALLOW_STAGED and baseline.safe_to_apply)
    checks["restore_steps_never_name_live_paths"] = all(
        step.startswith("STAGE ") or step.startswith("REVIEW_REQUIRED")
        for step in baseline.steps)

    def refuse(**kwargs) -> bool:
        defaults: dict = dict(
            checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
            manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
            target_root=_TARGET_ROOT)
        defaults.update(kwargs)
        decision = evaluate_restore(**defaults)  # type: ignore[arg-type]
        return decision.action == REFUSE

    rolled = journal.mark_rollback("deployment.20261128.1")
    rolled_recover = journal.recover()
    rolled_decision = evaluate_restore(
        checkpoint=rolled, plan=fixture.plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT)
    checks["gate_rollback_in_flight"] = (
        rolled.rollback_in_flight and rolled_recover.action == WAIT_ROLLBACK
        and rolled_decision.action == REFUSE
        and ROLLBACK_IN_FLIGHT in rolled_decision.reasons)

    checks["gate_deployment_changed"] = refuse(current_deployment_id="deployment.20261128.9")
    checks["gate_owner_data_conflict"] = (
        refuse(existing_targets=("notes",))
        and OWNER_DATA_CONFLICT in evaluate_restore(
            checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
            manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
            target_root=_TARGET_ROOT, existing_targets=("notes",)).reasons)
    checks["owner_ack_relaxes_conflict"] = evaluate_restore(
        checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT, existing_targets=("notes",),
        acked_targets=("notes",)).action == ALLOW_STAGED
    checks["gate_target_not_contained"] = (
        refuse(target_root="core/restore") and not valid_restore_root("/usr/bin")
        and not valid_restore_root("restore/home/data"))

    planning_state = base / "fixture" / "planning_state"
    planning_state.mkdir(parents=True, exist_ok=True)
    planning_journal = CheckpointJournal(planning_state)
    planning_journal.path.unlink(missing_ok=True)
    planning_record = planning_journal.begin(
        fixture.plan, fixture.provenance, manifest.digest())
    planning_decision = evaluate_restore(
        checkpoint=planning_record, plan=fixture.plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT)
    checks["gate_checkpoint_not_sealed"] = (
        planning_record.state == PLANNING
        and planning_decision.action == REFUSE
        and CHECKPOINT_NOT_SEALED in planning_decision.reasons)

    core_plan = build_plan(
        "core_plan", _CURRENT,
        [SourceSpec("core", "owner_data/notes.txt", "owner_data")])
    core_decision = evaluate_restore(
        checkpoint=record, plan=core_plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT)
    checks["gate_core_mutation_refused"] = (
        CORE_MUTATION_REFUSED in core_decision.reasons
        and core_decision.action == REFUSE)

    pinned_view = RollbackCheckpointView(_CURRENT, "a" * 64, True, CAPTURED_AT)
    unpinned_view = RollbackCheckpointView(_CURRENT, "a" * 64, False, CAPTURED_AT)
    checks["rollback_view_pinned_allows"] = evaluate_restore(
        checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT, rollback_view=pinned_view).action == ALLOW_STAGED
    unpinned_decision = evaluate_restore(
        checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT, rollback_view=unpinned_view)
    checks["gate_rollback_checkpoint_unpinned"] = (
        unpinned_decision.action == REFUSE
        and "ROLLBACK_CHECKPOINT_MISSING" in unpinned_decision.reasons)
    guest = evaluate_restore(
        checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
        manifest=manifest, integrity=verified, current_deployment_id=_CURRENT,
        target_root=_TARGET_ROOT, guest_class="REAL_GUEST_NOT_RUN")
    checks["real_guest_is_not_run"] = guest.action == NOT_RUN and GUEST_NOT_RUN in guest.reasons

    try:
        parse_bounded_document(b'{"plan":1,"plan":2}')
        checks["duplicate_json_keys_rejected"] = False
    except BackupRecoveryError:
        checks["duplicate_json_keys_rejected"] = True

    tamper_one(fixture)
    tampered = verify_manifest(manifest, fixture.source_root)
    checks["tamper_detected"] = tampered.status == MISMATCH
    checks["gate_integrity_failed"] = (
        evaluate_restore(
            checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
            manifest=manifest, integrity=tampered, current_deployment_id=_CURRENT,
            target_root=_TARGET_ROOT).action == REFUSE
        and INTEGRITY_FAILED in evaluate_restore(
            checkpoint=record, plan=fixture.plan, provenance=fixture.provenance,
            manifest=manifest, integrity=tampered, current_deployment_id=_CURRENT,
            target_root=_TARGET_ROOT).reasons)
    target = fixture.path_for("owner_data/notes.txt")
    target.write_bytes(_FIXTURE_FILES["owner_data/notes.txt"])
    checks["fixture_restored_to_deterministic_bytes"] = verify_manifest(
        manifest, fixture.source_root).verified

    artifacts = {}
    for path in artifact_paths:
        if path.exists():
            artifacts[path.relative_to(base.parent.parent).as_posix()] = sha256_file(path)
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "label": "SYNTHETIC",
        "real_guest": {
            "status": BLOCKED,
            "gate": NOT_RUN,
            "reason": "no real Kinoite/Mint guest, deployment or live owner data was contacted",
        },
        "checks": checks,
        "summary": {"total": len(checks), "passed": len(checks) - len(failed),
                    "failed": len(failed), "failed_names": failed},
        "artifacts": artifacts,
    }


def main() -> int:
    evidence = run()
    write_document(BASE / "evidence_synthetic.json", evidence)
    digest = sha256_file(BASE / "evidence_synthetic.json")
    (BASE / "evidence_synthetic.json.sha256").write_bytes(
        (digest + "  evidence_synthetic.json\n").encode("utf-8"))
    summary = evidence.get("summary", {})
    print("label=SYNTHETIC real_guest=BLOCKED/NOT_RUN")
    print("checks total={total} passed={passed} failed={failed}".format(**summary))
    print("failed_names={}".format(",".join(summary.get("failed_names", [])) or "none"))
    print("evidence_sha256={}".format(digest))
    return 0 if summary.get("failed") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
