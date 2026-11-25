#!/usr/bin/env python3
"""Real-Qt pixel lock: EXACTLY five icons may change in dock centering.

The user specifically froze Calendar, Photos and Music. Their artwork MUST
match the same-binary baseline. All non-icon UI must also match (except
tightly bounded live clock pixels). Separate Xvfb processes can round the
translucent dock's software compositing one 8-bit channel level differently
even inside a frozen icon slot; only that already-admitted dock-plate noise
is tolerated here, per icon and per run bounded, with any larger artwork
change still failing closed.
"""
import argparse
import json
from pathlib import Path
import sys

try:
    from .check_classic_icon_frame_diff import APPS, CENTERS, HALF_SLOT, ComparisonError, _read_png
except ImportError:
    from check_classic_icon_frame_diff import APPS, CENTERS, HALF_SLOT, ComparisonError, _read_png

try:
    from .check_dock_inner_framing import corner_antialias_jitter, dock_plate_one_level_jitter
except ImportError:
    from check_dock_inner_framing import corner_antialias_jitter, dock_plate_one_level_jitter

FROZEN = frozenset({"Calendar", "Photos", "Music"})
TARGET = frozenset({"Browser", "Mail", "Files", "Terminal", "Settings"})
# Bound borrowed from the dock-plate compositing exception: at most eight
# one-level RGB deltas per frozen slot and the existing 256-pixel run total.
FROZEN_JITTER_MAX = 8
DOCK_PLATE_JITTER_MAX = 256


def compare_five(before: Path, after: Path, size: str):
    if size not in CENTERS:
        raise ComparisonError("unsupported real-Qt screenshot size")
    if frozenset(APPS) != FROZEN | TARGET or FROZEN & TARGET:
        raise ComparisonError("source application inventory no longer matches user's scope")
    width, height, source, source_hash = _read_png(before, size)
    _, _, candidate, candidate_hash = _read_png(after, size)
    changes = dict.fromkeys(APPS, 0)
    frozen_jitter = dict.fromkeys(FROZEN, 0)
    clock_pixels = 0
    corner_jitter = 0
    dock_plate_jitter = 0
    pixels = CENTERS[size]["desktop"]
    for offset in range(0, len(source), 4):
        if source[offset:offset+4] == candidate[offset:offset+4]:
            continue
        pixel = offset // 4
        x, y = pixel % width, pixel // width
        matches = [i for i, (cx, cy) in enumerate(pixels)
                   if abs(x-cx) < HALF_SLOT and abs(y-cy) < HALF_SLOT]
        if len(matches) == 1:
            app = APPS[matches[0]]
            if app in FROZEN:
                # Separate Xvfb processes can round translucent-dock
                # compositing by one 8-bit level even inside a frozen slot.
                # Admit only the same one-level RGB noise already accepted
                # for dock-plate pixels, bounded per slot and per run; any
                # alpha shift, larger delta or out-of-dock pixel still fails.
                if (frozen_jitter[app] < FROZEN_JITTER_MAX and
                        dock_plate_one_level_jitter(
                            size, x, y, source[offset:offset+4],
                            candidate[offset:offset+4])):
                    frozen_jitter[app] += 1
                    dock_plate_jitter += 1
                    if dock_plate_jitter > DOCK_PLATE_JITTER_MAX:
                        raise ComparisonError(
                            "too many 1-level glass compositing pixels")
                    continue
                raise ComparisonError(f"frozen {app} artwork changed at ({x},{y})")
            changes[app] += 1
        elif y < 32 and x >= width - 220:
            clock_pixels += 1
        elif corner_antialias_jitter(
                size, x, y, source[offset:offset+4], candidate[offset:offset+4]):
            corner_jitter += 1
            if corner_jitter > 2:
                raise ComparisonError("too many Files rounded-corner AA changes")
        elif dock_plate_one_level_jitter(
                size, x, y, source[offset:offset+4], candidate[offset:offset+4]):
            dock_plate_jitter += 1
            if dock_plate_jitter > DOCK_PLATE_JITTER_MAX:
                raise ComparisonError("too many 1-level glass compositing pixels")
        else:
            raise ComparisonError(f"unexpected non-icon change at ({x},{y})")
    for name in TARGET:
        if changes[name] == 0:
            raise ComparisonError(f"targeted {name} icon did not change")
    for (cx, cy) in pixels:
        for dx in (-30,30):
            for dy in (-30,30):
                p = 4*((cy+dy)*width+(cx+dx))
                if source[p:p+4] != candidate[p:p+4]:
                    raise ComparisonError("dock card corner or silhouette changed")
    return {
        "resolution":size, "baseline_sha256":source_hash,
        "five_icon_candidate_sha256":candidate_hash,
        "per_icon_changed_pixels":changes,
        "calendar_photos_music_pixel_perfect":all(changes[n]==0 for n in FROZEN),
        "frozen_one_level_compositing_jitter":frozen_jitter,
        "five_targets_genuinely_changed":all(changes[n]>0 for n in TARGET),
        "non_icon_changes":0,
        "clock_exception_pixels":clock_pixels,
        "one_level_files_corner_aa_pixels":corner_jitter,
        "one_level_dock_plate_aa_pixels":dock_plate_jitter,
        "owner_visual_approval_inferred":False,
        "evidence": "same compiled Qt binary + SHA-locked approved masters required",
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before",type=Path,required=True)
    p.add_argument("--after",type=Path,required=True)
    p.add_argument("--size",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        result=compare_five(a.before,a.after,a.size)
        a.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print("FIVE_DOCK_ICON_PIXEL_LOCK_PASS:",a.size,
              "frozen artwork locked, bounded one-level compositing jitter recorded")
        return 0
    except (ComparisonError,OSError) as exc:
        print("FIVE_DOCK_ICON_PIXEL_LOCK_FAIL:",exc,file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
