"""Bounded pre-flight limits for Qt screenshots, before any PNG inspection.

This is a size/dimension gate, not a PNG decoder. It reads at most the file
signature and the IHDR chunk, decides whether the image is safe to inspect,
and leaves structural/decompression validation to existing validators such as
``tools.check_screenshot.verify_png`` or ``tools.mint_classic_qt_smoke.png_size``.

No background services, polling, privileged actions or unbounded reads.
"""
import os
from pathlib import Path
import stat
import struct
from typing import NamedTuple

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Signature (8) plus one chunk header (8). Anything shorter cannot be a PNG.
MIN_PNG_BYTES = 16


class ScreenshotLimitError(ValueError):
    """A screenshot is missing, unsafe or outside the configured limits."""


class ScreenshotLimits(NamedTuple):
    """Hard bounds applied before a screenshot is inspected."""

    max_bytes: int = 40_000_000
    max_width: int = 3840
    max_height: int = 2160


class ScreenshotInfo(NamedTuple):
    """Small result returned by the bounded pre-flight."""

    width: int
    height: int
    byte_size: int


DEFAULT_LIMITS = ScreenshotLimits()


def _validate_limits(limits):
    if not isinstance(limits, ScreenshotLimits):
        raise TypeError("limits must be a ScreenshotLimits instance")
    for name in ScreenshotLimits._fields:
        value = getattr(limits, name)
        if type(value) is not int or not 0 < value <= 2**31 - 1:
            raise ValueError(name + " must be a positive bounded integer")


def _read_exact(descriptor, count):
    """Read at most ``count`` bytes from a descriptor; never more."""
    parts = []
    remaining = count
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


def _has_symlink_component(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def check_limits(path, limits=None):
    """Return ``ScreenshotInfo`` for a PNG that passes bounded pre-flight.

    Rejects oversized files, oversized dimensions and truncated headers.
    Reads only the signature and IHDR chunk; image data is never decoded.
    """
    limits = DEFAULT_LIMITS if limits is None else limits
    _validate_limits(limits)
    path = Path(path)
    if not path.is_absolute():
        raise ScreenshotLimitError("absolute screenshot path required")
    if _has_symlink_component(path):
        raise ScreenshotLimitError("screenshot path contains a symlink")
    # O_BINARY avoids CR/LF translation on Windows; absent on Linux (no-op).
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScreenshotLimitError("screenshot missing or unsafe") from exc
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ScreenshotLimitError("screenshot is not a regular file")
        byte_size = file_stat.st_size
        if byte_size > limits.max_bytes:
            raise ScreenshotLimitError(
                "screenshot file {} bytes exceeds {} byte limit".format(
                    byte_size, limits.max_bytes
                )
            )
        if byte_size < MIN_PNG_BYTES:
            raise ScreenshotLimitError("truncated PNG: file too small")

        if _read_exact(descriptor, 8) != PNG_SIGNATURE:
            raise ScreenshotLimitError("invalid PNG signature")
        header = _read_exact(descriptor, 8)
        if len(header) != 8:
            raise ScreenshotLimitError("truncated PNG: missing chunk header")
        length, kind = struct.unpack(">I4s", header)
        if kind != b"IHDR" or length != 13:
            raise ScreenshotLimitError("missing PNG image header")
        payload = _read_exact(descriptor, 13)
        if len(payload) != 13:
            raise ScreenshotLimitError("truncated PNG: incomplete image header")
        if len(_read_exact(descriptor, 4)) != 4:
            raise ScreenshotLimitError("truncated PNG: incomplete header CRC")

        width, height = struct.unpack(">II", payload[:8])
        if width == 0 or height == 0:
            raise ScreenshotLimitError("invalid PNG dimensions")
        if width > limits.max_width:
            raise ScreenshotLimitError(
                "PNG width {} exceeds {} pixel limit".format(width, limits.max_width)
            )
        if height > limits.max_height:
            raise ScreenshotLimitError(
                "PNG height {} exceeds {} pixel limit".format(height, limits.max_height)
            )
        return ScreenshotInfo(width, height, byte_size)
    finally:
        os.close(descriptor)


def guard(path, inspector, limits=None):
    """Pre-flight ``path``, then call ``inspector(path)`` only when safe.

    Composes this bounded gate with an existing full validator. Returns a
    ``(inspector_result, ScreenshotInfo)`` pair. The inspector is never called
    when the pre-flight rejects the file.
    """
    info = check_limits(path, limits)
    if not callable(inspector):
        raise TypeError("inspector must be callable")
    return inspector(path), info
