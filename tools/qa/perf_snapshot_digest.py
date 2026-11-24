#!/usr/bin/env python3
"""Bounded OFFLINE content-address gate for validated performance snapshots.

A "digest artifact" is the JSON-serializable record produced by
``PerformanceSnapshot.as_dict()`` (``canopy_features/performance``). This
module composes the already-tested offline validator
``tools.qa.perf_snapshot_artifact_validator``: an artifact must validate
before any digest is produced. It then CANONICALIZES the approved artifact
(sorted keys, compact separators, ASCII escaping) and computes one SHA-256
content address over those canonical bytes.

Unlike the bundle gate, which only *format-checks* caller-supplied SHA pins,
this module COMPUTES the digest itself. The digest is diagnostic provenance for
an offline artifact only: it proves byte identity of that record, not real
hardware measurement, Linux Mint acceptance, release approval or owner visual
approval. Every negative claim is hardcoded in the report serializer.

Nothing is measured, executed or launched. No caller value is echoed into an
error or into the report. The file reader is bounded, absolute-path-only and
symlink-safe, with the whole descriptor path inside one ``OSError`` boundary
(POSIX ``os.open()`` accepts a directory and can fail later at ``fdopen()``).
Malformed, drifted, unbounded or claim-flipped input raises
:class:`DigestError` with a fixed message.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

# Support direct script execution (``python tools/qa/<this file>.py``) as well
# as package import (``from tools.qa import ...``) without duplicating the
# validator's logic.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.qa import perf_snapshot_artifact_validator as snapshot_validator

SCHEMA = 1
MAX_ARTIFACT_BYTES = 65_536
# A validated artifact may hold bounded text collections whose canonical
# escaping is larger than the on-disk JSON that produced it (quotes, control
# characters, non-ASCII). This cap keeps the computed bytes bounded without
# rejecting a valid artifact accepted by the owning validator.
MAX_CANONICAL_BYTES = 1_048_576
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class DigestError(ValueError):
    """Invalid, drifted, unbounded or claim-flipped digest input."""


def _bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DigestError("digest " + label + " is invalid or unbounded")
    return value


def _reject_constant(token):
    raise DigestError("digest JSON contains a non-finite number")


def digest_artifact(value):
    """Validate an artifact, then return its frozen SHA-256 content address.

    The sub-validator's detail is chained as the cause, never copied into the
    message. Canonical encoding is bounded and fail-closed.
    """
    try:
        snapshot_validator.validate(value)
    except snapshot_validator.ArtifactError as exc:
        raise DigestError("snapshot artifact rejected") from exc
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise DigestError("artifact is not canonically encodable") from exc
    if not data or len(data) > MAX_CANONICAL_BYTES:
        raise DigestError("canonical artifact is missing or oversized")
    return DigestReport(
        sha256=hashlib.sha256(data).hexdigest(),
        byte_length=len(data),
    )


class DigestReport:
    """Frozen record of one canonical content address."""

    __slots__ = ("_sha256", "_byte_length")

    def __init__(self, sha256, byte_length):
        object.__setattr__(self, "_sha256", sha256)
        object.__setattr__(self, "_byte_length", byte_length)

    def __setattr__(self, name, value):
        raise AttributeError("digest report is immutable")

    @property
    def sha256(self):
        return self._sha256

    @property
    def byte_length(self):
        return self._byte_length

    def __eq__(self, other):
        if not isinstance(other, DigestReport):
            return NotImplemented
        return (self._sha256, self._byte_length) == (
            other._sha256, other._byte_length)

    def __hash__(self):
        return hash((self._sha256, self._byte_length))

    def as_dict(self):
        """Return a fresh JSON-serializable copy with fixed negative claims.

        Fields are validated here as well, so a directly constructed (forged)
        record cannot emit an invalid address or an approval through the public
        serialization path. Every claim field is hardcoded rather than stored.
        """
        sha = self._sha256
        if type(sha) is not str or not SHA256.fullmatch(sha):
            raise DigestError("digest report address is invalid")
        length = _bounded_int(
            self._byte_length, "byte length", 1, MAX_CANONICAL_BYTES)
        return {
            "status": "VALID",
            "schema": SCHEMA,
            "sha256": sha,
            "byte_length": length,
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "real_hardware_measured": False,
            "owner_visual_approval": False,
            "measurement_performed": False,
        }


def digest_json(text):
    """Decode bounded UTF-8 JSON text and digest the validated artifact."""
    if isinstance(text, bytes):
        data = text
    elif type(text) is str:
        try:
            data = text.encode("utf-8")
        except UnicodeError as exc:
            raise DigestError("digest text cannot be encoded") from exc
    else:
        raise DigestError("digest JSON must be text or bytes")
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise DigestError("digest JSON is missing or oversized")
    try:
        parsed = json.loads(
            data.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DigestError("digest JSON could not be parsed") from exc
    return digest_artifact(parsed)


def digest_file(path):
    """Read a bounded, symlink-safe regular file and digest its JSON."""
    p = Path(path)
    if not p.is_absolute():
        raise DigestError("absolute digest path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise DigestError("symlinked digest path rejected")
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise DigestError("digest path is not a regular file")
            data = handle.read(MAX_ARTIFACT_BYTES + 1)
    except OSError as exc:
        raise DigestError("digest file missing or unsafe") from exc
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise DigestError("digest JSON is missing or oversized")
    return digest_json(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        result = digest_file(args.artifact).as_dict()
    except (DigestError, OSError) as exc:
        print("QT_PERF_DIGEST_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
