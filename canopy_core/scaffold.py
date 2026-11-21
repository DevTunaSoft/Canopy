"""Create an original Canopy Shell Pack directory from the checked-in starter.

This local developer tool only writes metadata + a QML stub. It never installs,
imports, runs, trusts, registers with a desktop session or executes pack code.
"""

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Iterable

from .registry import MAX_PACK_DIRECTORIES, scan_shell_packs
from tools.check_shell_pack import (
    CAPABILITIES, NAME_CONTROL, PACK_ID, PackValidationError, validate_pack,
)


STARTER = Path(__file__).resolve().parents[1] / "examples" / "shell-pack-starter"


def create_pack(
    catalog: Path,
    pack_id: str,
    name: str,
    description: str,
    capabilities: Iterable[str] = ("app-launcher",),
) -> Path:
    """Create a new local starter, refusing duplicates or invalid metadata."""
    root = Path(catalog)
    if root.is_symlink() or not root.is_dir():
        raise PackValidationError("catalog must be an existing real directory")
    if not isinstance(pack_id, str) or len(pack_id) > 128 or \
            not PACK_ID.fullmatch(pack_id) or pack_id.startswith("org.canopy."):
        raise PackValidationError("invalid or reserved reverse-DNS pack ID")
    for value, label, maximum in (
        (name, "name", 80), (description, "description", 240)
    ):
        if (not isinstance(value, str) or not value or len(value) > maximum
                or value != value.strip() or NAME_CONTROL.search(value)):
            raise PackValidationError(f"invalid {label}")
    capabilities = tuple(capabilities)
    if (not capabilities or
            any(not isinstance(cap, str) or cap not in CAPABILITIES
                for cap in capabilities) or
            len(set(capabilities)) != len(capabilities)):
        raise PackValidationError("unsupported or duplicate capabilities")

    # Never create a pack in an unsafe or ambiguous existing catalog.
    snapshot = scan_shell_packs(root)
    if snapshot.problems:
        raise PackValidationError("fix invalid or duplicate existing packs first")
    if snapshot.checked_directories >= MAX_PACK_DIRECTORIES:
        raise PackValidationError("shell pack catalog is full")
    if snapshot.get(pack_id) is not None:
        raise PackValidationError("pack ID already exists in catalog")

    target = root / pack_id
    if target.exists() or target.is_symlink():
        raise PackValidationError("target directory already exists")
    source_info = validate_pack(STARTER)
    if source_info["ui_engine"] != "qt-qml":
        raise PackValidationError("checked-in starter is not Qt/QML")
    source_qml = STARTER / source_info["entrypoint"]

    # mkdir(exist_ok=False) prevents accidental overwrite of any directory.
    # The partial directory is never executed or auto-discovered.
    target.mkdir(mode=0o700, exist_ok=False)
    try:
        (target / "ui").mkdir()
        shutil.copyfile(source_qml, target / "ui" / "Main.qml")
        manifest = dict(source_info)
        manifest.update(
            id=pack_id, name=name, description=description,
            capabilities=list(capabilities),
        )
        (target / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        (target / "README.md").write_text(
            f"# {name}\n\n"
            "Local Canopy Shell Pack starter only. This is NOT an installed, "
            "trusted or running desktop.\n\n"
            "Edit ui/Main.qml, verify visual/accessibility quality and "
            "run the offline manifest checker from the Canopy checkout. "
            "No runtime loader exists yet.\n",
            encoding="utf-8",
        )
        validated = validate_pack(target)
        if validated["id"] != pack_id:
            raise PackValidationError("generated pack identity mismatch")
    except Exception:
        # The whole target was created exclusively by this invocation.
        shutil.rmtree(target)
        raise
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="existing local pack catalog")
    parser.add_argument("--id", required=True, dest="pack_id")
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", default="Original Canopy desktop presentation")
    parser.add_argument(
        "--capability", action="append", dest="capabilities",
        choices=sorted(CAPABILITIES),
        help="repeat for each needed host affordance (default: app-launcher)",
    )
    args = parser.parse_args(argv)
    try:
        new_path = create_pack(
            args.catalog, args.pack_id, args.name, args.description,
            args.capabilities if args.capabilities else ("app-launcher",),
        )
    except (PackValidationError, OSError, ValueError) as exc:
        print(f"CANOPY_SCAFFOLD_FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"CANOPY_SCAFFOLD_PASS: {new_path} (metadata + QML stub only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
