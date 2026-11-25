"""Verify old and new installation ownership before a user-level Canopy upgrade.

Offline, standard-library only and unprivileged. This is a preflight verifier,
not an installer: it writes no files, launches no apps and changes no state.
It reuses the reversible Classic preview ownership marker and SHA-256 checks
from ``tools.register_classic_preview`` instead of inventing a second scheme.

Two checks gate an upgrade:

* old installation is still exactly owned by Canopy -- the registered desktop
  entry must match the SHA-256 in its ``ownership.json`` marker;
* new candidate is internally consistent -- its payload must match the digest
  declared in its release manifest, and its version must be newer than the
  installed version (no rollback).

A digest match proves integrity, not cryptographic authenticity. Signing and
a trust root are future integration work. The installed version is supplied
by the caller and must be bound to owned state before a real updater ships.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import NamedTuple

from tools import register_classic_preview as installer

SCHEMA = 1
MANIFEST_KEYS = frozenset({"schema", "version", "payload_sha256"})
MAX_MANIFEST_BYTES = 8192
CHUNK = 1 << 20
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*\Z")


class UpgradeError(ValueError):
    """Raised when an upgrade may not proceed. Fail closed."""


class UpgradeDecision(NamedTuple):
    old_version: str
    new_version: str


def parse_version(text):
    """Return a tuple of ints for a dotted numeric version, or fail closed."""
    if not isinstance(text, str) or not _VERSION.fullmatch(text):
        raise UpgradeError("invalid version: " + repr(text))
    parts = tuple(int(p) for p in text.split("."))
    if any(p > 0x7fffffff for p in parts):
        raise UpgradeError("version component out of range")
    return parts


def _sha_file(path):
    """Stream a file through SHA-256 so memory stays bounded."""
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
    except (OSError, ValueError) as exc:
        raise UpgradeError("candidate payload unreadable") from exc
    return digest.hexdigest()


def read_manifest(manifest_path):
    """Validate a new release manifest; return (version_tuple, digest)."""
    path = Path(manifest_path)
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > MAX_MANIFEST_BYTES):
        raise UpgradeError("invalid candidate manifest")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise UpgradeError("candidate manifest unreadable") from exc
    if not isinstance(data, dict) or set(data) != MANIFEST_KEYS:
        raise UpgradeError("candidate manifest has unexpected fields")
    if type(data["schema"]) is not int or data["schema"] != SCHEMA:
        raise UpgradeError("unsupported candidate manifest schema")
    version = parse_version(data["version"])
    digest = data["payload_sha256"]
    if not isinstance(digest, str) or not installer.HASH.fullmatch(digest):
        raise UpgradeError("invalid candidate payload digest")
    return version, digest


def verify_installed_ownership(home):
    """Reuse the Classic preview marker check for the installed copy."""
    state = installer.status(home)
    if state != "INSTALLED":
        raise UpgradeError("old installation not owned: " + state)
    return state


def verify_candidate(payload, manifest):
    """Check new payload against its manifest; return its version tuple."""
    version, digest = read_manifest(manifest)
    if _sha_file(payload) != digest:
        raise UpgradeError("candidate payload does not match its ownership manifest")
    return version


def verify_upgrade(home, installed_version, payload, manifest):
    """Return a decision only when old/new ownership and version all pass."""
    verify_installed_ownership(home)
    old_text = installed_version
    old = parse_version(old_text)
    new = verify_candidate(payload, manifest)
    if new <= old:
        raise UpgradeError("version rollback refused: %s -> %s"
                           % (old_text, ".".join(map(str, new))))
    return UpgradeDecision(old_version=old_text,
                           new_version=".".join(map(str, new)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--home", required=True, type=Path)
    check.add_argument("--installed-version", required=True)
    check.add_argument("--payload", required=True, type=Path)
    check.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        decision = verify_upgrade(args.home, args.installed_version,
                                 args.payload, args.manifest)
    except (UpgradeError, installer.RegistrationError, OSError, ValueError) as exc:
        print("CANOPY_UPGRADE_REFUSED:", exc, file=sys.stderr)
        return 1
    print("CANOPY_UPGRADE_ALLOWED:", decision.old_version, "->",
          decision.new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
