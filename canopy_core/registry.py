"""Bounded metadata-only Canopy Shell Pack discovery.

This module never imports, executes, displays, installs, trusts, or grants
permissions to code in a Shell Pack. The future Qt host must enforce its own
signed-package review and sandbox/capability boundaries before loading QML.
"""

from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import FrozenSet, Mapping, Optional, Tuple

from tools.check_shell_pack import (
    PackValidationError,
    require_real_path_components,
    validate_pack,
)


MAX_PACK_DIRECTORIES = 64


@dataclass(frozen=True)
class ShellPackInfo:
    """Immutable metadata for a discovered pack; NOT an execution approval."""

    pack_id: str
    name: str
    description: str
    directory: Path
    entrypoint: str
    shell_api: int
    ui_engine: str
    capabilities: FrozenSet[str]


@dataclass(frozen=True)
class ScanProblem:
    location: str
    reason: str


@dataclass(frozen=True)
class PackScan:
    packs: Tuple[ShellPackInfo, ...]
    problems: Tuple[ScanProblem, ...]
    checked_directories: int

    def get(self, pack_id: str) -> Optional[ShellPackInfo]:
        """Exact-case lookup, not a filesystem path lookup or code load."""
        return next((pack for pack in self.packs if pack.pack_id == pack_id), None)

    def compatible(self, host_capabilities: FrozenSet[str]) -> Tuple[ShellPackInfo, ...]:
        """Capability declarations describe UI affordances, not privileges."""
        if not isinstance(host_capabilities, frozenset):
            raise TypeError("host_capabilities must be a frozenset")
        return tuple(pack for pack in self.packs
                     if pack.capabilities.issubset(host_capabilities))


def scan_shell_packs(directory: Path) -> PackScan:
    """Inspect at most 64 direct child pack folders; reject ambiguous IDs.

    Invalid packs are reported and excluded without interfering with healthy
    packs. Duplicate IDs are all excluded, rather than choosing a winner.
    Returns metadata only: QML entrypoints are never executed.
    """
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise PackValidationError("shell pack catalog root must be a real directory")
    require_real_path_components(
        root, "shell pack catalog root must be a real directory"
    )

    discovered = {}
    bad_ids = set()
    problems = []
    children = list(islice(root.iterdir(), MAX_PACK_DIRECTORIES + 1))
    if len(children) > MAX_PACK_DIRECTORIES:
        raise PackValidationError("shell pack catalog exceeds 64 entries")

    for candidate in sorted(children, key=lambda item: (item.name.casefold(), item.name)):
        if candidate.is_symlink():
            problems.append(ScanProblem(candidate.name, "symlink pack directory rejected"))
            continue
        if not candidate.is_dir():
            # A README or other ordinary catalog file is not a Shell Pack.
            continue
        try:
            manifest = validate_pack(candidate)
        except (PackValidationError, OSError) as exc:
            problems.append(ScanProblem(candidate.name, str(exc)))
            continue

        pack_id = manifest["id"]
        if pack_id in bad_ids:
            problems.append(ScanProblem(candidate.name, "duplicate pack ID rejected"))
            continue
        if pack_id in discovered:
            previous = discovered.pop(pack_id)
            bad_ids.add(pack_id)
            problems.append(ScanProblem(previous.directory.name,
                                        "duplicate pack ID rejected"))
            problems.append(ScanProblem(candidate.name, "duplicate pack ID rejected"))
            continue

        discovered[pack_id] = ShellPackInfo(
            pack_id=pack_id,
            name=manifest["name"],
            description=manifest["description"],
            directory=candidate.resolve(strict=True),
            entrypoint=manifest["entrypoint"],
            shell_api=manifest["shell_api"],
            ui_engine=manifest["ui_engine"],
            capabilities=frozenset(manifest["capabilities"]),
        )

    return PackScan(
        packs=tuple(sorted(discovered.values(), key=lambda pack: pack.pack_id)),
        problems=tuple(problems),
        checked_directories=sum(1 for child in children if child.is_dir()),
    )
