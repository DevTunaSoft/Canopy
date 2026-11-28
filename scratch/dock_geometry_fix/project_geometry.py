#!/usr/bin/env python3
"""Headless, byte-level dock-geometry projection evidence.

No Qt, no display, no screenshot, no pixel sampling and no native runtime is
used. All claims are STATIC SOURCE ONLY / SYNTHETIC projections of committed
bytes. Pixel/visual owner acceptance stays HOLD / NOT_RUN.
"""

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = "ec910d7a7275296ecbc8b5e5c459d356205165d1"
APPROVED = {"barHeight": 32, "dockSize": 96, "dockPadding": 14, "dockSpacing": 7}
BASE_TUPLE = {"barHeight": 32, "dockSize": 88, "dockPadding": 12, "dockSpacing": 7}
DIRECTIVE_SHA256 = (
    "1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a"
)
DIRECTIVE = Path("C:/Users/X1/Downloads/"
                 "Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md")
THEME = "prototype/classic/Theme.qml"
ASSETS_PREFIX = "prototype/classic/assets/"
TILE_WIDTH = 58  # committed prototype/classic/DockTile.qml `width: 58`
ICON_COUNT = 8   # approved eight-icon dock


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError("git %s failed rc=%d: %s" % (
            " ".join(args), proc.returncode,
            proc.stderr.decode("utf-8", "replace")[:400]))
    return proc.stdout


def norm(data):
    return data.replace(b"\r\n", b"\n")


def sha256(data):
    return hashlib.sha256(norm(data)).hexdigest()


def parse_constants(text):
    found = {}
    for key in APPROVED:
        match = re.search(r"readonly property int " + key + r":\s*(\d+)", text)
        if not match:
            raise AssertionError("missing constant " + key)
        found[key] = int(match.group(1))
    return found


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def projection(constants):
    surface = ICON_COUNT * TILE_WIDTH + (ICON_COUNT - 1) * constants[
        "dockSpacing"] + 2 * constants["dockPadding"]
    return {
        "bar_height_px": constants["barHeight"],
        "dock_height_px": constants["dockSize"],
        "dock_padding_px": constants["dockPadding"],
        "dock_spacing_px": constants["dockSpacing"],
        "icon_count": ICON_COUNT,
        "tile_width_px": TILE_WIDTH,
        "projected_dock_surface_width_px": surface,
        "formula": "%d*%d + %d*%d + 2*%d" % (
            ICON_COUNT, TILE_WIDTH, ICON_COUNT - 1,
            constants["dockSpacing"], constants["dockPadding"]),
    }


def nonvisual_projection(theme_bytes):
    """Freeze every Theme.qml byte except the four geometry constant lines.

    Replacing the four complete lines with a fixed placeholder proves whether
    all colors, identity tokens and other constants stayed byte-identical.
    """
    lines = norm(theme_bytes).decode("utf-8").split("\n")
    out = []
    for line in lines:
        if re.match(r"\s*readonly property int (barHeight|dockSize|"
                    r"dockPadding|dockSpacing):\s*\d+\s*$", line):
            out.append("<GEOMETRY-CONSTANT-PROJECTION>")
        else:
            out.append(line)
    return "\n".join(out)


def asset_tree(repo, rev):
    raw = git(repo, "ls-tree", "-r", "-z", rev, "--", ASSETS_PREFIX)
    blobs = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        blobs[path.decode("utf-8", "replace")] = meta.decode("ascii")
    return blobs


def main():
    repo = Path(__file__).resolve().parents[2]
    head = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    base_exists = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", BASE + "^{commit}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    base_blob = git(repo, "show", BASE + ":" + THEME) if base_exists else b""
    head_blob = (repo / THEME).read_bytes()

    base_const = parse_constants(base_blob.decode("utf-8"))
    head_const = parse_constants(head_blob.decode("utf-8"))

    base_lines = norm(base_blob).decode("utf-8").split("\n")
    head_lines = norm(head_blob).decode("utf-8").split("\n")
    if len(base_lines) != len(head_lines):
        raise AssertionError("Theme.qml line count changed")
    changed = []
    for index, (before, after) in enumerate(zip(base_lines, head_lines), 1):
        if before != after:
            changed.append({"line": index, "base": before.strip(),
                            "head": after.strip()})

    nonvisual_base = nonvisual_projection(base_blob)
    nonvisual_head = nonvisual_projection(head_blob)

    base_assets = asset_tree(repo, BASE)
    head_assets = asset_tree(repo, "HEAD")
    asset_delta = sorted(
        path for path in set(base_assets) | set(head_assets)
        if base_assets.get(path) != head_assets.get(path))

    diff_rev = BASE + ".." + head if head != BASE else BASE
    diff_raw = git(repo, "diff", "--name-status", diff_rev, "--").decode(
        "utf-8", "replace")
    diff_paths = [line for line in diff_raw.splitlines() if line.strip()]

    directive_bytes = (DIRECTIVE.read_bytes() if DIRECTIVE.exists() else b"")
    directive_sha = sha256(directive_bytes)

    result = {
        "schema_version": 1,
        "evidence_class": "STATIC SOURCE ONLY / SYNTHETIC",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": BASE,
        "head_commit": head,
        "governing_directive": {
            "path": str(DIRECTIVE),
            "sha256": directive_sha,
            "matches_rev3_pin": directive_sha == DIRECTIVE_SHA256,
        },
        "theme_sha256": {"base": sha256(base_blob), "head": sha256(head_blob)},
        "constants": {"base": base_const, "head": head_const,
                      "approved": APPROVED},
        "geometry_tuple_exact": head_const == APPROVED,
        "base_tuple_reproduced": base_const == BASE_TUPLE,
        "projection": {"base": projection(base_const),
                       "head": projection(head_const)},
        "projection_sha256": {
            "base": sha256(canonical(projection(base_const))),
            "head": sha256(canonical(projection(head_const))),
        },
        "nonvisual_theme_projection_sha256": {
            "base": sha256(nonvisual_base.encode("utf-8")),
            "head": sha256(nonvisual_head.encode("utf-8")),
            "identical": nonvisual_base == nonvisual_head,
        },
        "theme_changed_lines": changed,
        "theme_changed_lines_are_geometry_only": all(
            "readonly property int" in row["base"]
            and "readonly property int" in row["head"] for row in changed)
        and len(changed) == 2,
        "approved_asset_blobs_changed": asset_delta,
        "approved_assets_byte_identical": not asset_delta,
        "base_to_head_diff_paths": diff_paths,
        "visual_input_freeze_byte_level": (
            nonvisual_base == nonvisual_head and not asset_delta),
        "pixel_visual_owner_acceptance": "HOLD / NOT_RUN",
        "pixel_sampling_performed": False,
        "compiled_qt_run": "NOT_RUN",
        "native_runtime": "NOT_RUN",
        "boundary": ("Headless byte-level projection only. No artwork, "
                     "wallpaper or icon regenerated; no pixel/visual approval "
                     "claimed; no merge or PR approval performed."),
    }
    out = Path(__file__).resolve().parent / "geometry_projection.json"
    out.write_bytes(canonical(result) + b"\n")
    print(json.dumps({
        "head_commit": head,
        "head_tuple": head_const,
        "geometry_tuple_exact": result["geometry_tuple_exact"],
        "base_tuple_reproduced": result["base_tuple_reproduced"],
        "projected_width_base": result["projection"]["base"][
            "projected_dock_surface_width_px"],
        "projected_width_head": result["projection"]["head"][
            "projected_dock_surface_width_px"],
        "nonvisual_projection_identical": result[
            "nonvisual_theme_projection_sha256"]["identical"],
        "changed_lines": changed,
        "asset_delta": asset_delta,
        "diff_paths": diff_paths,
        "output": str(out),
    }, indent=2, sort_keys=True))
    return 0 if (result["geometry_tuple_exact"]
                 and result["base_tuple_reproduced"]
                 and result["approved_assets_byte_identical"]
                 and result["theme_changed_lines_are_geometry_only"]) else 1


if __name__ == "__main__":
    sys.exit(main())
