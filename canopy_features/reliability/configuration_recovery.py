"""Offline validation and safe recovery for versioned Canopy config backups.

The versioned config is the SHA-locked approved manifest (schema v1) plus the
asset tree it references. Validation completes before any write. Recovery
publishes a fully verified tree in one rename and never follows symlinks.

This is a library primitive. It does not load QML, start the Qt shell, or prove
Linux Mint behavior; that integration remains separate work.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
import uuid

from tools.prepare_approved_art import (
    MANIFEST,
    ArtworkError,
    check_exact,
    read_manifest,
)

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
MAX_ENTRIES = 64
STAGING_PREFIX = ".canopy-config-recovery-"
INTERRUPTED_MARKERS = (".tmp", ".part", ".partial", ".canopy-")


class RecoveryError(ValueError):
    """Raised when a recovery cannot be performed safely."""


@dataclass(frozen=True)
class BackupReport:
    ok: bool
    version: int | None
    reason: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryOutcome:
    status: str
    version: int
    quarantined: Path | None


def _invalid(reason: str) -> BackupReport:
    return BackupReport(False, None, reason, ())


def _entries(manifest: dict) -> list[tuple[str, str]]:
    return [
        (item["path"], item["sha256"])
        for item in [*manifest["icons"], manifest["wallpaper"]]
    ]


def _scan(root: Path) -> set[str]:
    """List relative entries without following links or allowing a large tree."""
    found = set()
    count = 0
    for current, directories, files in os.walk(root, followlinks=False):
        for name in [*directories, *files]:
            path = Path(current) / name
            if path.is_symlink():
                raise ValueError("backup contains a symlink")
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError("backup exceeds the safe entry count")
            found.add(path.relative_to(root).as_posix())
    return found


def _verify_tree(root: Path, manifest: dict) -> tuple[str, ...]:
    expected_files = {MANIFEST_NAME, *(rel for rel, _ in _entries(manifest))}
    expected_dirs = set()
    for name in expected_files:
        parts = Path(name).parts[:-1]
        for depth in range(1, len(parts) + 1):
            expected_dirs.add("/".join(parts[:depth]))

    found = _scan(root)
    for name in sorted(found):
        if any(marker in name for marker in INTERRUPTED_MARKERS):
            raise ValueError("interrupted write artifact in backup: " + name)
    unexpected = sorted(found - expected_files - expected_dirs)
    if unexpected:
        raise ValueError("unexpected backup entry: " + unexpected[0])
    missing = sorted(expected_files - found)
    if missing:
        raise ValueError("missing backup file: " + missing[0])
    for rel, digest in _entries(manifest):
        check_exact(root / rel, digest)
    return tuple(sorted(expected_files))


def validate_backup(
    backup_dir: Path, reference_manifest: Path | str = MANIFEST
) -> BackupReport:
    """Check version, trusted-lock match, layout and exact bytes. Never writes."""
    try:
        if not backup_dir.is_dir() or backup_dir.is_symlink():
            return _invalid("backup path is not a safe directory")
        version = json.loads(
            (backup_dir / MANIFEST_NAME).read_text(encoding="utf-8")
        ).get("schema_version")
        if version != MANIFEST_VERSION:
            return _invalid(f"unsupported config version: {version!r}")
        manifest = read_manifest(backup_dir / MANIFEST_NAME)
        reference = json.loads(
            Path(reference_manifest).read_text(encoding="utf-8")
        )
        if manifest != reference:
            return _invalid("backup manifest differs from trusted config lock")
        files = _verify_tree(backup_dir, manifest)
    except json.JSONDecodeError as exc:
        return _invalid("corrupt config JSON: " + str(exc))
    except (ArtworkError, OSError, KeyError, TypeError, ValueError) as exc:
        return _invalid(f"{type(exc).__name__}: {exc}")
    return BackupReport(True, version, "", files)


def recover(
    backup_dir: Path,
    destination: Path,
    reference_manifest: Path | str = MANIFEST,
) -> RecoveryOutcome:
    """Restore a verified backup atomically; quarantine a corrupt destination."""
    report = validate_backup(backup_dir, reference_manifest)
    if not report.ok:
        raise RecoveryError("refusing recovery: " + report.reason)

    parent = destination.parent
    if destination.is_symlink() or parent.is_symlink() or not parent.is_dir():
        raise RecoveryError("unsafe recovery destination path")
    if destination.exists() and not destination.is_dir():
        raise RecoveryError("recovery destination is not a directory")
    if destination.exists() and validate_backup(
        destination, reference_manifest
    ).ok:
        return RecoveryOutcome("unchanged", report.version, None)

    quarantine = None
    if destination.exists():
        quarantine = destination.with_name(
            destination.name + ".corrupt-" + uuid.uuid4().hex[:8]
        )
        destination.rename(quarantine)

    try:
        # Stage beside the destination so the final rename stays atomic.
        with tempfile.TemporaryDirectory(prefix=STAGING_PREFIX, dir=parent) as tmp:
            stage = Path(tmp) / "config"
            stage.mkdir()
            source_manifest = backup_dir / MANIFEST_NAME
            staged_manifest = stage / MANIFEST_NAME
            shutil.copyfile(source_manifest, staged_manifest)
            if staged_manifest.read_bytes() != source_manifest.read_bytes():
                raise OSError("interrupted manifest copy")
            manifest = read_manifest(source_manifest)
            for rel, digest in _entries(manifest):
                target = stage / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(backup_dir / rel, target)
                check_exact(target, digest)
            stage.rename(destination)
    except (ArtworkError, OSError, ValueError) as exc:
        if (quarantine is not None and quarantine.exists()
                and not destination.exists()):
            quarantine.rename(destination)
            quarantine = None
        raise RecoveryError("recovery failed: " + str(exc)) from exc
    return RecoveryOutcome("restored", report.version, quarantine)
