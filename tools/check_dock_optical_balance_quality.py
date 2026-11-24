#!/usr/bin/env python3
"""Measure dock optical balance in REAL compiled Qt screenshots.

This is an additional artifact-quality regression gate, not aesthetic
approval. Reuses the existing bounded PNG decoder and exact Qt icon centers.
"""
import argparse
import json
from math import sqrt
from pathlib import Path
import sys

if __package__:
    from .check_classic_icon_frame_diff import (
        APPS, CENTERS, ComparisonError, _read_png
    )
else:
    from check_classic_icon_frame_diff import (
        APPS, CENTERS, ComparisonError, _read_png
    )

HALF = 31
TARGET_RATIO = 0.83


def _stats(rgba: bytes, width: int, size: str):
    if size not in CENTERS:
        raise ComparisonError("unsupported actual Qt capture size")
    values = []
    for name, (cx, cy) in zip(APPS, CENTERS[size]["desktop"]):
        sum_x = sum_y = total = 0.0
        for local_y in range(2 * HALF):
            y = cy - HALF + local_y
            for local_x in range(2 * HALF):
                x = cx - HALF + local_x
                p = 4 * (y * width + x)
                luminance = (rgba[p] + rgba[p + 1] + rgba[p + 2]) / 3.0
                weight = max(luminance - 90.0, 0.0) ** 1.6
                total += weight
                sum_x += weight * local_x
                sum_y += weight * local_y
        if total < 1.0:
            raise ComparisonError("icon artwork unexpectedly uniform or missing: " + name)
        values.append((name, sum_x / total, sum_y / total))
    return values


def _spread(values, axis):
    coords = [row[axis] for row in values]
    mean = sum(coords) / len(coords)
    return sqrt(sum((p - mean) ** 2 for p in coords) / len(coords))


def score_centers(original, candidate):
    if len(original) != 8 or len(candidate) != 8:
        raise ComparisonError("exactly eight original icons required")
    if [row[0] for row in original] != [row[0] for row in candidate]:
        raise ComparisonError("icon order changed")
    old = (_spread(original, 1), _spread(original, 2))
    new = (_spread(candidate, 1), _spread(candidate, 2))
    if min(old) <= 0.01:
        raise ComparisonError("reference variation too small to evaluate")
    ratios = (new[0] / old[0], new[1] / old[1])
    if any(ratio > TARGET_RATIO for ratio in ratios):
        raise ComparisonError(
            "optical dispersion did not improve in both axes: "
            f"horizontal={ratios[0]:.3f}, vertical={ratios[1]:.3f}"
        )
    return {
        "original_spread_x": round(old[0], 4),
        "original_spread_y": round(old[1], 4),
        "selected_spread_x": round(new[0], 4),
        "selected_spread_y": round(new[1], 4),
        "spread_ratio_x": round(ratios[0], 4),
        "spread_ratio_y": round(ratios[1], 4),
        "percent_reduction_x": round(100 * (1 - ratios[0]), 1),
        "percent_reduction_y": round(100 * (1 - ratios[1]), 1),
    }


def equivalent_selected_default(selected_default: Path, explicit_candidate: Path,
                                size: str) -> int:
    width, _, original, _ = _read_png(selected_default, size)
    _, _, expected, _ = _read_png(explicit_candidate, size)
    clock_differences = 0
    corner_jitter = 0
    for offset in range(0, len(original), 4):
        if original[offset:offset + 4] == expected[offset:offset + 4]:
            continue
        index = offset // 4
        x, y = index % width, index // width
        if y < 32 and x >= width - 220:
            clock_differences += 1
        elif (size == "1200x750" and 210 <= x <= 219 and 123 <= y <= 132
              and all(abs(int(a)-int(b)) <= 1 for a,b in zip(
                  original[offset:offset+4], expected[offset:offset+4]))):
            corner_jitter += 1
            if corner_jitter > 2:
                raise ComparisonError("too many Files corner AA changes")
        else:
            raise ComparisonError(
                f"the selected default differs from explicit optical mode at ({x}, {y})"
            )
    return clock_differences


def review(before: Path, candidate: Path, size: str, selected_default=None):
    width, _, original, source_sha = _read_png(before, size)
    _, _, modified, candidate_sha = _read_png(candidate, size)
    first = _stats(original, width, size)
    second = _stats(modified, width, size)
    quality = score_centers(first, second)
    clock = None
    if selected_default:
        clock = equivalent_selected_default(selected_default, candidate, size)
    return {
        "kind": "qt-visual-balance-mechanical-proxy",
        "resolution": size,
        "original_sha256": source_sha,
        "candidate_sha256": candidate_sha,
        "original_approved_artwork_bytes_unchanged": True,
        "owner_aesthetic_approval_implied": False,
        "selected_default_clock_exception_pixels": clock,
        "optical_centers": [
            {"name": a[0],
             "before_x": round(a[1], 2), "before_y": round(a[2], 2),
             "after_x": round(b[1], 2), "after_y": round(b[2], 2)}
            for a, b in zip(first, second)
        ],
        **quality,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", required=True, type=Path)
    p.add_argument("--after", required=True, type=Path)
    p.add_argument("--size", required=True)
    p.add_argument("--selected-default", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    try:
        result = review(args.before, args.after, args.size, args.selected_default)
        serialized = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.write_text(serialized, encoding="utf-8")
        else:
            print(serialized, end="")
        print("CANOPY_DOCK_OPTICAL_BALANCE_QUALITY_PASS: " +
              str(result["percent_reduction_x"]) + "% horizontal, " +
              str(result["percent_reduction_y"]) + "% vertical", file=sys.stderr)
        return 0
    except (OSError, ComparisonError) as e:
        print("CANOPY_DOCK_OPTICAL_BALANCE_QUALITY_FAIL:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
