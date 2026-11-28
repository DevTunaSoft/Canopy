#!/usr/bin/env python3
"""Bounded static/synthetic verifier and read-only probe CLI for LacOS P0 sources.

Subcommands:
  probe                 emit read-only host tool-presence facts (JSON/text)
  manifest --file PATH  evaluate an untrusted manifest declaration
  verify                run bounded positive and negative checks over fixtures
  pin                   regenerate the fixture SHA-256 manifest (maintainer use)

Nothing here installs software, changes a package database, mutates the booted
core, starts a service, contacts a network or approves a real guest.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canopy_features.software_sources import (  # noqa: E402
    CAPABILITIES_BY_ECOSYSTEM,
    ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    collect_host_facts,
    evaluate_manifest,
    evaluate_probe,
)

FIXTURES = ROOT / "scratch" / "lacos_sources" / "fixtures"
EVIDENCE = ROOT / "scratch" / "lacos_sources" / "evidence"
PRODUCTION = ROOT / "canopy_features" / "software_sources"
MAX_JSON_BYTES = 65_536
EXPECTED_NEGATIVE_CASES = 18
FORBIDDEN_ROOTS = frozenset(("subprocess", "socket", "urllib", "requests", "http"))
WRITE_METHODS = frozenset((
    "write_text", "write_bytes", "mkdir", "unlink", "rmtree", "chmod",
    "write", "writelines", "rename", "replace", "touch", "symlink_to",
))


def static_flags(text):
    """Detect real call/import sites in production source, not docstrings."""
    tree = ast.parse(text)
    live = False
    write = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] in FORBIDDEN_ROOTS
                   for alias in node.names):
                live = True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in FORBIDDEN_ROOTS:
                live = True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in ("Popen", "urlopen", "eval", "exec", "open"):
                    if func.id == "open":
                        write = True
                    else:
                        live = True
            elif isinstance(func, ast.Attribute):
                root = func.value.id if isinstance(func.value, ast.Name) else ""
                if root == "os" and func.attr in ("system", "popen", "execv", "spawnv"):
                    live = True
                if func.attr in WRITE_METHODS:
                    write = True
    return live, write


def load_json(path: Path):
    """Read one bounded JSON fixture; fail closed on size or parse errors."""
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"fixture missing or oversized: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_dict(report):
    return {
        "status": report.status,
        "target": report.target,
        "decisions": [
            {
                "ecosystem": d.ecosystem,
                "status": d.status,
                "capabilities": sorted(d.capabilities),
                "source_ids": list(d.source_ids),
                "isolation": d.isolation,
            }
            for d in report.decisions
        ],
        "violations": list(report.violations),
        "detail": report.detail,
    }


def probe_dict(report):
    return {
        "status": report.status,
        "context": report.context,
        "evidence_class": report.evidence_class,
        "guest_acceptance": report.guest_acceptance,
        "decisions": [
            {
                "ecosystem": d.ecosystem,
                "status": d.status,
                "reasons": list(d.reasons),
                "capabilities": sorted(d.capabilities),
            }
            for d in report.decisions
        ],
        "grants": {key: list(value) for key, value in report.grants.items()},
        "reasons": list(report.reasons),
    }


def _record(checks, name, passed):
    checks.append((name, "PASS" if passed else "FAIL"))


def _fixture_hashes():
    pin = FIXTURES / "SHA256SUMS"
    if not pin.is_file() or pin.stat().st_size > MAX_JSON_BYTES:
        return {}
    result = {}
    for line in pin.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            result[parts[1]] = parts[0]
    return result


def pin_hashes():
    """Write a hash manifest for all fixture inputs except the manifest itself."""
    names = sorted(
        path.name for path in FIXTURES.iterdir()
        if path.is_file() and path.name != "SHA256SUMS")
    lines = []
    for name in names:
        digest = hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (FIXTURES / "SHA256SUMS").write_text("\n".join(lines) + "\n",
                                          encoding="utf-8", newline="\n")
    return len(names)


def verify(write_report=False):
    checks = []
    pinned = _fixture_hashes()
    actual = {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
              for name in pinned if (FIXTURES / name).is_file()}
    _record(checks, "FIXTURE_HASHES", bool(pinned) and pinned == actual)

    sources = sorted(PRODUCTION.glob("*.py"))
    texts = {path.name: path.read_text(encoding="utf-8") for path in sources}
    flags = [static_flags(text) for text in texts.values()]
    _record(checks, "STATIC_NO_TOOL_EXEC", bool(sources)
            and not any(live for live, _ in flags))
    _record(checks, "STATIC_NO_WRITE_IO", bool(sources)
            and not any(write for _, write in flags))
    _record(checks, "STATIC_FIVE_ECOSYSTEMS", set(ECOSYSTEM_IDS) ==
            frozenset(("apt_deb", "dnf_rpm", "flatpak_flathub",
                       "pacman", "rootless_podman_oci")))
    _record(checks, "STATIC_FORBIDDEN_CAPABILITIES",
            {"core_mutation", "host_repo_mixing", "partial_upgrade",
             "privileged", "telemetry", "paid_tier", "always_on"}
            <= FORBIDDEN_CAPABILITIES)

    valid_manifest = evaluate_manifest(load_json(FIXTURES / "manifest_valid.json"))
    _record(checks, "MANIFEST_VALID", valid_manifest.ok)
    _record(checks, "MANIFEST_ALL_DECLARED",
            all(d.status == "DECLARED" for d in valid_manifest.decisions)
            and len(valid_manifest.decisions) == 5)

    host_facts = load_json(FIXTURES / "probe_host.json")
    host = evaluate_probe(valid_manifest, host_facts)
    _record(checks, "PROBE_HOST_NO_GRANTS",
            not host.grants
            and all(d.status == "HOST_ONLY" for d in host.decisions)
            and host.guest_acceptance == "NOT_RUN")

    guest_facts = load_json(FIXTURES / "probe_guest_synthetic.json")
    guest = evaluate_probe(valid_manifest, guest_facts)
    expected_grants = {key: sorted(value)
                       for key, value in CAPABILITIES_BY_ECOSYSTEM.items()}
    _record(checks, "PROBE_GUEST_SYNTHETIC_GRANTS",
            guest.status == "VALID"
            and {key: sorted(value) for key, value in guest.grants.items()}
            == expected_grants
            and all(d.status == "READY" for d in guest.decisions))
    _record(checks, "NO_REAL_GUEST_ACCEPTANCE",
            guest.guest_acceptance == "NOT_RUN"
            and host.guest_acceptance == "NOT_RUN")

    cases = load_json(FIXTURES / "negative_cases.json")
    _record(checks, "NEGATIVE_COUNT_BOUND",
            isinstance(cases, dict) and len(cases) == EXPECTED_NEGATIVE_CASES)
    for name in sorted(cases):
        expected = cases[name]
        fixture = FIXTURES / "negative" / name
        if name.startswith("manifest_"):
            report = evaluate_manifest(load_json(fixture))
            codes = list(report.violations)
        elif name.startswith("probe_"):
            report = evaluate_probe(valid_manifest, load_json(fixture))
            codes = list(report.reasons)
        else:
            codes = []
        _record(checks, "NEGATIVE_" + name[:-5].upper(), expected in codes)

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
            "production_sha256": {
                name: hashlib.sha256((PRODUCTION / name).read_bytes()).hexdigest()
                for name in sorted(texts)
            },
            "fixture_sha256": dict(sorted(actual.items())),
            "checks": [{"id": name, "status": status} for name, status in checks],
            "verdict": verdict,
        }
        (EVIDENCE / "verification_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    return 0 if verdict == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    probe_cmd = sub.add_parser("probe", help="read-only tool-presence probe")
    probe_cmd.add_argument("--context", choices=("host", "guest"), default="host")
    probe_cmd.add_argument("--json", action="store_true")

    manifest_cmd = sub.add_parser("manifest", help="evaluate a manifest JSON file")
    manifest_cmd.add_argument("--file", required=True)

    sub.add_parser("verify", help="run bounded static/synthetic checks")
    pin_cmd = sub.add_parser("pin", help="regenerate fixture SHA-256 manifest")
    pin_cmd.add_argument("--yes", action="store_true",
                         help="required confirmation for the maintainer write")
    verify_cmd = sub.add_parser("verify-write", help="verify and write evidence")
    verify_cmd.set_defaults(write_report=True)

    args = parser.parse_args(argv)
    if args.command == "probe":
        facts = collect_host_facts(args.context)
        if args.json:
            print(json.dumps(facts, indent=2, sort_keys=True))
        else:
            present = sum(1 for item in facts["ecosystems"].values()
                          if item["tool_present"])
            print(f"SOURCES_PROBE_{args.context.upper()}: tools_present={present}/5 "
                  "signature_check=NOT_RUN guest_acceptance=NOT_RUN")
        return 0
    if args.command == "manifest":
        path = Path(args.file)
        print(json.dumps(manifest_dict(evaluate_manifest(load_json(path))),
                         indent=2, sort_keys=True))
        return 0
    if args.command == "pin":
        if not args.yes:
            print("PIN\tBLOCKED\tpass --yes to rewrite fixture hashes")
            return 1
        print(f"PIN\tfiles={pin_hashes()}")
        return 0
    if args.command == "verify":
        return verify()
    return verify(write_report=True)


if __name__ == "__main__":
    raise SystemExit(main())
