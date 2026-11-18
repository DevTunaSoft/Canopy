"""Bounded guest result envelope for a future trusted host-side verifier.

Does not expose a network service or accept arbitrary commands. Guest
evidence is self-reported and MUST NOT become independent host attestation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[0-9a-f]{32}\Z")
STATUS = {"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE", "NOT_RUN"}
MAX_FILE = 1_000_000


def digest(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE:
        raise ValueError("Guest result file too large")
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            value.update(block)
    return value.hexdigest()


def wrap(*, commit, run_id, boot_id, report, status=None):
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise ValueError("Invalid commit")
    if not isinstance(run_id, str) or not ID.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    if not isinstance(boot_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", boot_id):
        raise ValueError("Invalid Linux boot ID")
    report = Path(report)
    if report.is_symlink() or not report.is_file():
        raise ValueError("Report must be a regular file, not a symlink")
    raw = report.read_bytes()
    if len(raw) > MAX_FILE:
        raise ValueError("Oversized report")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or parsed.get("schema_version") != 1:
        raise ValueError("Invalid report schema")
    reported = parsed.get("status")
    if reported not in STATUS:
        raise ValueError("Unknown report status")
    if status is not None and status != reported:
        raise ValueError("Claimed and reported statuses disagree")
    return {"schema_version": 1, "kind": "UNTRUSTED_GUEST_EVIDENCE",
            "commit": commit, "run_id": run_id, "boot_id": boot_id,
            "status": reported, "report_bytes": len(raw),
            "report_sha256": hashlib.sha256(raw).hexdigest(),
            "host_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bind untrusted guest report to test run")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--boot-id-file", type=Path,
                        default=Path("/proc/sys/kernel/random/boot_id"))
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        boot_id = args.boot_id_file.read_text(encoding="ascii").strip()
        envelope = wrap(commit=args.commit, run_id=args.run_id,
                        boot_id=boot_id, report=args.report)
        if args.output.resolve() == args.report.resolve():
            raise ValueError("Envelope output must differ from source report")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(envelope, handle, indent=2)
            handle.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print("Untrusted guest envelope created; independent host verification pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
