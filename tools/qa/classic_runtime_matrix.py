#!/usr/bin/env python3
"""Bounded compiled-Qt Classic runtime smoke matrix (offline orchestrator).

Runs the real compiled binary at three supported window sizes. Each run must
exit zero, confirm approved-art startup, report a visible QML window, and
produce a clean diagnostic log. Captures are verified with the existing PNG
validator. Missing compiler/binary is a NOT RUN prerequisite, never a PASS.
Synthetic stand-ins used by unit tests can never become real runtime evidence.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from tools import check_screenshot, qt_smoke

SCHEMA_VERSION = 1
SIZES = ((760, 500), (1200, 750), (1920, 1080))
COMPILER_TOOLS = ("cmake", "ninja", "qmake", "qmake6", "pkg-config")
READY_MARKER = b"CANOPY_CLASSIC_WINDOW_READY"
ART_MARKER = b"CANOPY_APPROVED_ART_VERIFIED"
MAX_OUTPUT_BYTES = 65_536
MAX_TIMEOUT_SECONDS = 30
MIN_TIMEOUT_SECONDS = 2
MAX_LIVENESS_SECONDS = 5.0


class MatrixError(ValueError):
    """Invalid or unsafe orchestrator input."""


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    exited_during_liveness: bool = False


def normalize_sizes(sizes=None):
    """Only the three approved resolutions are allowed; no invented sizes."""
    if sizes is None:
        return SIZES
    result = []
    for entry in sizes:
        try:
            pair = tuple(int(part) for part in entry)
        except (TypeError, ValueError) as exc:
            raise MatrixError("size must be a (width, height) pair") from exc
        if len(pair) != 2 or pair not in SIZES or pair in result:
            raise MatrixError("unsupported or duplicate smoke-matrix size")
        result.append(pair)
    if not result:
        raise MatrixError("at least one size is required")
    return tuple(result)


def build_command(binary, art_dir, wallpaper, width, height, screenshot, *,
                  terminal=None, framing_review=False):
    """Build only flags that prototype/classic/main.cpp actually implements."""
    if (int(width), int(height)) not in SIZES:
        raise MatrixError("unsupported smoke-matrix size")
    label = f"{int(width)}x{int(height)}"
    command = [
        str(binary),
        "--approved-art-dir", str(art_dir),
        "--landscape-wallpaper", str(wallpaper),
        "--self-test-approved",
        "--self-test-size", label,
        "--self-test-screenshot", str(screenshot),
    ]
    if terminal is not None:
        command.extend(("--terminal-refinement", str(terminal)))
    if framing_review:
        command.append("--icon-framing-review")
    return command


def file_sha256(path):
    """Hash a regular, non-symlink capture without following redirects."""
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise MatrixError("capture is missing or unsafe")
    digest = hashlib.sha256()
    with candidate.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assess_prerequisites(binary, *, compiler_probe=None, synthetic=False):
    """Report binary and compiler availability; never fabricate a runtime PASS."""
    probe = compiler_probe or shutil.which
    compilers = {name: bool(probe(name)) for name in COMPILER_TOOLS}
    candidate = Path(binary) if binary else None
    binary_available = bool(
        candidate and candidate.is_file() and os.access(candidate, os.X_OK)
    )
    return {
        "status": "PASS" if binary_available else "NOT_RUN",
        "binary_name": candidate.name if candidate else None,
        "binary_available": binary_available,
        "compiler_available": synthetic or any(compilers.values()),
        "compilers_found": sorted(name for name, found in compilers.items() if found),
        "reason": None if binary_available else (
            "compiled Qt binary not available; runtime smoke is NOT RUN"
        ),
    }


def _cap(data):
    return (data or b"")[:MAX_OUTPUT_BYTES]


def run_process(command, timeout_seconds, liveness_seconds=0.5):
    """Run the binary, watch for an early exit, and enforce a hard timeout."""
    env = os.environ.copy()
    env.setdefault("QT_QUICK_BACKEND", "software")
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        start_new_session=True, close_fds=True,
    )
    try:
        time.sleep(liveness_seconds)
        exited_during_liveness = process.poll() is not None
        try:
            remaining = max(0.01, timeout_seconds - liveness_seconds)
            stdout, stderr = process.communicate(timeout=remaining)
            timed_out = False
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            timed_out = True
        return ProcessOutcome(
            returncode=process.returncode, stdout=_cap(stdout), stderr=_cap(stderr),
            timed_out=timed_out, exited_during_liveness=exited_during_liveness,
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def _evaluate_size(width, height, outcome, screenshot):
    """One row of evidence; reuse the existing QML and PNG validators."""
    label = f"{width}x{height}"
    combined = (outcome.stdout or b"") + b"\n" + (outcome.stderr or b"")
    qml_errors = qt_smoke.qml_diagnostics(outcome.stderr or b"")
    row = {
        "resolution": label,
        "status": "FAIL",
        "exit_code": outcome.returncode,
        "timed_out": bool(outcome.timed_out),
        "exited_during_liveness": bool(outcome.exited_during_liveness),
        "window_ready": READY_MARKER in combined,
        "approved_art_verified": ART_MARKER in combined,
        "qml_errors": qml_errors[:10],
        "screenshot": Path(screenshot).name if screenshot is not None else None,
        "screenshot_sha256": None,
        "png_valid": False,
    }
    if (outcome.timed_out or outcome.returncode != 0 or qml_errors
            or not row["window_ready"] or not row["approved_art_verified"]):
        return row
    try:
        check_screenshot.verify_png(Path(screenshot), width, height)
        row["png_valid"] = True
        row["screenshot_sha256"] = file_sha256(screenshot)
        row["status"] = "PASS"
    except (OSError, ValueError):
        pass
    return row


def _not_run_row(width, height):
    return {
        "resolution": f"{width}x{height}",
        "status": "NOT_RUN",
        "exit_code": None,
        "timed_out": False,
        "exited_during_liveness": False,
        "window_ready": False,
        "approved_art_verified": False,
        "qml_errors": [],
        "screenshot": None,
        "screenshot_sha256": None,
        "png_valid": False,
    }


def run_matrix(*, binary, art_dir=None, wallpaper=None, output_dir=None,
               timeout_seconds=15, liveness_seconds=0.5, sizes=None,
               terminal=None, framing_review=False, synthetic=False,
               runner=None, compiler_probe=None, prerequisites=None):
    """Return an auditable matrix report; never claim synthetic runtime data."""
    if (type(timeout_seconds) is not int
            or not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS):
        raise MatrixError("timeout must be an integer within the bounded range")
    if type(liveness_seconds) not in (int, float) or not (
            0 <= liveness_seconds <= MAX_LIVENESS_SECONDS):
        raise MatrixError("liveness_seconds outside the bounded range")
    selected = normalize_sizes(sizes)
    prereq = prerequisites if prerequisites is not None else assess_prerequisites(
        binary, compiler_probe=compiler_probe, synthetic=synthetic,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "compiled-qt-classic-runtime-smoke-matrix",
        "capture_source": (
            "synthetic-test-stand-in" if synthetic else "real-compiled-binary"
        ),
        "prerequisites": prereq,
        "timeout_seconds": timeout_seconds,
        "liveness_seconds": liveness_seconds,
        "sizes": [f"{w}x{h}" for w, h in selected],
        "tests": [],
        "mechanics_status": "NOT_RUN",
        "overall": "NOT_RUN",
        "notes": [],
    }
    if prereq.get("status") != "PASS":
        report["tests"] = [_not_run_row(w, h) for w, h in selected]
        report["notes"].append("binary/compiler prerequisite absent; no Qt process launched")
        return report

    execute = runner if runner is not None else run_process
    for width, height in selected:
        label = f"{width}x{height}"
        screenshot = Path(output_dir) / f"qt-{label}.png" if output_dir else None
        command = build_command(
            binary, art_dir, wallpaper, width, height, screenshot,
            terminal=terminal, framing_review=framing_review,
        )
        try:
            outcome = execute(command, timeout_seconds, liveness_seconds)
            row = _evaluate_size(width, height, outcome, screenshot)
        except (OSError, subprocess.SubprocessError, MatrixError) as exc:
            row = _not_run_row(width, height)
            row["status"] = "FAIL"
            row["error"] = str(exc)[:200]
        row["command_flags"] = [item for item in command if item.startswith("--")]
        report["tests"].append(row)

    mechanics = "PASS" if all(row["status"] == "PASS" for row in report["tests"]) else "FAIL"
    report["mechanics_status"] = mechanics
    if synthetic:
        report["notes"].append("synthetic stand-in: mechanics only, not runtime evidence")
    else:
        report["overall"] = mechanics
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--approved-art-dir", type=Path)
    parser.add_argument("--landscape-wallpaper", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--terminal-refinement", type=Path)
    parser.add_argument("--icon-framing-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output_dir is not None:
            args.output_dir.mkdir(parents=True, exist_ok=True)
        report = run_matrix(
            binary=args.binary, art_dir=args.approved_art_dir,
            wallpaper=args.landscape_wallpaper, output_dir=args.output_dir,
            timeout_seconds=args.timeout, terminal=args.terminal_refinement,
            framing_review=args.icon_framing_review,
        )
    except MatrixError as exc:
        print("QT_RUNTIME_MATRIX_BLOCKED:", exc, file=sys.stderr)
        return 2
    if args.output_dir is not None:
        (args.output_dir / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
    print("QT_CLASSIC_RUNTIME_MATRIX_" + report["overall"])
    return {"PASS": 0, "FAIL": 1, "NOT_RUN": 2}[report["overall"]]


if __name__ == "__main__":
    raise SystemExit(main())
