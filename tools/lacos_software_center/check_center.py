#!/usr/bin/env python3
"""Bounded verifier and read-only presentation CLI for LacOS Software Center wiring.

Subcommands:
  view [--json] [--file PATH]  present the five P0 ecosystem cards
  verify                       run bounded static/synthetic checks
  verify-write                 verify and write the evidence JSON report
  pin --yes                    regenerate the fixture SHA-256 manifest

Nothing here installs software, executes a package manager, mutates the booted
core, starts a service, contacts a network or approves a real guest.
"""

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

from canopy_features.software_center import (  # noqa: E402
    ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    SoftwareCenterError,
    SoftwareCenterView,
    build_center_view,
    presentation_lines,
    view_dict,
)

FIXTURES = ROOT / "scratch/lacos_software_center/fixtures"
EVIDENCE = ROOT / "scratch/lacos_software_center/evidence"
PRODUCTION = ROOT / "canopy_features/software_center"
SNAPSHOT = "software_center_snapshot.json"
MAX_JSON_BYTES = 65_536
EXPECTED_NEGATIVES = 14
PR753_HEAD = "616ce171a7b71f69f19060122f53c97ada346662"
PR753_BASE = "ec910d7a7275296ecbc8b5e5c459d356205165d1"
SOURCE_PINS = {
    "capability_manifest.py": "91ca6a8bd677c7a584b6c89ada7bb737b5c3a8bbe9da7b1c4cba21344df4d983",
    "source_probe.py": "66685a317e745cddaf33f7c6d92b7d4fe195bc83716b43c55683ac292d981ade",
}
CANONICAL_IDS = ("apt_deb", "dnf_rpm", "flatpak_flathub", "pacman", "rootless_podman_oci")
CANONICAL_DENIALS = frozenset((
    "core_mutation", "host_repo_mixing", "partial_upgrade", "privileged",
    "telemetry", "paid_tier", "always_on", "accounts",
))
ALLOWED_IMPORT_ROOTS = frozenset((
    "collections", "dataclasses", "re", "types", "unicodedata", "typing",
    "canopy_features",
))
FORBIDDEN_IMPORT_ROOTS = frozenset((
    "subprocess", "socket", "urllib", "requests", "http", "os", "pathlib",
    "shutil", "tempfile", "ctypes", "multiprocessing",
))
WRITE_METHODS = frozenset((
    "write_text", "write_bytes", "mkdir", "unlink", "rmtree", "chmod", "write",
    "writelines", "rename", "replace", "touch", "symlink_to",
))
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SoftwareCenterError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def load_json(path: Path):
    """Read one bounded JSON fixture; fail closed on hostile input."""
    if not isinstance(path, Path):
        raise SoftwareCenterError("FIXTURE_PATH_INVALID")
    name = path.name
    if (not isinstance(name, str) or not _NAME.fullmatch(name)
            or ".." in name or path.parent not in (FIXTURES, FIXTURES / "negative")):
        raise SoftwareCenterError("FIXTURE_PATH_INVALID")
    try:
        if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            raise SoftwareCenterError("FIXTURE_TOO_LARGE")
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SoftwareCenterError("FIXTURE_READ_ERROR") from exc
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except SoftwareCenterError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise SoftwareCenterError("FIXTURE_PARSE_ERROR") from exc


def import_roots(text: str):
    tree = ast.parse(text)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
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
                if func.id in ("Popen", "urlopen", "eval", "exec", "__import__"):
                    live = True
                elif func.id == "open":
                    write = True
            elif isinstance(func, ast.Attribute):
                root = func.value.id if isinstance(func.value, ast.Name) else ""
                if root == "os" and func.attr in ("system", "popen", "execv", "spawnv"):
                    live = True
                if func.attr in WRITE_METHODS:
                    write = True
    return live, write


def _record(checks, name, passed):
    checks.append((name, "PASS" if passed else "FAIL"))


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


def pin_hashes():
    names = sorted(path.name for path in FIXTURES.iterdir()
                   if path.is_file() and path.name != "SHA256SUMS")
    lines = [f"{_sha(FIXTURES / name)}  {name}" for name in names]
    (FIXTURES / "SHA256SUMS").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8", newline="\n")
    return len(names)


def _expect_code(fn, code: str) -> bool:
    try:
        fn()
    except SoftwareCenterError as exc:
        return exc.code == code
    except Exception:
        return False
    return False


def verify(write_report: bool = False):
    checks = []
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
    _record(checks, "STATIC_FIVE_ECOSYSTEMS", ECOSYSTEM_IDS == CANONICAL_IDS)
    _record(checks, "STATIC_FORBIDDEN_CAPABILITIES", CANONICAL_DENIALS <= FORBIDDEN_CAPABILITIES)
    _record(checks, "STATIC_NO_TOOL_EXEC", bool(sources) and not any(live for live, _ in flags))
    _record(checks, "STATIC_NO_WRITE_IO", bool(sources) and not any(write for _, write in flags))
    _record(checks, "STATIC_READ_ONLY_IMPORTS",
            bool(sources) and roots <= ALLOWED_IMPORT_ROOTS
            and not roots & FORBIDDEN_IMPORT_ROOTS)

    snapshot = load_json(FIXTURES / SNAPSHOT)
    view = build_center_view(snapshot)
    _record(checks, "SNAPSHOT_VALID", isinstance(view, SoftwareCenterView) and view.ok)
    _record(checks, "SNAPSHOT_FIVE_CARDS",
            len(view.cards) == 5 and tuple(card.id for card in view.cards) == CANONICAL_IDS)
    _record(checks, "SNAPSHOT_NO_CORE_MUTATION",
            view.policy["no_core_mutation"] is True
            and all(card.core_mutation == "ABSENT_DECLARED" for card in view.cards))
    _record(checks, "SNAPSHOT_NO_PAID_ACCOUNTS_TELEMETRY_DUP_SERVICES",
            all(view.policy[key] is False for key in (
                "paid_tiers", "accounts", "telemetry",
                "duplicate_always_on_services", "foreign_host_repo_mixing")))
    _record(checks, "SNAPSHOT_PROVENANCE_SIGNATURE_PRESENT",
            all(card.provenance and card.signature_schemes
                and card.signature_status == "DECLARED_NOT_VERIFIED"
                for card in view.cards))
    _record(checks, "SNAPSHOT_ISOLATION_NOTES_PRESENT",
            all(len(card.isolation) >= 40 and "no " in card.isolation.lower()
                for card in view.cards))
    _record(checks, "SNAPSHOT_RUNTIME_BLOCKED",
            view.runtime == "BLOCKED_NOT_RUN"
            and view.guest_acceptance == "NOT_RUN")
    _record(checks, "SNAPSHOT_CONSUMES_PR753_READ_ONLY",
            view.source_pr == 753 and view.source_head_sha == PR753_HEAD
            and view.source_base_sha == PR753_BASE
            and view.consumption == "read-only"
            and dict(view.source_sha256) == SOURCE_PINS)

    try:
        view.cards[0].label = "mutated"
        immutable = False
    except Exception:
        immutable = True
    try:
        view.policy["paid_tiers"] = True
        immutable = immutable and False
    except Exception:
        immutable = immutable and True
    _record(checks, "VIEW_IMMUTABLE", immutable)
    again = build_center_view(load_json(FIXTURES / SNAPSHOT))
    _record(checks, "VIEW_DETERMINISTIC", view_dict(view) == view_dict(again))

    cases = load_json(FIXTURES / "negative_cases.json")
    _record(checks, "NEGATIVE_COUNT_BOUND",
            isinstance(cases, dict) and len(cases) == EXPECTED_NEGATIVES)
    for name in sorted(cases):
        expected = cases[name]
        _record(checks, "NEGATIVE_" + name[:-5].upper().replace("_", ""),
                _expect_code(
                    lambda p=FIXTURES / name: build_center_view(load_json(p)), expected))

    hostile = copy.deepcopy(snapshot)
    hostile["ecosystems"][0]["capabilities"] = {"search"}
    _record(checks, "HARDEN_UNORDERED_REJECTED",
            _expect_code(lambda: build_center_view(hostile), "UNORDERED_CONTAINER"))
    hostile = copy.deepcopy(snapshot)
    hostile["ecosystems"][0]["capabilities"] = "search"
    _record(checks, "HARDEN_STRING_NOT_SEQUENCE",
            _expect_code(lambda: build_center_view(hostile), "CAPABILITIES_INVALID"))
    _record(checks, "HARDEN_TOP_NOT_MAPPING",
            _expect_code(lambda: build_center_view([]), "TOP_NOT_MAPPING"))
    hostile = copy.deepcopy(snapshot)
    hostile["extra"] = True
    _record(checks, "HARDEN_TOP_FIELDS_INVALID",
            _expect_code(lambda: build_center_view(hostile), "TOP_FIELDS_INVALID"))
    hostile = copy.deepcopy(snapshot)
    hostile["source"]["sha256"]["source_probe.py"] = "0" * 64
    _record(checks, "HARDEN_SOURCE_PIN_INVALID",
            _expect_code(lambda: build_center_view(hostile), "SOURCE_SHA256_INVALID"))
    hostile = copy.deepcopy(snapshot)
    hostile["evidence_labels"] = ["NATIVE RUNTIME"]
    _record(checks, "HARDEN_RUNTIME_LABEL_REJECTED",
            _expect_code(lambda: build_center_view(hostile), "EVIDENCE_LABELS_INVALID"))
    hostile = copy.deepcopy(snapshot)
    hostile["ecosystems"][0]["guest_acceptance"] = "READY"
    _record(checks, "HARDEN_GUEST_CLAIM_REJECTED",
            _expect_code(lambda: build_center_view(hostile), "GUEST_ACCEPTANCE_INVALID"))

    failed = [name for name, status in checks if status == "FAIL"]
    verdict = "PASS" if not failed else "FAIL"
    for name, status in checks:
        print(f"CHECK\t{name}\t{status}")
    print(f"SUMMARY\tchecks={len(checks)}\tpass={len(checks) - len(failed)}"
          f"\tfail={len(failed)}\tverdict={verdict}")
    if failed:
        print("FIRST\t" + failed[0])

    if write_report:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        report = {
            "schema_version": 1,
            "evidence_labels": ["STATIC SOURCE ONLY", "SYNTHETIC"],
            "guest_execution": "NOT_RUN",
            "guest_acceptance": "NOT_RUN",
            "software_center_runtime": "BLOCKED_NOT_RUN",
            "source_consumption": "read-only",
            "source_pr": 753,
            "source_head_sha": PR753_HEAD,
            "source_base_sha": PR753_BASE,
            "source_sha256": SOURCE_PINS,
            "production_sha256": {
                name: _sha(PRODUCTION / name) for name in sorted(texts)},
            "fixture_sha256": dict(sorted(actual.items())),
            "checks": [{"id": name, "status": status} for name, status in checks],
            "verdict": verdict,
            "note": ("Declaration-only presentation. No core mutation, paid tiers, "
                     "accounts, telemetry or duplicate always-on services. "
                     "No real guest or Software Center runtime was executed."),
        }
        (EVIDENCE / "verification_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    return 0 if verdict == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    view_cmd = sub.add_parser("view", help="present the five P0 ecosystem cards")
    view_cmd.add_argument("--json", action="store_true")
    view_cmd.add_argument("--file", default=SNAPSHOT)
    sub.add_parser("verify", help="run bounded static/synthetic checks")
    pin_cmd = sub.add_parser("pin", help="regenerate the fixture SHA-256 manifest")
    pin_cmd.add_argument("--yes", action="store_true")
    verify_cmd = sub.add_parser("verify-write", help="verify and write evidence")
    verify_cmd.set_defaults(write_report=True)
    args = parser.parse_args(argv)
    if args.command == "view":
        view = build_center_view(load_json(FIXTURES / args.file))
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
