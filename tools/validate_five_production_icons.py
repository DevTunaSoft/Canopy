#!/usr/bin/env python3
"""Verify immutable user-approved sources and Qt-generated five-icon PNG pack.

No image editing, aesthetic inference, network, Pillow, or external resources.
Accept EXACTLY five names x three densities, all SHA-256-verified. The other
three icons must not be present in the production derivative directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

try:
    from .audit_approved_icon_optics import decode_rgba_png, AuditError
except ImportError:
    from audit_approved_icon_optics import decode_rgba_png, AuditError

TARGET = ("browser", "mail", "files", "terminal", "settings")
FROZEN = ("calendar", "photos", "music")
DENSITIES = (1, 2, 3)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXPECTED_RENDERER = "canopy-five-qt-v3-alpha"


class ProductionIconError(ValueError):
    pass


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read_secure(path, limit=3_000_000):
    if path.is_symlink() or not path.is_file() or not (1 <= path.stat().st_size <= limit):
        raise ProductionIconError("unsafe, absent, or oversized asset: " + str(path))
    return path.read_bytes()


def verify_pack(master_dir: Path, output_dir: Path):
    mpath = master_dir / "manifest.json"
    mbytes = read_secure(mpath, 128_000)
    master = json.loads(mbytes)
    icons = master["icons"]
    if len(icons) != 8:
        raise ProductionIconError("expected 8 immutable approved originals")
    by_name = {row["name"].lower(): row for row in icons}
    if set(by_name) != set(TARGET) | set(FROZEN):
        raise ProductionIconError("approved source inventory changed")
    for name, row in by_name.items():
        path = master_dir / row["path"]
        if not row["path"].startswith("icons/") or "../" in row["path"]:
            raise ProductionIconError("untrusted approved source path")
        if digest(read_secure(path)) != row["sha256"]:
            raise ProductionIconError("original master SHA mismatch: " + name)

    pack_path = output_dir / "manifest.json"
    pack = json.loads(read_secure(pack_path, 128_000))
    if pack.get("schema_version") != 1 or pack.get("renderer") != EXPECTED_RENDERER:
        raise ProductionIconError("production pack provenance or version mismatch")
    if pack.get("source_manifest_sha256") != digest(mbytes):
        raise ProductionIconError("production pack points to wrong original source manifest")
    files = pack.get("files")
    if not isinstance(files, list) or len(files) != 15:
        raise ProductionIconError("expected exactly five x three production PNGs")
    by_path = {row["path"]: row for row in files}
    required = {f"{density}x/{id}.png" for id in TARGET for density in DENSITIES}
    if set(by_path) != required or len(by_path) != len(files):
        raise ProductionIconError("unexpected source, frozen icon, or missing derivative")
    actual_files = {str(p.relative_to(output_dir)).replace("\\", "/")
                    for p in output_dir.rglob("*") if p.is_file()}
    if actual_files != required | {"manifest.json"}:
        raise ProductionIconError("unexpected file in production icon folder")

    hashes = {}
    for density in DENSITIES:
        for name in TARGET:
            rel = f"{density}x/{name}.png"
            row = by_path[rel]
            blob = read_secure(output_dir / rel)
            if row.get("sha256") != digest(blob):
                raise ProductionIconError("production PNG SHA mismatch: " + rel)
            if not blob.startswith(PNG_SIGNATURE) or blob[12:16] != b"IHDR":
                raise ProductionIconError("invalid PNG header: " + rel)
            width, height, bitdepth, mode = struct.unpack(">IIBB", blob[16:26])
            if (width, height, bitdepth) != (192*density, 192*density, 8):
                raise ProductionIconError("wrong production dimensions: " + rel)
            if mode not in (4, 6):
                raise ProductionIconError("production icon lacks transparent corner capacity: " + rel)
            if row.get("pixels") != 192*density:
                raise ProductionIconError("production manifest dimensions mismatch: " + rel)
            try:
                decoded_width, decoded_height, rgba = decode_rgba_png(blob)
            except AuditError as exc:
                raise ProductionIconError("PNG pixel/CRC integrity failure: " + rel) from exc
            if (decoded_width, decoded_height) != (width, height):
                raise ProductionIconError("decoded dimensions mismatch: " + rel)
            for x, y in ((0, 0), (width-1, 0), (0, height-1), (width-1, height-1)):
                if rgba[4 * (y*width+x) + 3] != 0:
                    raise ProductionIconError("source-derived icon corner must be transparent: " + rel)
            if rgba[4*((height//2)*width+width//2)+3] < 250:
                raise ProductionIconError("source-derived icon center unexpectedly transparent: " + rel)
            hashes[rel] = row["sha256"]
    return {
        "verified_source_master_count": 8,
        "production_icon_names": list(TARGET),
        "frozen_icons_excluded": list(FROZEN),
        "variants": len(required),
        "density_pixels": [192, 384, 576],
        "source_manifest_sha256": digest(mbytes),
        "pack_file_sha256": hashes,
        "master_pngs_untouched": True,
        "scope": "source and image integrity; not owner aesthetic approval",
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--approved-art-dir",type=Path,required=True)
    p.add_argument("--production-dir",type=Path,required=True)
    p.add_argument("--report",type=Path)
    args=p.parse_args(argv)
    try:
        result=verify_pack(args.approved_art_dir,args.production_dir)
        payload=json.dumps(result,indent=2)+"\n"
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(payload,encoding="utf-8")
        else:
            print(payload,end="")
        print("CANOPY_FIVE_PRODUCTION_ASSET_PACK_PASS: 15 SHA-checked PNGs; 3 frozen excluded")
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError,AuditError) as exc:
        print("CANOPY_FIVE_PRODUCTION_ASSET_PACK_FAIL:",exc,file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
