"""Host-owned run ledger with immutable evidence names and bounded retries.

This module doesn't open sockets, execute guest commands, or trust guest status.
The host must collect exit codes and artifact digests independently.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys

SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_BYTES = 5_000_000
STATES = {"CREATED", "RUNNING", "PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"}


def new_run(commit, *, nonce=None):
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise ValueError("Full immutable lowercase Git SHA required")
    identifier = secrets.token_hex(16) if nonce is None else nonce
    if not isinstance(identifier, str) or not RUN_ID.fullmatch(identifier):
        raise ValueError("Invalid 128-bit run identifier")
    return {"schema_version": 1, "run_id": identifier, "commit": commit,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "state": "CREATED", "attempts": 0, "artifacts": []}


def record_artifact(run, name, path):
    """Require artifacts to live outside guest checkout; bound size/hash only."""
    if run["state"] not in {"CREATED", "RUNNING", "FAIL", "INCONCLUSIVE"}:
        raise ValueError("Cannot add artifacts to completed run")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
        raise ValueError("Invalid artifact name")
    if any(x["name"] == name for x in run["artifacts"]):
        raise ValueError("Duplicate evidence name")
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ValueError("Evidence exceeds size cap")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    if path.stat().st_size != size:
        raise ValueError("Artifact changed while hashing")
    run["artifacts"].append({"name": name, "bytes": size, "sha256": digest.hexdigest()})
    return run


def advance(run, state, *, max_attempts=3):
    if state not in STATES or not 1 <= max_attempts <= 5:
        raise ValueError("Invalid transition configuration")
    previous = run.get("state")
    if previous in {"PASS", "BLOCKED"} or state == "CREATED":
        raise ValueError("Invalid terminal state transition")
    if state == "RUNNING":
        if previous not in {"CREATED", "FAIL", "INCONCLUSIVE"} or run["attempts"] >= max_attempts:
            raise ValueError("Retry limit or invalid restart")
        run["attempts"] += 1
    elif previous != "RUNNING":
        raise ValueError("Results require a running attempt")
    if state == "PASS" and not run["artifacts"]:
        raise ValueError("PASS requires independently hashed evidence")
    run["state"] = state
    return run


def save_new(path, run):
    """Exclusive creation avoids quietly overwriting old run identity."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(run, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create host-side Canopy evidence run identity")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run = new_run(args.commit)
        path = save_new(args.output_dir / (run["run_id"] + ".json"), run)
    except (OSError, ValueError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
