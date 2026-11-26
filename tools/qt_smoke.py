#!/usr/bin/env python3
"""Run a Qt app under Xvfb and require it to stay alive until terminated."""
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

READY_MARKER = b"CANOPY_CLASSIC_WINDOW_READY"
READY_DEADLINE_SECONDS = 12.0
LIVENESS_SECONDS = 5.0
POLL_SECONDS = 0.05
MAX_STARTUP_BYTES = 262144

def qml_diagnostics(stderr: bytes) -> list[str]:
    """Return actionable QML binding/runtime diagnostics (not benign Qt notices)."""
    markers = (
        "Unable to assign",
        "ReferenceError:",
        "TypeError:",
        "Binding loop detected",
        "QQmlApplicationEngine failed to load component",
    )
    return [line for line in stderr.decode(errors="replace").splitlines()
            if any(marker in line for marker in markers)]


class StartupFailure(RuntimeError):
    """Helper exited before the smoke observation window completed."""

    def __init__(self, message: str, output: bytes = b""):
        super().__init__(message)
        self.output = bytes(output)


def _stderr_pump(process, timeout_seconds: float) -> bytes | None:
    """Read available stderr bytes; None on timeout, b'' on EOF."""
    if process.stderr is None:
        raise StartupFailure("missing startup channel")
    selector = selectors.DefaultSelector()
    try:
        os.set_blocking(process.stderr.fileno(), False)
        selector.register(process.stderr, selectors.EVENT_READ)
        if selector.select(timeout_seconds):
            return os.read(process.stderr.fileno(), 65536)
    finally:
        os.set_blocking(process.stderr.fileno(), True)
        selector.close()
    return None


def observe_startup(process, *, pump=None,
                    deadline_seconds: float = READY_DEADLINE_SECONDS,
                    liveness_seconds: float = LIVENESS_SECONDS,
                    poll_seconds: float = POLL_SECONDS) -> bytes:
    """Wait for the readiness event, then observe until the liveness deadline.

    Replaces a fixed blind sleep: an early exit is observed as soon as it
    happens, while a healthy helper is still required to remain alive for the
    same 5-second window measured from process launch. The ready marker is
    still mandatory; diagnostics are capped so a noisy helper cannot grow RAM.
    """
    if (not isinstance(liveness_seconds, (int, float))
            or isinstance(liveness_seconds, bool)
            or not 0 < liveness_seconds <= 60):
        raise ValueError("liveness_seconds must be a bounded positive number")
    if (not isinstance(deadline_seconds, (int, float))
            or isinstance(deadline_seconds, bool)
            or not 0 < deadline_seconds <= 120):
        raise ValueError("deadline_seconds must be a bounded positive number")
    if pump is None:
        pump = lambda timeout: _stderr_pump(process, timeout)
    started = time.monotonic()
    deadline = started + deadline_seconds
    captured = bytearray()
    ready = False
    while not ready:
        code = process.poll()
        if code is not None:
            raise StartupFailure("app exited before window readiness",
                                 bytes(captured))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("app did not report window readiness",
                               bytes(captured))
        chunk = pump(max(0.0, min(poll_seconds, remaining)))
        if chunk:
            captured.extend(chunk)
            if len(captured) > MAX_STARTUP_BYTES:
                del captured[:-MAX_STARTUP_BYTES]
            if READY_MARKER in captured:
                ready = True
        elif chunk == b"":
            raise StartupFailure("app closed startup channel before readiness",
                                 bytes(captured))
    if process.poll() is not None:
        raise StartupFailure("app exited at window readiness", bytes(captured))
    remaining = max(0.0, liveness_seconds - (time.monotonic() - started))
    if remaining:
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            pass
    code = process.poll()
    if code is not None:
        raise StartupFailure(f"app exited early ({code})", bytes(captured))
    return bytes(captured)


def main():
    if len(sys.argv) != 2:
        print("Usage: qt_smoke.py /path/to/executable", file=sys.stderr)
        return 2
    exe = Path(sys.argv[1]).resolve()
    if not exe.is_file():
        print(f"Missing executable: {exe}", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env.setdefault("QT_QUICK_BACKEND", "software")
    process = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        try:
            startup_output = observe_startup(process)
        except (StartupFailure, TimeoutError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            output = getattr(exc, "output", b"")
            if isinstance(output, bytes) and output:
                print(output.decode(errors="replace"), file=sys.stderr)
            return 1
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        stderr = startup_output + stderr
        errors = qml_diagnostics(stderr)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            print("FAIL: actionable QML diagnostics detected", file=sys.stderr)
            return 1
        if READY_MARKER not in stderr:
            print(stderr.decode(errors="replace"), file=sys.stderr)
            print("FAIL: Qt process did not confirm a visible QML window", file=sys.stderr)
            return 1
        print("PASS: visible Qt Quick window initialized and remained alive for 5 seconds")
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()

if __name__ == "__main__":
    raise SystemExit(main())
