#!/usr/bin/env python3
"""Build a private, offline before/after review from two Mint Qt smoke reports.

Does not run Qt, change image pixels, upload screenshots or grant visual approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from tools.mint_classic_qt_smoke import png_size

RESOLUTIONS = ((1920, 1080), (1200, 750), (760, 500))
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")


class ReviewError(ValueError):
    """Evidence is missing, unsafe, mismatched or not independently approved."""


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_capture(directory, expected_framing):
    root = Path(directory)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ReviewError("capture directory must be real and absolute")
    report_path = root / "report.json"
    if (report_path.is_symlink() or not report_path.is_file()
            or report_path.stat().st_size > 64_000):
        raise ReviewError("capture report missing or unsafe")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ReviewError("invalid capture report") from exc
    if (not isinstance(report, dict) or report.get("schema_version") != 1
            or report.get("environment") != "linuxmint"
            or report.get("qt_smoke") != "PASS"
            or report.get("framing_review") is not expected_framing
            or not isinstance(report.get("tests"), list)
            or len(report["tests"]) != len(RESOLUTIONS)):
        raise ReviewError("capture is not a matching PASS Mint Qt report")
    source = report.get("declared_source_sha")
    binary = report.get("verified_binary_sha256")
    if (not isinstance(source, str) or not HEX40.fullmatch(source)
            or not isinstance(binary, str) or not HEX64.fullmatch(binary)):
        raise ReviewError("missing exact source/binary identity")
    screenshots = []
    for index, (width, height) in enumerate(RESOLUTIONS):
        row = report["tests"][index]
        name = f"qt-{width}x{height}.png"
        if (not isinstance(row, dict) or row.get("resolution") != f"{width}x{height}"
                or row.get("screenshot") != name or row.get("status") != "PASS"
                or row.get("exit_code") != 0
                or not isinstance(row.get("screenshot_sha256"), str)
                or not HEX64.fullmatch(row["screenshot_sha256"])):
            raise ReviewError("incomplete or unexpected screenshot report")
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ReviewError("screenshot missing or linked")
        try:
            dims = png_size(path)
        except ValueError as exc:
            raise ReviewError("corrupt PNG screenshot") from exc
        if dims != (width, height) or sha256(path) != row["screenshot_sha256"]:
            raise ReviewError("screenshot content differs from report")
        screenshots.append((name, path, row["screenshot_sha256"]))
    return source, binary, screenshots


def make_gallery(baseline, candidate, output):
    """Validate all evidence before creating a new private review directory."""
    before_sha, before_binary, before = read_capture(baseline, False)
    after_sha, after_binary, after = read_capture(candidate, True)
    if (before_sha, before_binary) != (after_sha, after_binary):
        raise ReviewError("baseline and candidate must use identical source and Qt binary")
    destination = Path(output)
    if (not destination.is_absolute() or destination.is_symlink()
            or destination.exists() or not destination.parent.is_dir()
            or destination.parent.is_symlink()):
        raise ReviewError("output must be a new absolute directory with a real parent")
    destination.mkdir(mode=0o700, exist_ok=False)
    for sub in ("before", "after"):
        (destination / sub).mkdir(mode=0o700)
    rows = []
    evidence = []
    for index, (width, height) in enumerate(RESOLUTIONS):
        name, old_path, old_hash = before[index]
        _, new_path, new_hash = after[index]
        for sub, path, digest in (("before", old_path, old_hash),
                                  ("after", new_path, new_hash)):
            copied = destination / sub / name
            shutil.copyfile(path, copied, follow_symlinks=False)
            copied.chmod(0o600)
            if sha256(copied) != digest:
                raise ReviewError("copied screenshot hash mismatch")
        resolution = f"{width} × {height}"
        rows.append(f'''<section><h2>{resolution}</h2><div class="comparison">
<figure><a href="before/{name}"><img src="before/{name}" width="{width}" height="{height}" alt="Baseline actual Qt capture, {resolution}"></a><figcaption>Baseline · original framing</figcaption></figure>
<figure><a href="after/{name}"><img src="after/{name}" width="{width}" height="{height}" alt="Candidate actual Qt capture, {resolution}"></a><figcaption>Candidate · opt-in framing</figcaption></figure>
</div></section>''')
        evidence.append({"resolution": f"{width}x{height}",
                         "baseline_sha256": old_hash, "candidate_sha256": new_hash})
    html = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canopy Classic — local Qt screenshot review</title>
<style>body{font:16px system-ui,sans-serif;margin:0 auto;max-width:1600px;padding:24px;background:#10141b;color:#edf2fa}p{max-width:900px;line-height:1.55;color:#bfc9d8}.comparison{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}figure{margin:0}img{display:block;width:100%;height:auto;border-radius:10px;border:1px solid #435164}figcaption{padding:10px 0 24px;color:#cfdae8}section{border-top:1px solid #344052;padding-top:12px}@media(max-width:800px){.comparison{grid-template-columns:1fr}}</style>
<h1>Canopy Classic — actual Qt screenshot evidence</h1>
<p>Two separately supplied PASS smoke reports for the same declared source commit and measured binary. Images are copied byte-for-byte and hash-checked; click to inspect full resolution. No artwork is retouched or regenerated.</p>
<p><strong>NOT visually approved. NOT proof of a real Mint acceptance run or binary source provenance.</strong> Confirm the original run environment and personally inspect the screenshots before accepting any visual change.</p>
''' + "\n".join(rows) + "\n</html>\n"
    (destination / "index.html").write_text(html, encoding="utf-8")
    (destination / "index.html").chmod(0o600)
    manifest = {"schema_version": 1, "source_sha_claim": before_sha,
                "measured_binary_sha256": before_binary,
                "visual_owner_approval": "NOT_RUN",
                "actual_mint_session_independently_verified": False,
                "images_copied_unchanged": True, "screenshots": evidence}
    (destination / "review.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "review.json").chmod(0o600)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        make_gallery(args.baseline_dir, args.candidate_dir, args.output_dir)
    except (ReviewError, OSError) as exc:
        print("CLASSIC_VISUAL_REVIEW_BLOCKED:", exc, file=sys.stderr)
        return 2
    print("CLASSIC_VISUAL_REVIEW_READY: inspect locally; visual approval NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
