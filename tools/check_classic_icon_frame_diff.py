#!/usr/bin/env python3
"""Verify frozen dock is pixel-identical, launcher changes only its icons.

This is reproducible image evidence, not visual approval or automatic
optical correction. Images must come from separately verified same-binary
Qt runs with the owner's exact original icons. Stdlib only; PNG decoder
reused from the existing bounded source-art audit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__:
    from .audit_approved_icon_optics import AuditError, decode_rgba_png
else:
    from audit_approved_icon_optics import AuditError, decode_rgba_png

APPS = ("Browser", "Mail", "Files", "Calendar", "Photos",
        "Music", "Terminal", "Settings")
SIZES = ("760x500", "1200x750", "1920x1080")
# User-approved enlargement: 66x66 dock QML image centers. This audit is intentionally
# strict: a future layout change requires a reviewed geometry update, not a
# silent tolerance expansion or arbitrary ignored screenshot rectangle.
CENTERS = {
    "760x500": {
        "desktop": [(112 + 77 * i, 427) for i in range(8)],
        "launcher": [(127 + 169 * i, 196) for i in range(4)] +
                    [(127 + 169 * i, 293) for i in range(4)],
    },
    "1200x750": {
        "desktop": [(332 + 77 * i, 677) for i in range(8)],
        "launcher": [(310 + 193 * i, 284) for i in range(4)] +
                    [(310 + 193 * i, 401) for i in range(4)],
    },
    "1920x1080": {
        "desktop": [(692 + 77 * i, 1007) for i in range(8)],
        "launcher": [(670 + 193 * i, 449) for i in range(4)] +
                    [(670 + 193 * i, 566) for i in range(4)],
    },
}
HALF_SLOT = 33
LAUNCHER_HALF_SLOT = 27
MAX_FILE = 12_000_000


class ComparisonError(ValueError):
    pass


def _read_png(path, size):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_FILE:
        raise ComparisonError("unsafe, missing or oversized screenshot: " + p.name)
    data = p.read_bytes()
    try:
        width, height, rgba = decode_rgba_png(data)
    except AuditError as exc:
        raise ComparisonError("invalid RGBA screenshot: " + p.name) from exc
    if f"{width}x{height}" != size:
        raise ComparisonError("wrong screenshot dimensions: " + p.name)
    return width, height, rgba, hashlib.sha256(data).hexdigest()


def compare_pair(before, after, size, scene):
    if size not in CENTERS or scene not in ("desktop", "launcher"):
        raise ComparisonError("unsupported Qt screenshot geometry")
    width, height, orig, before_hash = _read_png(before, size)
    _, _, modified, after_hash = _read_png(after, size)
    # The dock and every other desktop pixel are frozen. A launcher-only
    # experiment is invalid if even one closed-desktop pixel differs.
    if scene == "desktop":
        if orig != modified:
            for offset in range(0, len(orig), 4):
                if orig[offset:offset + 4] != modified[offset:offset + 4]:
                    pixel = offset // 4
                    raise ComparisonError(
                        f"frozen dock/desktop pixel changed at "
                        f"({pixel % width}, {pixel // width}) in {size}"
                    )
        return {
            "resolution": size, "scene": scene,
            "changed_pixels": 0, "outside_icon_pixels": 0,
            "per_icon_changed_pixels": dict.fromkeys(APPS, 0),
            "before_sha256": before_hash, "after_sha256": after_hash,
        }
    counts = [0] * len(APPS)
    for i in range(0, len(orig), 4):
        if (orig[i] == modified[i] and orig[i + 1] == modified[i + 1]
                and orig[i + 2] == modified[i + 2]
                and orig[i + 3] == modified[i + 3]):
            continue
        pixel = i // 4
        x, y = pixel % width, pixel // width
        slot_half = HALF_SLOT if scene == "desktop" else LAUNCHER_HALF_SLOT
        matches = [n for n, (cx, cy) in enumerate(CENTERS[size][scene])
                   if abs(x - cx) < slot_half and abs(y - cy) < slot_half]
        if len(matches) != 1:
            raise ComparisonError(
                f"unexpected change outside exactly one {scene} icon slot "
                f"at ({x}, {y}) in {size}"
            )
        counts[matches[0]] += 1
    if min(counts) == 0:
        raise ComparisonError("framing mode failed to visibly affect every icon")
    return {
        "resolution": size,
        "scene": scene,
        "changed_pixels": sum(counts),
        "outside_icon_pixels": 0,
        "per_icon_changed_pixels": dict(zip(APPS, counts)),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
    }


def audit_directory(root):
    directory = Path(root)
    if directory.is_symlink() or not directory.is_dir():
        raise ComparisonError("evidence directory must be a regular local directory")
    rows = []
    for size in SIZES:
        for scene in ("desktop", "launcher"):
            rows.append(compare_pair(
                directory / f"baseline-{scene}-{size}.png",
                directory / f"framed-{scene}-{size}.png",
                size, scene))
    return {
        "kind": "qt-classic-optical-review-only",
        "same_binary_required_but_not_inferred_from_screenshots": True,
        "approved_original_sha_evidence_required_separately": True,
        "owner_visual_approval": False,
        "pair_count": len(rows),
        "scenes": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_directory(args.evidence_dir)
        payload = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        print("CANOPY_ICON_FRAME_DIFF_PASS: six Qt screenshot comparisons, "
              "frozen dock byte-identical; launcher edits inside 54px icon slots", file=sys.stderr)
        return 0
    except (AuditError, ComparisonError, OSError) as exc:
        print("CANOPY_ICON_FRAME_DIFF_FAIL:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
