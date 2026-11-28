#!/usr/bin/env python3
"""Bounded verifier and read-only capability-map CLI for LacOS multi-ecosystem.

Subcommands:
  map [--file NAME] [--json]  present the inert five-ecosystem capability map
  verify                      run bounded static/synthetic checks
  verify-write                verify and write the evidence JSON report
  pin --yes                   regenerate the fixture SHA-256 manifest

Nothing here launches a package manager, contacts a guest, mutates the booted
core, starts a service, executes a handoff step, or approves a real guest.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canopy_features.multi_ecosystem import (  # noqa: E402
    CANONICAL_ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    MultiEcosystemError,
    SOURCE_HEADS,
    SOURCE_SHA256,
    build_capability_map,
    reject_duplicate_keys,
    view_dict,
)

FIXTURES = ROOT / "scratch" / "lacos_multi_ecosystem" / "fixtures"
EVIDENCE = ROOT / "scratch" / "lacos_multi_ecosystem" / "evidence"
PRODUCTION = ROOT / "canopy_features" / "multi_ecosystem"
SNAPSHOT = "capability_snapshot.json"
MAX_JSON_BYTES = 65_536
EXPECTED_NEGATIVES = 29
EXPECTED_CAPABILITIES = 27
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_IMPORT_ROOTS = frozenset((
    "__future__", "collections", "dataclasses", "hashlib", "json", "re",
    "types", "typing", "unicodedata", "canopy_features",
))
FORBIDDEN_IMPORT_ROOTS = frozenset((
    "subprocess", "socket", "urllib", "requests", "http", "os", "pathlib",
    "shutil", "tempfile", "ctypes", "multiprocessing", "threading",
))
WRITE_METHODS = frozenset((
    "write_text", "write_bytes", "mkdir", "unlink", "rmtree", "chmod",
    "write", "writelines", "rename", "replace", "touch", "symlink_to",
))
VERIFIER_EXCEPTION_CODE = "VERIFIER_EXCEPTION"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    """Read one bounded JSON fixture; fail closed on hostile input."""
    if not isinstance(path, Path):
        raise MultiEcosystemError("FIXTURE_PATH_INVALID")
    name = path.name
    if (not _NAME.fullmatch(name) or ".." in name
            or path.parent not in (FIXTURES, FIXTURES / "negative")):
        raise MultiEcosystemError("FIXTURE_PATH_INVALID")
    try:
        if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            raise MultiEcosystemError("FIXTURE_TOO_LARGE")
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise MultiEcosystemError("FIXTURE_READ_ERROR") from None
    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("non-finite constant")))
    except MultiEcosystemError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise MultiEcosystemError("INPUT_OUT_OF_BOUNDS") from None


def import_roots(text: str):
    tree = ast.parse(text)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def static_flags(text: str):
    """Detect live process/network/write sites, not docstring literals."""
    tree = ast.parse(text)
    live = False
    write = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in ("Popen", "urlopen", "eval", "exec",
                               "__import__"):
                    live = True
                elif func.id == "open":
                    write = True
            elif isinstance(func, ast.Attribute):
                root = func.value.id if isinstance(func.value, ast.Name) else ""
                if root == "os" and func.attr in (
                        "system", "popen", "execv", "spawnv"):
                    live = True
                if func.attr in WRITE_METHODS:
                    write = True
    return live, write


def _record(checks, name: str, passed: bool) -> None:
    checks.append((name, "PASS" if passed else "FAIL"))


def _expect_code(fn, code: str) -> bool:
    try:
        fn()
    except MultiEcosystemError as exc:
        return exc.code == code
    except Exception:
        return False
    return False


def _fixture_hashes():
    pin = FIXTURES / "SHA256SUMS"
    result = {}
    try:
        if not pin.is_file() or pin.stat().st_size > MAX_JSON_BYTES:
            return result
        for line in pin.read_text(encoding="utf-8").splitlines():
            parts = line.split("  ", 1)
            if (len(parts) == 2 and _HEX64.fullmatch(parts[0])
                    and _NAME.fullmatch(parts[1]) and ".." not in parts[1]):
                result[parts[1]] = parts[0]
    except OSError:
        return {}
    return result


def pin_hashes() -> int:
    names = sorted(path.name for path in FIXTURES.iterdir()
                   if path.is_file() and path.name != "SHA256SUMS")
    lines = [f"{_sha(FIXTURES / name)}  {name}" for name in names]
    (FIXTURES / "SHA256SUMS").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8", newline="\n")
    return len(names)


def _emit(checks, failed, verdict, code=None):
    for name, status in checks:
        print(f"CHECK\t{name}\t{status}")
    if code is not None:
        print(f"CODE\t{code}")
    print(f"SUMMARY\tchecks={len(checks)}\tpass={len(checks) - len(failed)}"
          f"\tfail={len(failed)}\tverdict={verdict}")
    if failed:
        print("FIRST\t" + failed[0])


def _write_report(checks, failed, verdict, context, failure_code=None):
    report = {
        "schema_version": 1,
        "evidence_labels": ["STATIC SOURCE ONLY", "SYNTHETIC"],
        "guest_execution": "NOT_RUN",
        "guest_acceptance": "NOT_RUN",
        "real_guest": {"status": "BLOCKED", "gate": "NOT_RUN"},
        "runtime": "BLOCKED_NOT_RUN",
        "source_consumption": "read-only",
        "source_heads": dict(SOURCE_HEADS),
        "source_sha256": dict(SOURCE_SHA256),
        "production_sha256": {
            name: _sha(PRODUCTION / name)
            for name in sorted(context["texts"])},
        "fixture_sha256": dict(sorted(context["actual"].items())),
        "checks": [{"id": name, "status": status} for name, status in checks],
        "verdict": verdict,
        "note": ("Read-only-first declaration map only. No capability grants, "
                 "core mutation, paid tiers, accounts, telemetry or duplicate "
                 "services. No real guest or runtime was executed."),
    }
    if failure_code is not None:
        report["failure_code"] = failure_code
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "verification_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")


def _terminal_failure(checks, code, write_report, context):
    _record(checks, "VERIFIER_GUARD", False)
    failed = ["VERIFIER_GUARD"]
    _emit(checks, failed, "FAIL", code=code)
    if write_report:
        _write_report(checks, failed, "FAIL", context, failure_code=code)
    return 1


def verify(write_report: bool = False) -> int:
    checks = []
    context = {"actual": {}, "texts": {}}
    try:
        failed = _run_checks(checks, context)
    except MultiEcosystemError as exc:
        return _terminal_failure(checks, exc.code, write_report, context)
    except Exception:
        return _terminal_failure(checks, VERIFIER_EXCEPTION_CODE,
                                 write_report, context)
    verdict = "PASS" if not failed else "FAIL"
    _emit(checks, failed, verdict)
    if write_report:
        _write_report(checks, failed, verdict, context)
    return 0 if verdict == "PASS" else 1


def _run_checks(checks, context):
    pinned = _fixture_hashes()
    actual = {name: _sha(FIXTURES / name) for name in pinned
              if (FIXTURES / name).is_file()}
    _record(checks, "FIXTURE_HASHES",
            bool(pinned) and pinned == actual
            and SNAPSHOT in pinned and "negative_cases.json" in pinned)

    sources = sorted(PRODUCTION.glob("*.py"))
    texts = {path.name: path.read_text(encoding="utf-8") for path in sources}
    flags = [static_flags(text) for text in texts.values()]
    roots = set()
    for text in texts.values():
        roots |= import_roots(text)
    _record(checks, "STATIC_FIVE_ECOSYSTEMS",
            CANONICAL_ECOSYSTEM_IDS == (
                "apt_deb", "dnf_rpm", "flatpak_flathub", "pacman",
                "rootless_podman_oci"))
    _record(checks, "STATIC_FORBIDDEN_CAPABILITIES",
            {"core_mutation", "host_repo_mixing", "partial_upgrade",
             "privileged", "telemetry", "paid_tier", "always_on", "accounts"}
            <= FORBIDDEN_CAPABILITIES)
    _record(checks, "STATIC_NO_TOOL_EXEC",
            bool(sources) and not any(live for live, _ in flags))
    _record(checks, "STATIC_NO_WRITE_IO",
            bool(sources) and not any(write for _, write in flags))
    _record(checks, "STATIC_READ_ONLY_IMPORTS",
            bool(sources) and roots <= ALLOWED_IMPORT_ROOTS
            and not roots & FORBIDDEN_IMPORT_ROOTS)

    snapshot = load_json(FIXTURES / SNAPSHOT)
    view = build_capability_map(snapshot)
    _record(checks, "SNAPSHOT_VALID", view_dict(view)["status"] ==
            "DECLARED_READ_ONLY_FIRST")
    _record(checks, "SNAPSHOT_FIVE_ECOSYSTEMS",
            len(view.ecosystems) == 5
            and tuple(item.id for item in view.ecosystems)
            == CANONICAL_ECOSYSTEM_IDS)
    _record(checks, "SNAPSHOT_CAPABILITY_COVERAGE",
            view.capability_count == EXPECTED_CAPABILITIES)
    _record(checks, "SNAPSHOT_READ_ONLY_FIRST",
            all(entry.access == "read_only"
                and entry.status == "READ_ONLY_DECLARED"
                for item in view.ecosystems for entry in item.capabilities
                if entry.access == "read_only")
            and all(entry.access == "mutating"
                and entry.status == "DESCRIBE_ONLY"
                for item in view.ecosystems for entry in item.capabilities
                if entry.access == "mutating"))
    _record(checks, "SNAPSHOT_NO_OPERATIONAL_GRANTS",
            not view.grants and view.launch_permitted is False
            and view.guest_acceptance == "NOT_RUN"
            and dict(view.real_guest) == {"status": "BLOCKED",
                                          "gate": "NOT_RUN"}
            and view.runtime == "BLOCKED_NOT_RUN")
    _record(checks, "SNAPSHOT_CONSUMES_P0_PINS",
            dict(view.source_pins) == SOURCE_SHA256
            and dict(view.source_heads) == SOURCE_HEADS)
    _record(checks, "SNAPSHOT_CONTRACT_GATES",
            view.contract_gates_ok
            and view.contracts["atomic_updates"] ==
            "READY_FOR_HANDOFF_DECLARED"
            and view.contracts["backup_recovery"] ==
            "SEALED_REVIEW_REQUIRED_DECLARED"
            and view.contracts["app_isolation"] ==
            "UPSTREAM_DESCRIBE_ONLY_DECLARED")

    try:
        view.ecosystems[0].capabilities[0].label = "mutated"
        immutable = False
    except Exception:
        immutable = True
    try:
        view.policy["paid_tiers"] = True
        immutable = immutable and False
    except Exception:
        immutable = immutable and True
    _record(checks, "VIEW_IMMUTABLE", immutable)
    _record(checks, "VIEW_DETERMINISTIC",
            view_dict(view) == view_dict(build_capability_map(
                load_json(FIXTURES / SNAPSHOT))))

    cases = load_json(FIXTURES / "negative_cases.json")
    _record(checks, "NEGATIVE_COUNT_BOUND",
            type(cases) is dict and len(cases) == EXPECTED_NEGATIVES)
    for name in sorted(cases):
        expected = cases[name]

        def check_negative(filename=name, code=expected):
            try:
                result = build_capability_map(load_json(FIXTURES / filename))
            except MultiEcosystemError as exc:
                return exc.code == code
            reasons = [reason for item in result.ecosystems
                       for entry in item.capabilities
                       for reason in entry.reasons]
            return code in reasons

        _record(checks, "NEGATIVE_" + name[:-5].upper().replace("_", ""),
                check_negative())

    hostile = copy.deepcopy(snapshot)
    hostile["ecosystems"][0]["capabilities"] = {"search"}
    _record(checks, "HARDEN_UNORDERED_REJECTED",
            _expect_code(lambda: build_capability_map(hostile),
                         "CANONICAL_JSON_INVALID"))
    hostile = copy.deepcopy(snapshot)
    hostile["ecosystems"][0]["capabilities"] = "search"
    _record(checks, "HARDEN_STRING_NOT_SEQUENCE",
            _expect_code(lambda: build_capability_map(hostile),
                         "CAPABILITIES_INVALID"))
    _record(checks, "HARDEN_TOP_NOT_MAPPING",
            _expect_code(lambda: build_capability_map([]),
                         "TOP_FIELDS_INVALID"))
    hostile = copy.deepcopy(snapshot)
    hostile["extra"] = True
    _record(checks, "HARDEN_TOP_FIELDS_INVALID",
            _expect_code(lambda: build_capability_map(hostile),
                         "TOP_FIELDS_INVALID"))
    hostile = copy.deepcopy(snapshot)
    hostile["contracts"]["sources"]["context"] = "real-guest"
    _record(checks, "HARDEN_REAL_GUEST_CONTEXT_REJECTED",
            _expect_code(lambda: build_capability_map(hostile),
                         "SOURCE_CONTRACT_INVALID"))

    context["actual"] = actual
    context["texts"] = texts
    return [name for name, status in checks if status == "FAIL"]


def presentation_lines(view) -> list:
    lines = [f"MULTI_ECOSYSTEM\tstatus={view.status}",
             f"ECOSYSTEMS\tcount={len(view.ecosystems)}",
             f"CAPABILITIES\tcount={view.capability_count}\tgrants=0",
             f"REAL_GUEST\tstatus=BLOCKED\tgate=NOT_RUN",
             f"RUNTIME\tstatus=BLOCKED_NOT_RUN"]
    for item in view.ecosystems:
        read_only = sum(1 for entry in item.capabilities
                        if entry.access == "read_only")
        describe = sum(1 for entry in item.capabilities
                       if entry.status == "DESCRIBE_ONLY")
        lines.append(f"MAP\t{item.id}\tread_only={read_only}"
                     f"\tdescribe_only={describe}\tstatus={item.status}")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    map_cmd = sub.add_parser("map", help="present the inert capability map")
    map_cmd.add_argument("--json", action="store_true")
    map_cmd.add_argument("--file", default=SNAPSHOT)
    sub.add_parser("verify", help="run bounded static/synthetic checks")
    pin_cmd = sub.add_parser("pin", help="regenerate fixture SHA-256 manifest")
    pin_cmd.add_argument("--yes", action="store_true")
    verify_cmd = sub.add_parser("verify-write", help="verify and write evidence")
    verify_cmd.set_defaults(write_report=True)
    args = parser.parse_args(argv)
    if args.command == "map":
        view = build_capability_map(load_json(FIXTURES / args.file))
        if args.json:
            print(json.dumps(view_dict(view), indent=2, sort_keys=True))
        else:
            for line in presentation_lines(view):
                print(line)
        return 0
    if args.command == "pin":
        if not args.yes:
            print("PIN\tBLOCKED\tpass --yes to rewrite fixture hashes")
            return 1
        print(f"PIN\tfiles={pin_hashes()}")
        return 0
    return verify(write_report=getattr(args, "write_report", False))


if __name__ == "__main__":
    raise SystemExit(main())
