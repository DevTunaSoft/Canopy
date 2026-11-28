#!/usr/bin/env python3
"""Run bounded headless M4 display-response fixtures (SYNTHETIC only).

This tool feeds one trusted KWin/KScreen push payload at a time into
``DisplayChangeResponse.handle_native_change``. It starts no service, opens no
socket, polls no display, imports no Qt and never claims a real monitor,
compositor or Mint runtime result. It also reports the frozen dock geometry
tuple read from a caller-supplied QML text without editing that text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_FIXTURE_BYTES = 1_000_000
MAX_SCENARIOS = 64
MAX_STEPS_PER_SCENARIO = 32
BANNED_TOKENS = (
    "import time", "import threading", "asyncio", "QTimer", "while True",
    "sleep(", "subprocess", "socket.", "QGuiApplication",
)
MODULES = (
    "canopy_features/dock/display_change_response.py",
    "canopy_features/dock/geometry.py",
)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key: " + str(key))
        result[key] = value
    return result


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_fixtures(path):
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_FIXTURE_BYTES:
        raise ValueError("fixture file size out of bounds")
    text = raw.decode("utf-8")
    data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("unsupported fixture schema")
    scenarios = data.get("scenarios")
    if type(scenarios) is not list or len(scenarios) > MAX_SCENARIOS:
        raise ValueError("invalid fixture scenario set")
    return data


def _static_checks():
    findings = {}
    for relative in MODULES:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        findings[relative] = {
            token: (token in text) for token in BANNED_TOKENS
        }
    return findings


def run(fixtures_path, theme_path, out_path):
    from canopy_features.dock.display_change_response import (
        DisplayChangeResponse,
    )
    from canopy_features.dock.geometry import (
        APPROVED, APPROVED_DOCK_GEOMETRY, assert_approved, geometry_status,
    )

    fixtures = _load_fixtures(fixtures_path)
    if list(fixtures.get("approved_dock_geometry", ())) != \
            list(APPROVED_DOCK_GEOMETRY):
        raise ValueError("fixture approved geometry diverges from the module")
    assert_approved(APPROVED)

    theme_text = theme_path.read_text(encoding="utf-8")
    status = geometry_status(theme_text)
    static = _static_checks()
    static_ok = all(
        not any(hits.values())
        for hits in static.values()
    )

    results = []
    passed_steps = 0
    total_steps = 0
    for scenario in fixtures["scenarios"]:
        if not isinstance(scenario, dict):
            raise ValueError("scenario must be an object")
        steps = scenario.get("steps")
        if type(steps) is not list or len(steps) > MAX_STEPS_PER_SCENARIO:
            raise ValueError("invalid scenario step set")
        response = DisplayChangeResponse()
        step_results = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError("step must be an object")
            payload = step.get("payload")
            expected = step.get("expect")
            if not isinstance(payload, dict) or not isinstance(expected, dict):
                raise ValueError("step needs payload and expect objects")
            plan = response.handle_native_change(payload)
            actual = {
                "kind": plan.kind,
                "size": list(plan.size),
                "reason": plan.reason,
            }
            wanted = {
                "kind": expected.get("kind"),
                "size": list(expected.get("size", ())),
                "reason": expected.get("reason"),
            }
            ok = actual == wanted
            total_steps += 1
            passed_steps += int(ok)
            payload_blob = json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")
            step_results.append({
                "index": index,
                "payload_sha256": hashlib.sha256(payload_blob).hexdigest(),
                "expected": wanted,
                "actual": actual,
                "passed": ok,
            })
        results.append({
            "id": scenario.get("id"),
            "steps": step_results,
            "passed": all(step["passed"] for step in step_results),
        })

    verdict = "PASS_SYNTHETIC" if (
        static_ok and passed_steps == total_steps and total_steps > 0
    ) else "FAIL"
    evidence = {
        "schema": 1,
        "label": "SYNTHETIC",
        "native_runtime": "BLOCKED_NOT_RUN",
        "headless": True,
        "verdict": verdict,
        "fixtures": {
            "path": str(fixtures_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": _sha256(fixtures_path),
        },
        "theme": {
            "path": str(theme_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": _sha256(theme_path),
        },
        "source_sha256": {
            relative: _sha256(REPO_ROOT / relative) for relative in MODULES
        },
        "geometry": {
            "approved": list(status.approved),
            "observed_in_supplied_theme": list(status.observed),
            "matches_approved": status.matches_approved,
            "approved_fingerprint": status.approved_fingerprint,
            "note": (
                "The approved tuple is read-only. A mismatching supplied QML "
                "text is reported, never rewritten by this tool."
            ),
        },
        "static_checks": {
            "no_polling_or_duplicate_service": static_ok,
            "banned_tokens_found": static,
        },
        "counts": {
            "scenarios": len(results),
            "steps": total_steps,
            "passed_steps": passed_steps,
            "failed_steps": total_steps - passed_steps,
        },
        "scenarios": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("verdict=%s scenarios=%d steps=%d passed=%d evidence=%s" % (
        verdict, len(results), total_steps, passed_steps, out_path))
    return 0 if verdict == "PASS_SYNTHETIC" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures", type=Path,
        default=REPO_ROOT / "scratch" / "native_multimonitor" / "fixtures.json")
    parser.add_argument(
        "--theme", type=Path,
        default=REPO_ROOT / "prototype" / "classic" / "Theme.qml")
    parser.add_argument(
        "--out", type=Path,
        default=REPO_ROOT / "scratch" / "native_multimonitor" /
        "evidence.json")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(REPO_ROOT))
    return run(args.fixtures.resolve(), args.theme.resolve(),
               args.out.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
