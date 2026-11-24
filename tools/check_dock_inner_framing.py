#!/usr/bin/env python3
"""Verify an opt-in dock-content experiment changes only actual icon pixels.

Use screenshot pairs from the SAME compiled Qt executable, unchanged source
art, renderer and screen geometry. This is a pixel isolation gate, not visual
approval or a claim of improved appearance.
"""
import argparse
import json
from pathlib import Path
import sys

if __package__:
    from .check_classic_icon_frame_diff import (
        APPS, CENTERS, HALF_SLOT, ComparisonError, _read_png
    )
else:
    from check_classic_icon_frame_diff import (
        APPS, CENTERS, HALF_SLOT, ComparisonError, _read_png
    )


def compare_dock_pair(before: Path, after: Path, size: str) -> dict:
    if size not in CENTERS:
        raise ComparisonError("unsupported real Qt capture size")
    width, height, first, first_hash = _read_png(before, size)
    _, _, second, second_hash = _read_png(after, size)
    counts = [0] * len(APPS)
    clock_changes = 0
    for offset in range(0, len(first), 4):
        if first[offset:offset + 4] == second[offset:offset + 4]:
            continue
        n = offset // 4
        x, y = n % width, n // width
        matches = [
            i for i, (cx, cy) in enumerate(CENTERS[size]["desktop"])
            if abs(x - cx) < HALF_SLOT and abs(y - cy) < HALF_SLOT
        ]
        if len(matches) == 1:
            counts[matches[0]] += 1
        elif y < 32 and x >= width - 220:
            # Qt clock can roll over at the minute between two executions.
            # The tight right-hand clock area is the only dynamic exception.
            clock_changes += 1
        else:
            raise ComparisonError(
                f"unexpected non-icon change at ({x}, {y}) in {size}"
            )
    if any(count == 0 for count in counts):
        raise ComparisonError("inner framing did not affect every dock icon")
    for (cx, cy) in CENTERS[size]["desktop"]:
        # Corner outside the cached rounded-face mask must remain unchanged.
        for dx in (-32, 32):
            for dy in (-32, 32):
                i = 4 * ((cy + dy) * width + cx + dx)
                if first[i:i + 4] != second[i:i + 4]:
                    raise ComparisonError("rounded card silhouette corner moved")
    return {
        "resolution": size,
        "baseline_sha256": first_hash,
        "candidate_sha256": second_hash,
        "changed_icon_pixels": sum(counts),
        "per_icon_changed_pixels": dict(zip(APPS, counts)),
        "clock_delta_pixels": clock_changes,
        "unexpected_changed_pixels": 0,
        "source_approval_inferred": False,
        "owner_visual_approval": False,
        "compared_real_compiled_qt_images": True,
        "same_binary_proven_by_png_alone": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--size", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare_dock_pair(args.before, args.after, args.size)
        result = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.write_text(result, encoding="utf-8")
        else:
            print(result, end="")
        print("CANOPY_DOCK_INNER_FRAME_DIFF_PASS: all eight content areas changed, "
              "no wallpaper or dock geometry changes", file=sys.stderr)
        return 0
    except (OSError, ComparisonError) as exc:
        print("CANOPY_DOCK_INNER_FRAME_DIFF_FAIL:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
