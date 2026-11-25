"""Reconcile reversal of partially installed, owned files only.

An interrupted install can leave a subset of the files an installer owns on
disk. This module removes only files whose bytes still match the exact hash
recorded at install time. Foreign entries -- different bytes, symlinks,
directories, oversized or unreadable files -- are never removed.

Ownership follows the hash-verified model already used by
``tools/register_classic_preview.py`` (``ownership.json`` plus exact-byte
check); this module does not modify that tool or any GUI/asset file.

No polling, background services, privilege escalation, network calls or
unbounded reads. Callers supply the owned set; parent directories are kept.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

MAX_OWNED_BYTES = 8 * 1024 * 1024
_CHUNK = 64 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class RollbackError(ValueError):
    """Invalid declaration of owned files."""


@dataclass(frozen=True)
class OwnedFile:
    """One installer-owned file and the SHA-256 of the bytes it wrote."""

    path: Path
    sha256: str

    def __post_init__(self):
        if not isinstance(self.path, Path):
            raise RollbackError("owned path must be a pathlib.Path")
        if not self.path.is_absolute():
            raise RollbackError("owned path must be absolute")
        if not isinstance(self.sha256, str) or not _HASH.fullmatch(self.sha256):
            raise RollbackError("owned sha256 must be 64 lowercase hex chars")


@dataclass(frozen=True)
class ReconcileResult:
    """What reconciliation observed and acted on."""

    removed: tuple
    retained: tuple
    kept_foreign: tuple
    missing: tuple
    partial: bool


def _sha256(path):
    """Return the digest of a bounded regular file, or None if unverifiable."""
    try:
        if path.is_symlink() or not path.exists() or not path.is_file():
            return None
        if path.stat().st_size > MAX_OWNED_BYTES:
            return None
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                total += len(chunk)
                if total > MAX_OWNED_BYTES:
                    return None
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, ValueError):
        # Cannot verify => never remove. Fail closed on unreadable entries.
        return None


def _classify(item):
    if item.path.is_symlink():
        return "foreign"
    if not item.path.exists():
        return "missing"
    digest = _sha256(item.path)
    if digest is None:
        return "foreign"
    return "ours" if digest == item.sha256 else "foreign"


def reconcile_partial(owned):
    """Reverse a partial install, removing only provably owned files.

    ``partial`` is true when at least one owned file still holds our exact
    bytes and at least one other owned path is missing or foreign. A complete
    install (all owned files match) is left intact for the normal uninstall
    path. An install with nothing ours to remove is a no-op.
    """
    owned = tuple(owned)
    if not owned:
        raise RollbackError("owned set must not be empty")
    seen = set()
    for item in owned:
        if not isinstance(item, OwnedFile):
            raise RollbackError("owned entries must be OwnedFile instances")
        if item.path in seen:
            raise RollbackError("duplicate owned path")
        seen.add(item.path)

    states = [(item, _classify(item)) for item in owned]
    ours = sum(1 for _, state in states if state == "ours")
    partial = 0 < ours < len(owned)

    removed, retained, foreign, missing = [], [], [], []
    for item, state in states:
        if state == "missing":
            missing.append(item.path)
        elif state == "foreign":
            foreign.append(item.path)
        elif not partial:
            retained.append(item.path)
        else:
            # Re-verify immediately before unlink to shrink the window in
            # which a foreign file could be swapped in. A concurrent
            # adversarial swap between check and unlink is out of scope for
            # this unprivileged, single-user reconciliation tool.
            if _classify(item) == "ours":
                try:
                    item.path.unlink()
                    removed.append(item.path)
                except OSError:
                    foreign.append(item.path)
            else:
                foreign.append(item.path)

    return ReconcileResult(
        removed=tuple(removed),
        retained=tuple(retained),
        kept_foreign=tuple(foreign),
        missing=tuple(missing),
        partial=partial,
    )
