#!/usr/bin/env python3
"""Bounded OFFLINE verifier for performance snapshot digest pins.

The merged bundle gate only *format-checks* caller-supplied SHA pins; it never
checks that a pin matches the artifact it claims to describe. This module
closes that gap by composing the already-tested
``tools.qa.perf_snapshot_digest``: it RECOMPUTES the canonical content address
of a snapshot artifact and compares it with a caller-supplied pin.

A match proves byte identity of that offline record only. It is not signed
provenance and never affirms real hardware measurement, Linux Mint acceptance,
release approval or owner visual approval; every negative claim is hardcoded
in the report serializer. No caller value is echoed into an error or report.

The file reader is bounded, absolute-path-only and symlink-safe, with the
whole descriptor path inside one ``OSError`` boundary (POSIX ``os.open()`` can
accept a directory and fail later at ``fdopen()``). Malformed, drifted,
unbounded or claim-flipped input raises :class:`VerifyError` with a fixed
message.
"""
import argparse
import hmac
import json
import os
from pathlib import Path
import stat
import sys

# Direct script execution and package import both work without duplicating
# the composed module's logic.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.qa import perf_snapshot_digest as digest_gate

SCHEMA = 1
MAX_VERIFY_BYTES = 65_536
TOP_KEYS = frozenset({"schema", "artifact", "sha256", "byte_length"})
STATUSES = frozenset({"MATCH", "MISMATCH"})


class VerifyError(ValueError):
    """Invalid, drifted, unbounded or claim-flipped verification input."""


def _bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise VerifyError("verification " + label + " is invalid or unbounded")
    return value


def _pin(value):
    # Type-check BEFORE the regex lookup: an unhashable/wrong type must not
    # leak a raw TypeError instead of this fail-closed VerifyError.
    if type(value) is not str or not digest_gate.SHA256.fullmatch(value):
        raise VerifyError("verification SHA-256 pin is malformed")
    return value


def _reject_constant(token):
    raise VerifyError("verification JSON contains a non-finite number")


class VerifyReport:
    """Frozen status-only record of one digest verification."""

    __slots__ = ("_status",)

    def __init__(self, status):
        object.__setattr__(self, "_status", status)

    def __setattr__(self, name, value):
        raise AttributeError("verification report is immutable")

    @property
    def status(self):
        return self._status

    def __eq__(self, other):
        if not isinstance(other, VerifyReport):
            return NotImplemented
        return self._status == other._status

    def __hash__(self):
        return hash(self._status)

    def as_dict(self):
        """Return a fresh copy with a fixed status token and hardcoded claims.

        The status is validated here too, so a directly constructed (forged)
        record cannot emit an unknown token or an approval.
        """
        status = self._status
        # Type-check before membership for the same reason as _pin().
        if type(status) is not str or status not in STATUSES:
            raise VerifyError("verification report status is invalid")
        return {
            "status": status,
            "schema": SCHEMA,
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "real_hardware_measured": False,
            "owner_visual_approval": False,
            "measurement_performed": False,
        }


def verify_record(record):
    """Validate a verification record and compare the recomputed digest."""
    if type(record) is not dict or frozenset(record) != TOP_KEYS:
        raise VerifyError("verification record has an unexpected key set")
    if _bounded_int(record["schema"], "schema", SCHEMA, SCHEMA) != SCHEMA:
        raise VerifyError("verification schema is unsupported")
    sha = _pin(record["sha256"])
    length = _bounded_int(
        record["byte_length"], "byte length", 1, digest_gate.MAX_CANONICAL_BYTES)
    try:
        computed = digest_gate.digest_artifact(record["artifact"])
    except digest_gate.DigestError as exc:
        raise VerifyError("snapshot artifact rejected") from exc
    matches = (hmac.compare_digest(computed.sha256, sha)
               and computed.byte_length == length)
    return VerifyReport("MATCH" if matches else "MISMATCH")


def verify_json(text):
    """Decode bounded UTF-8 JSON text and verify its digest record."""
    if isinstance(text, bytes):
        data = text
    elif type(text) is str:
        try:
            data = text.encode("utf-8")
        except UnicodeError as exc:
            raise VerifyError("verification text cannot be encoded") from exc
    else:
        raise VerifyError("verification JSON must be text or bytes")
    if not data or len(data) > MAX_VERIFY_BYTES:
        raise VerifyError("verification JSON is missing or oversized")
    try:
        parsed = json.loads(
            data.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise VerifyError("verification JSON could not be parsed") from exc
    return verify_record(parsed)


def verify_file(path):
    """Read a bounded, symlink-safe regular file and verify its JSON."""
    p = Path(path)
    if not p.is_absolute():
        raise VerifyError("absolute verification path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise VerifyError("symlinked verification path rejected")
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise VerifyError("verification path is not a regular file")
            data = handle.read(MAX_VERIFY_BYTES + 1)
    except OSError as exc:
        raise VerifyError("verification file missing or unsafe") from exc
    if not data or len(data) > MAX_VERIFY_BYTES:
        raise VerifyError("verification JSON is missing or oversized")
    return verify_json(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_file(args.record).as_dict()
    except VerifyError as exc:
        print("QT_PERF_DIGEST_VERIFY_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    if result["status"] != "MATCH":
        print("QT_PERF_DIGEST_VERIFY_FAIL: digest mismatch", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
