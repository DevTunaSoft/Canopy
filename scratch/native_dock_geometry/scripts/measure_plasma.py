"""Pixel measurement of the real Plasma screenshots (read-only on images).

Derives barHeight, dockSize, dockPadding and dockSpacing from captured pixels:
top bar from an exact-RGB run at a clean column; dock surface from row-mean
border peaks and column-mean edge jumps; artwork pitch from saturated runs.
The 58px tile width is the frozen contract constant, not a fitted parameter.
Writes dock crops and a JSON measurement report inside owned scratch paths.
"""
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path(os.environ.get("NDG_BASE", str(Path(__file__).resolve().parents[1])))
SHOTS = BASE / "screenshots"
PER_SIZE = BASE / "per_size"
MEAS = BASE / "measurements"
MEAS.mkdir(parents=True, exist_ok=True)
SIZES = ["1920x1080", "1200x750", "760x500"]
# Clean columns free of dock and menu text in these captures.
CLEAN_COL = {"1920x1080": 1160, "1200x750": 800, "760x500": 580}
TILE = 58
ART = 48
N_TILES = 8
APPROVED = {"bar": 32, "dock": 96, "padding": 14, "spacing": 7}


def load(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB")).astype(np.int16)


def runs(mask, minimum=1):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= minimum:
                out.append((start, i - 1))
            start = None
    if start is not None and len(mask) - start >= minimum:
        out.append((start, len(mask) - 1))
    return out


def rle(line):
    out, s = [], 0
    for i in range(1, len(line) + 1):
        if i == len(line) or not np.array_equal(line[i], line[s]):
            out.append((s, i - 1, tuple(int(v) for v in line[s])))
            s = i
    return out


report = {}
for name in SIZES:
    if not (SHOTS / ("screen_%s.png" % name)).exists():
        print("SKIP missing " + name, flush=True)
        continue
    screen = load(SHOTS / ("screen_%s.png" % name))
    geo = {}
    for line in (PER_SIZE / name / "window_geometry.txt").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            geo[k] = int(v)
    # Crop 560x126 centred on the window, with the dock's bottom margin (22)
    # and the expected top border at crop row 15. Crop geometry is computed
    # from the observed window, never from a guessed screen offset.
    cw, ch = 560, 126
    cx = geo["X"] + geo["WIDTH"] // 2 - cw // 2
    cy = geo["Y"] + geo["HEIGHT"] - 22 - 96 - 15
    crop = screen[cy:cy + ch, cx:cx + cw]
    Image.fromarray(crop.astype(np.uint8)).save(SHOTS / ("dock_crop_%s.png" % name))

    rowmean = crop.mean(axis=(1, 2))
    top = int(np.argmax(rowmean[:40]))
    lo = top + 80
    hi = min(ch, top + 120)
    bottom = lo + int(np.argmax(rowmean[lo:hi]))
    cm = crop[top + 1:bottom].mean(axis=(0, 2))
    jump = np.diff(cm)
    left = int(np.argmax(jump[:150])) + 1
    right = 350 + int(np.argmin(jump[350:]))
    surf_w, surf_h = right - left + 1, bottom - top + 1

    # Artwork band: saturated icon pixels only, searched around the dock centre.
    satrows = (crop[:, 100:150].max(axis=2) - crop[:, 100:150].min(axis=2)).max(axis=1)
    hi_rows = 25 + np.flatnonzero(satrows[25:105] > 100)
    band = (int(hi_rows[0]), int(hi_rows[-1]))
    inner = slice(band[0] + 5, band[1] - 4)
    satcols = (crop[inner].max(axis=2) - crop[inner].min(axis=2)).max(axis=0)
    art = runs(satcols > 100, 45)
    pitch_values = sorted(set(np.diff([a for a, _ in art]).tolist()))
    spacing_values = [p - TILE for p in pitch_values]
    spacing = spacing_values[0]

    # Padding from the measured left inset of the first 58px tile slot.
    inset_left = art[0][0] - (TILE - ART) // 2 - left
    inset_right = right - (art[-1][1] + (TILE - ART) // 2)
    closure_width = N_TILES * TILE + (N_TILES - 1) * spacing + 2 * inset_left

    # Top bar: exact-RGB run-length at a clean column, ending at the border.
    col = CLEAN_COL[name]
    segs = [s for s in rle(screen[:, col, :]) if s[0] < 260]
    titles = [s for s in segs if s[2] == (222, 224, 226) and s[1] - s[0] >= 20]
    t_end = titles[0][1]
    bars = [s for s in segs if t_end < s[0] <= t_end + 50
            and abs(s[2][0] - 173) <= 3 and abs(s[2][1] - 189) <= 3
            and 200 <= s[2][2] <= 210 and s[1] - s[0] <= 2]
    bar_border = bars[0][0]
    bar_height = bar_border - t_end

    m = {
        "window": {k: geo[k] for k in ("X", "Y", "WIDTH", "HEIGHT")},
        "crop": {"x": cx, "y": cy, "width": cw, "height": ch},
        "dock_surface": {"crop_x": [left, right], "crop_y": [top, bottom],
                         "absolute_x": [cx + left, cx + right],
                         "absolute_y": [cy + top, cy + bottom],
                         "width": surf_w, "height": surf_h},
        "art_runs": [[a, b, b - a + 1] for a, b in art],
        "art_pitch": pitch_values,
        "tile_spacing": spacing_values,
        "padding_left": inset_left,
        "padding_right": inset_right,
        "closure_width": closure_width,
        "top_bar": {"title_strip_end": t_end, "border_row": bar_border,
                    "border_rgb": bars[0][2], "height": bar_height},
        "measured": {"bar": bar_height, "dock": surf_h,
                     "padding": inset_left, "spacing": spacing},
    }
    m["approved"] = APPROVED
    m["match"] = {k: m["measured"][k] == APPROVED[k]
                  for k in ("bar", "dock", "padding", "spacing")}
    m["tuple"] = "%d/%d/%d/%d" % (bar_height, surf_h, inset_left, spacing)
    report[name] = m
    print("%s %s bar=%d dock=%d padding=%d spacing=%d closure=%d/%d match=%s"
          % (name, m["tuple"], bar_height, surf_h, inset_left, spacing,
             closure_width, surf_w, all(m["match"].values())))

report["approved_tuple"] = "32/96/14/7"
report["all_match"] = all(all(v["match"].values())
                          for v in report.values() if isinstance(v, dict) and "match" in v)
out = MEAS / "geometry.json"
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("REPORT " + str(out))
