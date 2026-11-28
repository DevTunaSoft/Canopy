"""Helpers for reading bounded synthetic fixtures (tools only, no guest I/O)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from canopy_features.app_isolation import (  # noqa: E402
    MAX_DOC_BYTES,
    AppIsolationError,
    parse_request_document,
)

FIXTURE_DIR = (Path(__file__).resolve().parents[2] / "scratch"
               / "lacos_app_isolation" / "fixtures")
EVIDENCE_DIR = (Path(__file__).resolve().parents[2] / "scratch"
                / "lacos_app_isolation" / "evidence")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_document(path: Path, document: Any) -> None:
    """Write one deterministic canonical JSON document under scratch only."""
    resolved = Path(os.path.abspath(path))
    if not (resolved.resolve().is_relative_to(FIXTURE_DIR.resolve())
            or resolved.resolve().is_relative_to(EVIDENCE_DIR.resolve())):
        raise AppIsolationError("write target is outside owned scratch")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True) + "\n").encode("utf-8")
    if len(payload) > MAX_DOC_BYTES:
        raise AppIsolationError("document exceeds byte bound")
    resolved.write_bytes(payload)


def fixture_bytes(name: str) -> bytes:
    """Read one bounded fixture byte-for-byte; refuse links and traversal."""
    if not isinstance(name, str) or name != os.path.basename(name):
        raise AppIsolationError("invalid fixture name")
    path = FIXTURE_DIR / name
    if path.is_symlink() or not path.is_file():
        raise AppIsolationError("fixture is missing or a link")
    if any(parent.is_symlink() for parent in path.parents if parent.exists()):
        raise AppIsolationError("fixture parent is a link")
    payload = path.read_bytes()
    if not payload or len(payload) > MAX_DOC_BYTES:
        raise AppIsolationError("fixture bytes are out of bounds")
    return payload


def load_request(name: str):
    """Parse a fixture into a validated IsolationRequest, fail closed."""
    return parse_request_document(fixture_bytes(name))


def expected_failures() -> Dict[str, str]:
    """Fixture names whose parse or decision is intentionally negative."""
    return {name: "NEGATIVE" for name in (
        "F010_unsigned.json", "F011_foreign_provenance.json",
        "F012_core_mutation.json", "F013_duplicate_sandbox.json",
        "F014_duplicate_service.json", "F015_paid_tier.json",
        "F016_telemetry.json", "F017_account.json",
        "F018_host_context.json", "F019_real_guest.json",
        "F020_write_without_review.json", "F021_unknown_permission.json",
        "F022_wrong_ecosystem_source.json", "F023_mech_non_upstream.json",
        "F024_hostile_duplicate_key.json", "F025_huge_integer.json",
    )}
