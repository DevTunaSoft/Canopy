"""Build deterministic screenshot evidence manifests from existing captures.

Reads real PNG files that are already on disk. It never captures a screen,
launches a process, writes a file, polls, or starts a background service.

PNG integrity and hashing reuse the bounded validators in
``tools.mint_classic_qt_smoke`` so evidence here matches the Mint smoke
runner's definition of a real, nonuniform capture.
"""
import json
import re
from pathlib import Path

from tools.mint_classic_qt_smoke import (
    MintSmokeError,
    PNG_MAX_FILE_SIZE,
    file_sha256,
    png_size,
)

SCHEMA_VERSION = 1
MAX_CAPTURES = 64
MAX_NAME_LENGTH = 128
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")


class ManifestError(ValueError):
    """Input cannot produce a trustworthy manifest."""


class CaptureError(ManifestError):
    """One capture failed verification; ``reason`` is a stable failure code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _has_symlink_component(path):
    """Check the file and every parent, for absolute and relative paths alike."""
    current = Path(path)
    while True:
        if current.is_symlink():
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _require_file(path, missing_reason, unsafe_reason):
    path = Path(path)
    if _has_symlink_component(path):
        raise CaptureError(unsafe_reason)
    if not path.is_file():
        raise CaptureError(missing_reason)
    return path


def _valid_name(name):
    return (
        isinstance(name, str)
        and 0 < len(name) <= MAX_NAME_LENGTH
        and name.endswith(".png")
        and "/" not in name
        and "\\" not in name
        and ".." not in Path(name).parts
    )


def verify_capture(*, name, path, sha256, width=None, height=None):
    """Verify one existing capture and return its manifest entry.

    Raises ``CaptureError`` with a stable reason instead of guessing or
    synthesizing evidence. No file is ever created here.
    """
    if not _valid_name(name):
        raise CaptureError("BAD_NAME")
    if not isinstance(sha256, str) or SHA256.fullmatch(sha256) is None:
        raise CaptureError("BAD_SHA256")
    for label, value in (("width", width), ("height", height)):
        if value is not None and (type(value) is not int or value < 1):
            raise CaptureError("BAD_DIMENSIONS")

    capture = _require_file(path, "MISSING_CAPTURE", "UNSAFE_CAPTURE")
    size = capture.stat().st_size
    if size < 57 or size > PNG_MAX_FILE_SIZE:
        raise CaptureError("INVALID_PNG")

    if file_sha256(capture) != sha256:
        raise CaptureError("HASH_MISMATCH")
    try:
        measured_width, measured_height = png_size(capture)
    except (MintSmokeError, OSError, ValueError):
        raise CaptureError("INVALID_PNG") from None
    if ((width is not None and width != measured_width)
            or (height is not None and height != measured_height)):
        raise CaptureError("DIMENSION_MISMATCH")

    return {
        "name": name,
        "sha256": sha256,
        "width": measured_width,
        "height": measured_height,
        "bytes": size,
        "status": "PASS",
    }


def build_manifest(*, captures, binary, source_sha):
    """Return a deterministic manifest built only from verified captures.

    ``captures`` is a sequence of mappings with ``name``, ``path`` and
    ``sha256`` keys, and optional integer ``width``/``height`` declarations.
    ``binary`` is the existing compiled producer of those captures.
    ``source_sha`` is the declared 40-character source commit.

    Unverifiable inputs land in ``failures`` with a stable reason; they are
    never listed as captures. Overall status is PASS only with at least one
    verified capture and no failures.
    """
    if not isinstance(source_sha, str) or SOURCE_SHA.fullmatch(source_sha) is None:
        raise ManifestError("BAD_SOURCE_SHA")
    try:
        binary_path = _require_file(binary, "ABSENT_BINARY", "UNSAFE_BINARY")
    except CaptureError as exc:
        raise ManifestError(exc.reason) from None
    binary_hash = file_sha256(binary_path)

    if isinstance(captures, (str, bytes)) or not isinstance(captures, (list, tuple)):
        raise ManifestError("BAD_CAPTURES")
    if len(captures) > MAX_CAPTURES:
        raise ManifestError("TOO_MANY_CAPTURES")

    entries = []
    failures = []
    seen_names = set()
    for spec in captures:
        name = spec.get("name") if isinstance(spec, dict) else None
        label = name if _valid_name(name) else "<invalid>"
        if _valid_name(name):
            if name in seen_names:
                raise ManifestError("DUPLICATE_NAME")
            seen_names.add(name)
        if not isinstance(spec, dict):
            failures.append({"name": label, "reason": "BAD_SPEC"})
            continue
        try:
            entry = verify_capture(
                name=name,
                path=spec.get("path"),
                sha256=spec.get("sha256"),
                width=spec.get("width"),
                height=spec.get("height"),
            )
        except CaptureError as exc:
            failures.append({"name": label, "reason": exc.reason})
        else:
            entries.append(entry)

    entries.sort(key=lambda item: item["name"])
    failures.sort(key=lambda item: item["name"])
    return {
        "schema_version": SCHEMA_VERSION,
        "source_sha": source_sha,
        "binary_sha256": binary_hash,
        "status": "PASS" if entries and not failures else "FAIL",
        "captures": entries,
        "failures": failures,
    }


def render_manifest(manifest):
    """Serialize a manifest to stable deterministic JSON text.

    Sorted keys, fixed fields, no paths, no timestamps, no environment data.
    """
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
