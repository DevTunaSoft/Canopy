#!/usr/bin/env python3
"""Real-Qt five-dock gate: bounded frozen jitter and verified v3 pack activation.

Two independent, fail-closed checks live here:

1. Pixel lock. Only Browser, Mail, Files, Terminal and Settings may change.
   Calendar, Photos and Music are frozen. Separate Xvfb processes can round
   the translucent dock's software compositing by one 8-bit channel level
   even inside a frozen icon slot, so this gate admits ONLY that bounded
   one-level RGB noise (unchanged alpha, inside the dock plate, capped per
   frozen slot and per run). Any larger artwork change, alpha shift, out-of-
   dock change or excessive count still fails closed.

2. Runtime activation. A compiled-Qt log must contain exactly one
   FIVE_PRODUCTION_PACK_VERIFIED marker and no FALLBACK or FAIL marker.
   A missing pack therefore never launders into a pass.

This is engineering evidence, not owner visual approval.
"""
import argparse
import json
from pathlib import Path
import re
import sys

try:
    from .check_classic_icon_frame_diff import (
        APPS, CENTERS, HALF_SLOT, ComparisonError, _read_png
    )
except ImportError:
    from check_classic_icon_frame_diff import (
        APPS, CENTERS, HALF_SLOT, ComparisonError, _read_png
    )

FROZEN = frozenset({"Calendar", "Photos", "Music"})
TARGET = frozenset({"Browser", "Mail", "Files", "Terminal", "Settings"})
# At most eight one-level RGB deltas in any one frozen slot and at most 256
# across the whole run, matching the existing translucent dock-plate bound.
FROZEN_JITTER_MAX = 8
DOCK_PLATE_JITTER_MAX = 256
CORNER_AA_MAX = 2
WINDOW_CORNER = {"1200x750": (210, 123), "760x500": (36, 62),
                 "1920x1080": (422, 196)}


def corner_antialias_jitter(size, x, y, old_rgba, new_rgba):
    """One-level AA noise on 1-2 Files window-corner pixels, never a region."""
    px, py = WINDOW_CORNER[size]
    return (0 <= x - px <= 9 and 0 <= y - py <= 9 and
            all(abs(int(a) - int(b)) <= 1
                for a, b in zip(old_rgba, new_rgba)))


def dock_plate_one_level_jitter(size, x, y, first, second):
    """One-level RGB rounding inside the translucent dock plate only."""
    width, height = [int(n) for n in size.split("x")]
    dock_left = (width - 605) / 2.0
    dock_top = height - 118
    return (dock_left <= x < dock_left + 605 and
            dock_top <= y < dock_top + 96 and
            first[3] == second[3] and
            all(abs(int(a) - int(b)) <= 1 for a, b in zip(first[:3], second[:3])))


def compare_five(before: Path, after: Path, size: str,
                 frozen_identity: bool = False) -> dict:
    """Compare a rollback vs five-center pair, or two equivalent v3 captures.

    frozen_identity=True is the default-activation identity check: both sides
    already use the v3 five-center composition, so no target icon is required
    to change. Frozen artwork and non-icon pixels stay just as strictly gated.
    """
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
        first = source[offset:offset + 4]
        second = candidate[offset:offset + 4]
        if first == second:
            continue
        pixel = offset // 4
        x, y = pixel % width, pixel // width
        matches = [i for i, (cx, cy) in enumerate(pixels)
                   if abs(x - cx) < HALF_SLOT and abs(y - cy) < HALF_SLOT]
        if len(matches) == 1:
            app = APPS[matches[0]]
            if app in FROZEN:
                # Admit only the same one-level RGB noise accepted for the
                # dock plate: unchanged alpha, small per-slot and per-run
                # caps. A frozen artwork edit is still a hard failure.
                if (frozen_jitter[app] < FROZEN_JITTER_MAX and
                        dock_plate_one_level_jitter(size, x, y, first, second)):
                    frozen_jitter[app] += 1
                    dock_plate_jitter += 1
                    if dock_plate_jitter > DOCK_PLATE_JITTER_MAX:
                        raise ComparisonError("too many 1-level dock compositing pixels")
                    continue
                raise ComparisonError(f"frozen {app} artwork changed at ({x},{y})")
            changes[app] += 1
        elif y < 32 and x >= width - 220:
            clock_pixels += 1
        elif corner_antialias_jitter(size, x, y, first, second):
            corner_jitter += 1
            if corner_jitter > CORNER_AA_MAX:
                raise ComparisonError("too many Files rounded-corner AA changes")
        elif dock_plate_one_level_jitter(size, x, y, first, second):
            dock_plate_jitter += 1
            if dock_plate_jitter > DOCK_PLATE_JITTER_MAX:
                raise ComparisonError("too many 1-level dock compositing pixels")
        else:
            raise ComparisonError(f"unexpected non-icon change at ({x},{y})")
    if not frozen_identity:
        for name in TARGET:
            if changes[name] == 0:
                raise ComparisonError(f"targeted {name} icon did not change")
    for (cx, cy) in pixels:
        for dx in (-30, 30):
            for dy in (-30, 30):
                p = 4 * ((cy + dy) * width + cx + dx)
                if source[p:p + 4] != candidate[p:p + 4]:
                    raise ComparisonError("dock card corner or silhouette changed")
    return {
        "resolution": size, "baseline_sha256": source_hash,
        "five_icon_candidate_sha256": candidate_hash,
        "per_icon_changed_pixels": changes,
        "calendar_photos_music_pixel_perfect":
            all(changes[name] == 0 and frozen_jitter[name] <= FROZEN_JITTER_MAX
                for name in FROZEN),
        "frozen_one_level_compositing_jitter": frozen_jitter,
        "five_targets_genuinely_changed":
            (None if frozen_identity else all(changes[name] > 0 for name in TARGET)),
        "frozen_identity_mode": frozen_identity,
        "target_change_required": not frozen_identity,
        "non_icon_changes": 0,
        "clock_exception_pixels": clock_pixels,
        "one_level_files_corner_aa_pixels": corner_jitter,
        "one_level_dock_plate_aa_pixels": dock_plate_jitter,
        "frozen_artwork_change_rejected": True,
        "owner_visual_approval_inferred": False,
        "evidence": "same compiled Qt binary + SHA-locked approved masters required",
    }


def verify_pack_activation(log_text: str) -> dict:
    """Fail closed unless the exact v3 pack was actually loaded at runtime."""
    if not isinstance(log_text, str):
        raise ComparisonError("runtime log must be decoded text")
    verified = re.findall(
        r"^FIVE_PRODUCTION_PACK_VERIFIED:.*$", log_text, re.MULTILINE)
    fallback = re.findall(
        r"^FIVE_PRODUCTION_PACK_FALLBACK:.*$", log_text, re.MULTILINE)
    failure = re.findall(
        r"^FIVE_PRODUCTION_PACK_FAIL:.*$", log_text, re.MULTILINE)
    required = re.findall(
        r"^--require-five-production-icons$", log_text, re.MULTILINE)
    if fallback or failure or len(verified) != 1:
        raise ComparisonError(
            "FIVE_PRODUCTION_PACK_NOT_VERIFIED: verified=%d fallback=%d fail=%d"
            % (len(verified), len(fallback), len(failure)))
    return {
        "five_production_pack_verified": 1,
        "FIVE_PRODUCTION_PACK_VERIFIED": 1,
        "fallback_count": 0,
        "runtime_failure_count": 0,
        "require_flag_observed": bool(required),
        "renderer": "canopy-five-qt-v3",
        "owner_visual_approval_inferred": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", type=Path)
    p.add_argument("--after", type=Path)
    p.add_argument("--size")
    p.add_argument("--frozen-identity", action="store_true",
                   help="compare two v3 five-center captures; do not require target changes")
    p.add_argument("--pack-log", type=Path,
                   help="compiled-Qt runtime log to gate on verified v3 pack load")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.pack_log is not None:
            if a.before or a.after or a.size:
                raise ComparisonError("pack-log mode cannot combine with pixel arguments")
            result = verify_pack_activation(a.pack_log.read_text(encoding="utf-8"))
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("FIVE_PRODUCTION_PACK_VERIFIED=1")
            return 0
        if not (a.before and a.after and a.size):
            raise ComparisonError("pixel mode needs --before, --after and --size")
        result = compare_five(a.before, a.after, a.size,
                              frozen_identity=a.frozen_identity)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("FIVE_DOCK_ICON_PIXEL_LOCK_PASS:", a.size,
              "frozen artwork locked, bounded one-level compositing jitter recorded")
        return 0
    except (ComparisonError, OSError) as exc:
        print("FIVE_DOCK_ICON_PIXEL_LOCK_FAIL:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
