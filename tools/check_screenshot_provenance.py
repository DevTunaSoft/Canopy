#!/usr/bin/env python3
"""Offline, standard-library-only validator for screenshot evidence manifests.

A manifest records exact PNG paths, expected dimensions, SHA-256 digests, a
source commit and a Qt capture command.  This tool checks that the declared
metadata is internally consistent with the bytes on disk.  It never executes
the capture command, loads Qt, imports screenshot code, or renders anything.

PASS means only that metadata and bytes agree.  It does NOT prove the image
came from compiled Qt, that the capture command was actually run, that the
source commit built the image, or that the screenshot grants visual approval.
Human visual acceptance remains a separate gate.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib


MANIFEST_VERSION = 1
MAX_MANIFEST_BYTES = 65_536
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 256
MAX_PATH_CHARS = 256
MAX_COMMAND_CHARS = 1024
MAX_DIMENSION = 8_192
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SUPPORTED_DIMENSIONS = frozenset({
    (1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160),
})
REQUIRED_FIELDS = frozenset({
    "manifest_version", "source_commit", "capture_command", "entries",
})
ENTRY_FIELDS = frozenset({"path", "width", "height", "sha256"})
COMMIT_RE = re.compile(r"[0-9a-f]{40}", re.ASCII)
DIGEST_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
PATH_COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*", re.ASCII)
CHUNK_TYPE_RE = re.compile(r"[A-Za-z]{4}", re.ASCII)
BIT_DEPTH_BY_COLOR = {
    0: frozenset({1, 2, 4, 8, 16}),
    2: frozenset({8, 16}),
    3: frozenset({1, 2, 4, 8}),
    4: frozenset({8, 16}),
    6: frozenset({8, 16}),
}

DISCLAIMER = (
    "metadata only; not proof of compiled Qt, capture execution, "
    "or visual approval"
)


class ProvenanceValidationError(ValueError):
    """Untrusted screenshot manifest or referenced PNG is invalid."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ProvenanceValidationError(f"invalid JSON constant: {value}")


def _clean_string(value, name, maximum):
    if (not isinstance(value, str) or not value or len(value) > maximum
            or value != value.strip() or CONTROL_RE.search(value)):
        raise ProvenanceValidationError(
            f"{name} must be a clean string, max {maximum} characters"
        )
    return value


def _validate_relative_png_path(value):
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_CHARS:
        raise ProvenanceValidationError("path must be a bounded relative string")
    if "\\" in value or ":" in value or value.startswith("/"):
        raise ProvenanceValidationError("path escapes or uses a foreign separator")
    if not value.endswith(".png"):
        raise ProvenanceValidationError("path must name a .png file")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ProvenanceValidationError("path contains an empty or traversal component")
    if any(not PATH_COMPONENT_RE.fullmatch(part) for part in parts):
        raise ProvenanceValidationError("path component is not a safe name")
    return parts


def _resolve_png(base, parts):
    target = base
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise ProvenanceValidationError("path traverses a symlink")
    if target.is_symlink() or not target.is_file():
        raise ProvenanceValidationError("PNG is not a regular local file")
    return target


def _parse_png(raw, label):
    if len(raw) < len(PNG_SIGNATURE) or raw[:8] != PNG_SIGNATURE:
        raise ProvenanceValidationError(f"{label}: corrupt PNG signature")
    pos = 8
    width = height = None
    saw_idat = False
    saw_iend = False
    first_chunk = True
    while pos < len(raw):
        if pos + 8 > len(raw):
            raise ProvenanceValidationError(f"{label}: truncated PNG chunk header")
        length = struct.unpack_from(">I", raw, pos)[0]
        chunk_type = raw[pos + 4:pos + 8]
        if not CHUNK_TYPE_RE.fullmatch(chunk_type.decode("ascii", "replace")):
            raise ProvenanceValidationError(f"{label}: malformed PNG chunk type")
        end = pos + 12 + length
        if length > len(raw) or end > len(raw):
            raise ProvenanceValidationError(f"{label}: truncated PNG chunk")
        data = raw[pos + 8:pos + 8 + length]
        declared_crc = struct.unpack_from(">I", raw, pos + 8 + length)[0]
        actual_crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        if declared_crc != actual_crc:
            raise ProvenanceValidationError(f"{label}: PNG chunk CRC mismatch")
        if first_chunk and chunk_type != b"IHDR":
            raise ProvenanceValidationError(f"{label}: IHDR must be the first PNG chunk")
        first_chunk = False
        if chunk_type == b"IHDR":
            if width is not None or length != 13:
                raise ProvenanceValidationError(f"{label}: malformed PNG IHDR")
            width, height = struct.unpack_from(">II", data, 0)
            bit_depth, color_type = data[8], data[9]
            compression, filter_method, interlace = data[10], data[11], data[12]
            if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
                raise ProvenanceValidationError(f"{label}: invalid PNG dimensions")
            if color_type not in BIT_DEPTH_BY_COLOR:
                raise ProvenanceValidationError(f"{label}: unsupported PNG color type")
            if bit_depth not in BIT_DEPTH_BY_COLOR[color_type]:
                raise ProvenanceValidationError(f"{label}: invalid PNG bit depth")
            if compression != 0 or filter_method != 0 or interlace not in (0, 1):
                raise ProvenanceValidationError(f"{label}: unsupported PNG encoding")
        elif chunk_type == b"IDAT":
            saw_idat = True
        elif chunk_type == b"IEND":
            if length != 0 or end != len(raw):
                raise ProvenanceValidationError(f"{label}: malformed PNG IEND")
            saw_iend = True
        pos = end
    if width is None or not saw_idat or not saw_iend:
        raise ProvenanceValidationError(f"{label}: incomplete PNG chunk stream")
    return width, height


def validate_provenance(manifest_path):
    """Validate an untrusted screenshot evidence manifest and its PNGs."""
    manifest_path = Path(manifest_path)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ProvenanceValidationError("manifest must be a regular local file")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ProvenanceValidationError("manifest exceeds 64 KiB")
    try:
        text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceValidationError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.keys() != REQUIRED_FIELDS:
        raise ProvenanceValidationError(
            "manifest must be one object with exactly the required fields"
        )

    if type(manifest["manifest_version"]) is not int or manifest["manifest_version"] != MANIFEST_VERSION:
        raise ProvenanceValidationError("unsupported manifest_version")
    commit = manifest["source_commit"]
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise ProvenanceValidationError("source_commit must be a lowercase 40-hex SHA")
    _clean_string(manifest["capture_command"], "capture_command", MAX_COMMAND_CHARS)

    entries = manifest["entries"]
    if not isinstance(entries, list) or not entries:
        raise ProvenanceValidationError("entries must be a non-empty list")
    if len(entries) > MAX_ENTRIES:
        raise ProvenanceValidationError(f"entries exceed {MAX_ENTRIES}")
    base = manifest_path.parent
    seen_paths = set()
    for index, entry in enumerate(entries):
        label = f"entry {index}"
        if not isinstance(entry, dict) or entry.keys() != ENTRY_FIELDS:
            raise ProvenanceValidationError(
                f"{label}: expected exactly path/width/height/sha256"
            )
        parts = _validate_relative_png_path(entry["path"])
        normalized = "/".join(parts)
        if normalized in seen_paths:
            raise ProvenanceValidationError(f"duplicate entry path: {normalized}")
        seen_paths.add(normalized)
        for key in ("width", "height"):
            value = entry[key]
            if type(value) is not int or not (0 < value <= MAX_DIMENSION):
                raise ProvenanceValidationError(f"{label}: {key} must be a positive integer")
        dimensions = (entry["width"], entry["height"])
        if dimensions not in SUPPORTED_DIMENSIONS:
            raise ProvenanceValidationError(f"{label}: unsupported dimensions {dimensions}")
        digest = entry["sha256"]
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            raise ProvenanceValidationError(f"{label}: sha256 must be lowercase 64-hex")

        target = _resolve_png(base, parts)
        if target.stat().st_size > MAX_PNG_BYTES:
            raise ProvenanceValidationError(f"{label}: PNG exceeds 64 MiB")
        stat_before = target.stat()
        raw = target.read_bytes()
        stat_after = target.stat()
        if (len(raw) != stat_before.st_size
                or stat_before.st_mtime_ns != stat_after.st_mtime_ns
                or stat_before.st_ino != stat_after.st_ino):
            raise ProvenanceValidationError(f"{label}: PNG changed while reading")
        actual_width, actual_height = _parse_png(raw, label)
        if (actual_width, actual_height) != dimensions:
            raise ProvenanceValidationError(
                f"{label}: PNG dimensions {actual_width}x{actual_height} "
                f"do not match declared {dimensions[0]}x{dimensions[1]}"
            )
        actual_digest = hashlib.sha256(raw).hexdigest()
        if actual_digest != digest:
            raise ProvenanceValidationError(f"{label}: sha256 mismatch")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="screenshot evidence manifest JSON")
    args = parser.parse_args(argv)
    try:
        manifest = validate_provenance(args.manifest)
    except (ProvenanceValidationError, OSError) as exc:
        print(f"SCREENSHOT_PROVENANCE_FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"SCREENSHOT_PROVENANCE_PASS: {len(manifest['entries'])} entries, "
        f"commit {manifest['source_commit']} ({DISCLAIMER})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
