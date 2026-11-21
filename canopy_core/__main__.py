"""Offline shell catalog discovery: python -m canopy_core PATH [--json]."""

import argparse
import json
from pathlib import Path
import sys

from .registry import scan_shell_packs
from tools.check_shell_pack import PackValidationError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="local directory of pack folders")
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    args = parser.parse_args(argv)
    try:
        result = scan_shell_packs(args.directory)
    except (PackValidationError, OSError) as exc:
        print(f"CANOPY_PACK_SCAN_FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        record = {
            "schema_version": 1,
            "metadata_only": True,
            "runtime_loading_enabled": False,
            "count": len(result.packs),
            "packs": [{
                "id": pack.pack_id,
                "name": pack.name,
                "description": pack.description,
                "shell_api": pack.shell_api,
                "ui_engine": pack.ui_engine,
                "capabilities": sorted(pack.capabilities),
                "trusted": False,
            } for pack in result.packs],
            "problems": [{
                "location": problem.location,
                "reason": problem.reason,
            } for problem in result.problems],
        }
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(f"Canopy shell catalog: {len(result.packs)} valid metadata entries "
              "(NOT trusted or runnable)")
        for pack in result.packs:
            print(f"- {pack.name} [{pack.pack_id}]")
        for problem in result.problems:
            print(f"REJECTED {problem.location}: {problem.reason}", file=sys.stderr)

    return 1 if result.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
