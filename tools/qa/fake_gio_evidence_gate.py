"""Deterministic evidence gate for the synthetic fake-GIO launch fixture.

Reads the logs produced by tools/qa/fake_gio_launch_fixture/run_fixture.sh and
fails closed unless all twelve cases, the six desktop-ID mappings, the four
GIO refusal paths, the no-GIO refusal and the unmodified production source
hashes are exactly as contracted. The emitted JSON is explicitly labelled
SYNTHETIC / not Mint; it is not real-GIO, desktop, visual or screen-reader
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from typing import Dict, List, Optional, Sequence


class FakeGioEvidenceError(ValueError):
    """Domain error: fixture logs do not prove the exact case contract."""


SOURCE_SHA256 = {
    "SystemAppLauncher.cpp": (
        "b397916b6e2b2dc2664972722a7a77185d80be7f52bc28325d3fc62f816e6a03"
    ),
    "SystemAppLauncher.h": (
        "6b987962f5b77b4deee802efff301cc1f3fa2a970cba269fa2f7c7d3e349e05f"
    ),
}

_MAPPING_CALLS = {
    "Browser": "firefox.desktop",
    "Terminal": "gnome-terminal.desktop",
    "Calendar": "org.gnome.Calendar.desktop",
    "Photos": "pix.desktop",
    "Mail": "thunderbird.desktop",
    "Files": "nemo.desktop",
}

EXPECTED_MAPPING_CALLS = {
    "mapping:" + label: [
        "new " + desktop_id,
        "should_show " + desktop_id,
        "new " + desktop_id,
        "should_show " + desktop_id,
        "launch " + desktop_id,
    ]
    for label, desktop_id in _MAPPING_CALLS.items()
}
EXPECTED_MAPPING_CALLS["mapping:Browser-fallback-order"] = [
    "new firefox.desktop",
    "new org.mozilla.firefox.desktop",
    "should_show org.mozilla.firefox.desktop",
    "new firefox.desktop",
    "new org.mozilla.firefox.desktop",
    "should_show org.mozilla.firefox.desktop",
    "launch org.mozilla.firefox.desktop",
]

EXPECTED_REFUSAL_DETAILS = {
    "refusal:opt-in-disabled": "gio_calls=0",
    "refusal:unknown-action": "gio_calls=0 message=1",
    "refusal:unavailable": "can=0 launch=0 new_calls=12",
    "refusal:launch-failure-no-fallback": "can=1 launch=0 launch_calls=1",
    "refusal:no-gio-fallback-build": "7 labels x (canLaunch,launch) all false",
}

FIXTURE_CASE_NAMES = list(EXPECTED_MAPPING_CALLS) + [
    "refusal:opt-in-disabled",
    "refusal:unknown-action",
    "refusal:unavailable",
    "refusal:launch-failure-no-fallback",
]
FALLBACK_CASE_NAMES = ["refusal:no-gio-fallback-build"]

# Each case resets the shim log; the final log is the last GIO case.
EXPECTED_FINAL_CALL_LOG = [
    "new gnome-terminal.desktop",
    "should_show gnome-terminal.desktop",
    "new gnome-terminal.desktop",
    "should_show gnome-terminal.desktop",
    "launch gnome-terminal.desktop",
]


def _read_text(path: Path, label: str) -> str:
    if not isinstance(path, Path):
        raise FakeGioEvidenceError("path must be a pathlib.Path")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FakeGioEvidenceError(f"cannot read {label}: {path}") from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_report(text: str, expected_names: Sequence[str],
                  expected_summary: str, label: str) -> Dict[str, str]:
    """Parse one CASE_PASS-per-line report, failing closed on any anomaly."""
    if not isinstance(text, str) or not isinstance(expected_names, (list, tuple)):
        raise FakeGioEvidenceError("invalid report arguments")
    details: Dict[str, str] = {}
    summary = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("CASE_FAIL:"):
            raise FakeGioEvidenceError(f"{label}: CASE_FAIL present: {line}")
        if line.startswith("CASE_PASS: "):
            body = line[len("CASE_PASS: "):]
            if " | " not in body:
                raise FakeGioEvidenceError(f"{label}: malformed CASE_PASS: {line}")
            name, detail = body.split(" | ", 1)
            if name in details:
                raise FakeGioEvidenceError(f"{label}: duplicate case {name}")
            details[name] = detail.strip()
        elif line.startswith("SUMMARY: "):
            if summary:
                raise FakeGioEvidenceError(f"{label}: duplicate SUMMARY")
            summary = line
        elif line.startswith("DEBUG_MESSAGES:"):
            continue
        else:
            raise FakeGioEvidenceError(f"{label}: unexpected line: {line}")
    if list(details) != list(expected_names):
        raise FakeGioEvidenceError(
            f"{label}: case set/order mismatch: {list(details)}"
        )
    if summary != expected_summary:
        raise FakeGioEvidenceError(
            f"{label}: expected {expected_summary!r}, got {summary!r}"
        )
    return details


def _check_mapping_calls(name: str, detail: str) -> List[str]:
    prefix = "can=1 launch=1 calls="
    if not detail.startswith(prefix):
        raise FakeGioEvidenceError(f"{name}: unexpected detail {detail!r}")
    calls = detail[len(prefix):].split(" > ")
    expected = EXPECTED_MAPPING_CALLS[name]
    if calls != expected:
        raise FakeGioEvidenceError(
            f"{name}: expected calls {expected!r}, got {calls!r}"
        )
    return calls


def _check_sources(check_text: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for raw in check_text.splitlines():
        parts = raw.split()
        if len(parts) != 2:
            raise FakeGioEvidenceError(f"malformed source hash line: {raw!r}")
        digest, name = parts
        # MSYS2 sha256sum emits "hash *name" (binary marker); Linux emits
        # "hash  name". Accept both, nothing else.
        name = name[1:] if name.startswith("*") else name
        if not name or name in found:
            raise FakeGioEvidenceError(f"duplicate source hash entry: {name}")
        found[name] = digest
    if found != SOURCE_SHA256:
        raise FakeGioEvidenceError("production source SHA-256 set mismatch")
    return dict(found)


def assess(log_dir: Path, verify_sources: bool = True) -> dict:
    """Validate fixture logs and return a bounded synthetic evidence record."""
    if not isinstance(log_dir, Path):
        raise FakeGioEvidenceError("log_dir must be a pathlib.Path")
    fixture_text = _read_text(log_dir / "gio-fixture.log", "gio-fixture.log")
    fallback_text = _read_text(log_dir / "gio-fallback.log", "gio-fallback.log")
    call_text = _read_text(log_dir / "fake-gio-call-log.txt", "call log")

    fixture_cases = _parse_report(
        fixture_text, FIXTURE_CASE_NAMES,
        "SUMMARY: cases=11 result=ALL_PASS", "gio-fixture.log",
    )
    fallback_cases = _parse_report(
        fallback_text, FALLBACK_CASE_NAMES,
        "SUMMARY: cases=1 result=ALL_PASS", "gio-fallback.log",
    )

    mapping: Dict[str, List[str]] = {}
    for name in EXPECTED_MAPPING_CALLS:
        mapping[name] = _check_mapping_calls(name, fixture_cases[name])
    refusals: Dict[str, str] = {}
    for name, expected in EXPECTED_REFUSAL_DETAILS.items():
        source = fallback_cases if name in FALLBACK_CASE_NAMES else fixture_cases
        if source[name] != expected:
            raise FakeGioEvidenceError(
                f"{name}: expected detail {expected!r}, got {source[name]!r}"
            )
        refusals[name] = source[name]

    actual_calls = [line.strip() for line in call_text.splitlines() if line.strip()]
    if actual_calls != EXPECTED_FINAL_CALL_LOG:
        raise FakeGioEvidenceError(
            f"final fake-GIO call log mismatch: {actual_calls!r}"
        )

    sources: Dict[str, str] = {}
    if verify_sources:
        sources = _check_sources(
            _read_text(log_dir / "source-sha256-check.txt", "source sha256 check")
        )

    artifacts = {
        name: _sha256_bytes(path.read_bytes())
        for name, path in (
            ("gio-fixture.log", log_dir / "gio-fixture.log"),
            ("gio-fallback.log", log_dir / "gio-fallback.log"),
            ("fake-gio-call-log.txt", log_dir / "fake-gio-call-log.txt"),
        )
    }
    return {
        "schema": 1,
        "fixture": "synthetic-fake-gio-system-app-launcher",
        "status": "PASS",
        "classification": "SYNTHETIC",
        "linux_mint": False,
        "real_gio": False,
        "real_desktop_launch": False,
        "visual_approval": False,
        "screen_reader": "NOT_RUN",
        "source_sha256": sources,
        "case_count": len(fixture_cases) + len(fallback_cases),
        "mapping": mapping,
        "refusals": refusals,
        "final_call_log": actual_calls,
        "artifact_sha256": artifacts,
        "provenance": (
            "Unmodified SystemAppLauncher sources + fake GIO shim + real Qt6 "
            "Core objects; no GLib/GIO dev package, desktop database, X "
            "server or application process."
        ),
    }


def write_evidence(evidence: dict, output: Path) -> None:
    if not isinstance(output, Path):
        raise FakeGioEvidenceError("output must be a pathlib.Path")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate synthetic fake-GIO fixture logs and emit evidence."
    )
    parser.add_argument("--log-dir", required=True, type=Path,
                        help="directory written by run_fixture.sh")
    parser.add_argument("--output", required=True, type=Path,
                        help="JSON evidence file to write")
    parser.add_argument("--no-source-check", action="store_true",
                        help="skip source hash check (local harness use only)")
    args = parser.parse_args(argv)
    try:
        evidence = assess(args.log_dir, verify_sources=not args.no_source_check)
        write_evidence(evidence, args.output)
    except FakeGioEvidenceError as exc:
        print(f"FAKE_GIO_EVIDENCE_GATE_FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "FAKE_GIO_EVIDENCE_GATE_PASS: "
        f"cases={evidence['case_count']} classification=SYNTHETIC mint=false "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
