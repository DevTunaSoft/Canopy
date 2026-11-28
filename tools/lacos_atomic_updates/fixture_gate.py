#!/usr/bin/env python3
"""Run synthetic atomic-update fixtures through the read-only contract.

Dependency-free and deterministic. Reads only committed fixture JSON under
``scratch/lacos_atomic_updates/fixtures``, never a guest, host deployment,
package manager, process or network. Writes an evidence report only when
``--out`` is supplied.

Exit 0 means every fixture's expected decision matched the decision computed
by the contract; exit 1 means at least one mismatch or invalid fixture. A PASS
here is a SYNTHETIC contract-gate result, never a real update PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canopy_features.atomic_updates.contract import (  # noqa: E402
    AtomicUpdatesError,
    CONTRACT_VERSION,
    GUEST_BLOCKED,
    GUEST_NOT_RUN,
    SYNTHETIC_LABEL,
)
from canopy_features.atomic_updates.fixture import evaluate_fixture, parse_fixture  # noqa: E402

DEFAULT_FIXTURES = ROOT / "scratch" / "lacos_atomic_updates" / "fixtures"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(fixture_dir: Path, out: Path | None = None) -> tuple[int, dict[str, object]]:
    paths = sorted(fixture_dir.glob("*.json"))
    if not paths:
        raise SystemExit(f"No synthetic fixtures found in {fixture_dir}")

    rows: list[dict[str, object]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        row: dict[str, object] = {
            "fixture": path.name,
            "sha256": _sha256(text),
            "label": SYNTHETIC_LABEL,
            "guest_status": GUEST_NOT_RUN,
            "executed": False,
        }
        try:
            fixture = parse_fixture(text)
            decision = evaluate_fixture(fixture)
            expected = fixture.expect
            actual = decision.status
            row.update(
                {
                    "expected": expected,
                    "actual": actual,
                    "reasons": list(decision.reasons),
                    "steps": len(decision.steps),
                    "all_steps_unexecuted": all(not step.executed for step in decision.steps),
                    "verdict": "PASS" if expected == actual else "FAIL",
                }
            )
        except AtomicUpdatesError as exc:
            row.update({"expected": None, "actual": None, "reasons": [str(exc)], "verdict": "FAIL"})
        rows.append(row)

    passed = sum(1 for row in rows if row["verdict"] == "PASS")
    report: dict[str, object] = {
        "gate": "lacos-atomic-updates-synthetic-fixture-gate",
        "contract_version": CONTRACT_VERSION,
        "evidence_class": "SYNTHETIC",
        "guest_status": f"{GUEST_BLOCKED}/{GUEST_NOT_RUN}",
        "real_guest_update": "BLOCKED",
        "real_guest_rollback": "NOT_RUN",
        "fixture_root": str(fixture_dir),
        "fixtures_total": len(rows),
        "fixtures_passed": passed,
        "fixtures_failed": len(rows) - passed,
        "verdict": "PASS" if passed == len(rows) else "FAIL",
        "rows": rows,
    }
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(
        f"{report['verdict']}: {passed}/{len(rows)} synthetic fixtures matched; "
        f"guest={report['guest_status']}"
    )
    for row in rows:
        print(f"  {row['verdict']} {row['fixture']}: expected={row['expected']} actual={row['actual']}")
    return 0 if report["verdict"] == "PASS" else 1, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    rc, _ = run(args.fixtures, args.out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
