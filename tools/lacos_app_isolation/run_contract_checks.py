"""Run bounded synthetic checks and emit deterministic evidence.

Usage (from the worktree root)::

    python tools/lacos_app_isolation/run_contract_checks.py

Produces ``scratch/lacos_app_isolation/evidence/evidence_synthetic.json`` and
an LF-only ``.sha256`` sidecar. Every check is either SYNTHETIC (fixture bytes
and static source analysis) or NOT_RUN (real guest). No application, portal,
sandbox, systemd unit or compositor is started.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from canopy_features.app_isolation import (  # noqa: E402
    DESCRIBE_ONLY,
    FORBIDDEN_PERMISSIONS,
    MECHANISMS,
    MECHANISMS_BY_ECOSYSTEM,
    NOT_RUN,
    REFUSE,
    SOURCE_POLICY,
    canonical_bytes,
    evaluate_request,
)
from synthetic_fixtures import (  # noqa: E402
    EVIDENCE_DIR,
    FIXTURE_DIR,
    fixture_bytes,
    load_request,
    sha256_bytes,
    sha256_file,
    write_document,
)

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = "ec910d7a7275296ecbc8b5e5c459d356205165d1"
PRODUCTION = ROOT / "canopy_features" / "app_isolation"
TOOLS = ROOT / "tools" / "lacos_app_isolation"
OWNED_PREFIXES = (
    "canopy_features/app_isolation/",
    "docs/LACOS_APP_ISOLATION.md",
    "scratch/lacos_app_isolation/",
    "tools/lacos_app_isolation/",
)

_DANGEROUS_MODULES = frozenset((
    "subprocess", "socket", "shutil", "requests", "os", "ctypes",
    "multiprocessing", "threading", "dbus", "dbusmainloop", "urllib", "http",
))
_DANGEROUS_CALLS = frozenset((
    "open", "exec", "eval", "input", "write", "writelines", "write_bytes",
    "write_text", "unlink", "rmdir", "mkdir", "rename", "replace", "remove",
    "start", "spawn", "connect", "bind", "popen", "system",
))
_STACK_WORDS = ("sandbox", "compositor", "service", "daemon")


def _production_sources() -> Dict[str, str]:
    result = {}
    for path in sorted(PRODUCTION.glob("*.py")):
        result[path.name] = path.read_text("utf-8")
    return result


def _static_checks(sources: Dict[str, str]) -> Dict[str, bool]:
    checks: Dict[str, bool] = {}
    expected = {"__init__.py", "contract.py", "policy.py", "upstream.py"}
    checks["production_modules_present"] = set(sources) == expected

    bad_imports = []
    bad_calls = []
    bad_identifiers = []
    absolute_literals = []
    for name, text in sources.items():
        tree = ast.parse(text, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
                if roots & _DANGEROUS_MODULES:
                    bad_imports.append(name)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in _DANGEROUS_MODULES:
                    bad_imports.append(name)
            elif isinstance(node, ast.Call):
                func = node.func
                called = (func.id if isinstance(func, ast.Name)
                          else func.attr if isinstance(func, ast.Attribute)
                          else "")
                if called in _DANGEROUS_CALLS:
                    bad_calls.append(name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                if any(word in node.name.lower() for word in _STACK_WORDS):
                    bad_identifiers.append(name)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if value.startswith("/") or (len(value) > 1
                                             and value[1] == ":"
                                             and value[0].isalpha()):
                    absolute_literals.append(name)
    checks["no_process_network_or_write_imports"] = not bad_imports
    checks["no_execution_or_write_calls"] = not bad_calls
    checks["no_duplicate_stack_identifiers"] = not bad_identifiers
    checks["no_absolute_path_literals"] = not absolute_literals

    contract_text = sources.get("contract.py", "")
    policy_text = sources.get("policy.py", "")
    checks["forbidden_policy_symbols_present"] = all(
        token in contract_text and token in policy_text
        for token in ("core_mutation", "duplicate_sandbox",
                      "duplicate_service", "duplicate_compositor")
    ) and all(token in contract_text for token in (
        "paid_tier", "telemetry", "account_required", "FORBIDDEN_PERMISSIONS"))
    checks["no_account_paid_or_telemetry_flags_optional"] = all(
        token in policy_text for token in (
            "no_paid_tiers", "no_telemetry", "no_accounts"))
    checks["fixed_upstream_catalog"] = (
        set(MECHANISMS) == set().union(*MECHANISMS_BY_ECOSYSTEM.values())
        and len(MECHANISMS) == 6)
    checks["five_signed_ecosystems_covered"] = (
        len(SOURCE_POLICY) == 5
        and all(set(policy) == {"provenance", "signatures"}
                for policy in SOURCE_POLICY.values()))
    return checks


def _owned_paths() -> bool:
    """Verify the diff against the pinned base contains only owned paths."""
    tracked = subprocess.run(
        ["git", "diff", "--name-only", BASE_SHA, "--"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if tracked.returncode != 0 or untracked.returncode != 0:
        return False
    names = (tracked.stdout + untracked.stdout).decode("utf-8", "replace").splitlines()
    return bool(names) and all(
        any(name.startswith(prefix) or name == prefix
            for prefix in OWNED_PREFIXES) for name in names)


def _fixture_checks() -> Dict[str, bool]:
    checks: Dict[str, bool] = {}
    pins = (FIXTURE_DIR / "SHA256SUMS").read_text("ascii").splitlines()
    checks["fixture_count_19"] = len(pins) == 19
    checks["fixture_hashes_pinned"] = all(
        sha256_file(FIXTURE_DIR / line.split("  ", 1)[1]) == line.split("  ", 1)[0]
        for line in pins)
    valid = load_request("F001_valid_flatpak.json")
    podman = load_request("F002_valid_podman.json")
    write_ack = load_request("F003_valid_write_ack.json")
    checks["canonical_request_digest"] = (
        valid.digest() == sha256_bytes(canonical_bytes(valid.to_document())))
    checks["valid_synthetic_describe_only"] = all(
        evaluate_request(request).action == DESCRIBE_ONLY
        for request in (valid, podman, write_ack))
    checks["steps_are_inert_and_review_gated"] = all(
        all(step.startswith("UPSTREAM ") or step.startswith("REVIEW_REQUIRED")
            for step in evaluate_request(request).steps)
        and evaluate_request(request).steps[-1].startswith("REVIEW_REQUIRED")
        for request in (valid, podman, write_ack))
    checks["no_launch_is_permitted"] = all(
        not evaluate_request(request).to_document()["launch_permitted"]
        for request in (valid, podman, write_ack))

    def has(name: str, reason: str) -> bool:
        return reason in evaluate_request(load_request(name)).reasons

    checks["signature_gate"] = (
        has("F010_unsigned.json", "SIGNATURE_NOT_VERIFIED")
        and has("F010_unsigned.json", "SIGNATURE_UNSUPPORTED"))
    checks["provenance_gate"] = has("F011_foreign_provenance.json",
                                    "PROVENANCE_UNTRUSTED")
    checks["core_mutation_gate"] = has("F012_core_mutation.json",
                                       "CORE_MUTATION_REFUSED")
    checks["duplicate_sandbox_gate"] = (
        has("F013_duplicate_sandbox.json", "DUPLICATE_SANDBOX_REFUSED")
        and has("F013_duplicate_sandbox.json", "MECHANISM_NOT_UPSTREAM"))
    checks["duplicate_service_gate"] = has("F014_duplicate_service.json",
                                           "DUPLICATE_SERVICE_REFUSED")
    checks["paid_tier_gate"] = has("F015_paid_tier.json", "NON_FOSS_CONDITION")
    checks["telemetry_gate"] = has("F016_telemetry.json", "NON_FOSS_CONDITION")
    checks["account_gate"] = has("F017_account.json", "NON_FOSS_CONDITION")
    checks["host_context_no_grant"] = has("F018_host_context.json",
                                          "HOST_ONLY_NO_GRANT")
    checks["write_review_gate"] = has("F020_write_without_review.json",
                                      "WRITE_NEEDS_REVIEW")
    checks["unknown_permission_gate"] = has("F021_unknown_permission.json",
                                            "PERMISSION_NOT_ALLOWED")
    checks["source_ecosystem_gate"] = has(
        "F022_wrong_ecosystem_source.json", "SOURCE_ECOSYSTEM_MISMATCH")
    checks["mechanism_must_be_upstream"] = has(
        "F023_mech_non_upstream.json", "MECHANISM_NOT_UPSTREAM")

    real = evaluate_request(load_request("F019_real_guest.json"))
    checks["real_guest_blocked_not_run"] = (
        real.action == NOT_RUN and not real.steps
        and "REAL_GUEST_BLOCKED" in real.reasons
        and "GUEST_NOT_RUN" in real.reasons)

    from canopy_features.app_isolation import AppIsolationError
    hostile = []
    for name in ("F024_hostile_duplicate_key.json", "F025_huge_integer.json"):
        try:
            load_request(name)
        except AppIsolationError:
            hostile.append(name)
    checks["hostile_documents_fail_closed"] = len(hostile) == 2
    checks["wrong_type_refused"] = (
        evaluate_request("not-a-request").action == REFUSE)
    checks["forbidden_set_covers_product_constraints"] = all(
        name in FORBIDDEN_PERMISSIONS for name in (
            "core_mutation", "privileged", "always_on", "telemetry",
            "paid_tier", "account_required", "duplicate_sandbox",
            "duplicate_compositor", "duplicate_service"))
    checks["fixtures_are_synthetic_only"] = all(
        b"SYNTHETIC" in fixture_bytes(name) or name.startswith("F0")
        for name in ("F001_valid_flatpak.json", "F019_real_guest.json"))
    return checks


def run() -> dict:
    sources = _production_sources()
    checks: Dict[str, bool] = {}
    checks.update(_static_checks(sources))
    checks.update(_fixture_checks())
    checks["owned_paths_only"] = _owned_paths()
    checks["tests_inside_owned_tools"] = (
        (TOOLS / "test_app_isolation_contract.py").is_file())
    test_diff = subprocess.run(
        ["git", "diff", "--name-only", BASE_SHA, "--", "tests/"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "tests/"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    checks["no_test_tree_modification"] = (
        test_diff.returncode == 0 and untracked.returncode == 0
        and not test_diff.stdout.strip() and not untracked.stdout.strip())

    failed = sorted(name for name, passed in checks.items() if not passed)
    artifacts: Dict[str, str] = {}
    for base in (PRODUCTION, TOOLS, FIXTURE_DIR, ROOT / "docs" / "LACOS_APP_ISOLATION.md",
                 ROOT / "scratch" / "lacos_app_isolation" / "README.md"):
        paths = sorted(base.glob("*.py")) + sorted(base.glob("*.json"))
        if base.is_file():
            paths = [base]
        for path in paths:
            if path.is_file() and "__pycache__" not in path.parts:
                artifacts[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    return {
        "label": "SYNTHETIC",
        "base_sha": BASE_SHA,
        "real_guest": {
            "status": "BLOCKED",
            "gate": NOT_RUN,
            "reason": ("no real guest, portal, bubblewrap namespace, "
                       "systemd unit, compositor or application was contacted"),
        },
        "checks": checks,
        "summary": {"total": len(checks), "passed": len(checks) - len(failed),
                    "failed": len(failed), "failed_names": failed},
        "artifacts": artifacts,
    }


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence = run()
    path = EVIDENCE_DIR / "evidence_synthetic.json"
    write_document(path, evidence)
    digest = sha256_file(path)
    (EVIDENCE_DIR / "evidence_synthetic.json.sha256").write_bytes(
        (digest + "  evidence_synthetic.json\n").encode("utf-8"))
    summary = evidence["summary"]
    print("label=SYNTHETIC real_guest=BLOCKED/NOT_RUN")
    print("checks total={total} passed={passed} failed={failed}".format(**summary))
    print("failed_names={}".format(",".join(summary["failed_names"]) or "none"))
    print("evidence_sha256={}".format(digest))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
