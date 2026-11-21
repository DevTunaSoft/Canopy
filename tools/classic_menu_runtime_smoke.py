#!/usr/bin/env python3
"""End-to-end, disposable Linux X11 menu launch of the ACTUAL compiled Qt UI.

Runs only under an existing graphical display (normally GitHub's Xvfb).
Does not install a desktop session, replace Cinnamon or use any real user
applications. Uses the project's existing user-menu registration code and
removes the registration after testing. Never run with sudo.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

from tools import register_classic_preview as menu


class MenuRuntimeError(ValueError):
    """An explicit smoke acceptance condition was not met."""


def verified_executable(path, expected_sha=None):
    exe = Path(path)
    if not exe.is_absolute() or exe.is_symlink() or not exe.is_file():
        raise MenuRuntimeError("binary must be an absolute, regular, non-symlink file")
    if not os.access(exe, os.X_OK):
        raise MenuRuntimeError("binary must be executable")
    if expected_sha is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise MenuRuntimeError("expected binary SHA-256 must be 64 lowercase hex")
        digest = hashlib.sha256(exe.read_bytes()).hexdigest()
        if digest != expected_sha:
            raise MenuRuntimeError("binary does not match pinned SHA-256")
    before = exe.stat()
    if not stat.S_ISREG(before.st_mode):
        raise MenuRuntimeError("binary is not regular")
    return (before.st_dev, before.st_ino)


def _matching_pids(exe_identity):
    """Identify ONLY current-UID processes running this exact inode."""
    ids = set()
    if not Path("/proc").is_dir():
        raise MenuRuntimeError("Linux /proc is required for process isolation")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            st = (proc / "exe").stat()
            if (st.st_dev, st.st_ino) == exe_identity:
                ids.add(int(proc.name))
        except (OSError, ValueError):
            continue
    return ids


def _has_window():
    result = subprocess.run(
        ["xwininfo", "-root", "-tree"], capture_output=True,
        text=True, timeout=3, check=False, errors="replace",
    )
    if result.returncode != 0:
        return False
    # A newly started process of our exact binary must exist *as well*;
    # a coincidentally named unrelated window alone is never sufficient.
    return any("Canopy Classic" in line and "Technology Spike" in line
               for line in result.stdout.splitlines() if len(line) < 2000)


def _stop_new_processes(ids, exe_identity):
    """Only touch new exact-inode child PIDs, never previous user programs."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in ids:
            if pid not in _matching_pids(exe_identity):
                continue
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                continue
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not (_matching_pids(exe_identity) & ids):
                return
            time.sleep(0.1)
    if _matching_pids(exe_identity) & ids:
        raise MenuRuntimeError("test Qt process did not terminate")


def run(binary, *, expected_sha=None, timeout=8):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise MenuRuntimeError("never run this test as root")
    if not os.environ.get("DISPLAY"):
        raise MenuRuntimeError("isolated graphical DISPLAY is required")
    if not (2 <= timeout <= 12):
        raise MenuRuntimeError("timeout outside safe bounds (2-12 seconds)")
    for required in ("gio", "xwininfo", "desktop-file-validate"):
        if not shutil.which(required):
            raise MenuRuntimeError("required verifier unavailable: " + required)
    identity = verified_executable(binary, expected_sha)
    previously_running = _matching_pids(identity)
    new_pids = set()
    with tempfile.TemporaryDirectory(prefix="canopy-real-menu-qa-") as root:
        data = Path(root) / "share"
        data.mkdir(mode=0o700)
        old_xdg = os.environ.get("XDG_DATA_HOME")
        env = dict(os.environ, XDG_DATA_HOME=str(data))
        try:
            desktop = menu.install(data, binary)
            if menu.status(data) != "INSTALLED":
                raise MenuRuntimeError("desktop entry is not exactly owned")
            valid = subprocess.run(
                ["desktop-file-validate", str(desktop)],
                capture_output=True, timeout=5, check=False,
            )
            if valid.returncode:
                raise MenuRuntimeError("desktop entry failed freedesktop validation")
            # GIO executes the original entry, which points directly to the
            # real compiled Qt executable, not a shell script or mock.
            requested = subprocess.run(
                ["gio", "launch", str(desktop)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env, timeout=5, check=False,
            )
            if requested.returncode:
                raise MenuRuntimeError("GIO rejected the actual Qt menu entry")
            deadline = time.monotonic() + timeout
            visible = False
            while time.monotonic() < deadline:
                new_pids |= _matching_pids(identity) - previously_running
                if new_pids and _has_window():
                    # Verify it stays live, rather than instantly crashing.
                    time.sleep(0.25)
                    visible = bool(_matching_pids(identity) & new_pids)
                    if visible:
                        break
                time.sleep(0.15)
            if not visible:
                raise MenuRuntimeError("compiled Qt process/window not observed")
            if menu.status(data) != "INSTALLED":
                raise MenuRuntimeError("owned desktop entry changed during launch")
            # The Qt window is genuinely live and in the X11 window tree.
            return {
                "kind": "compiled-qt-from-disposable-linux-menu",
                "status": "PASS",
                "actual_gui_window_observed": True,
                "installed_system_wide": False,
                "real_mint_guest_acceptance": False,
                "window_manager_replaced": False,
            }
        finally:
            # Exclude every process which predates this run. Do not send
            # signals to any other app, even one with the same name.
            try:
                new_pids |= _matching_pids(identity) - previously_running
                _stop_new_processes(new_pids, identity)
            finally:
                if menu.status(data) == "INSTALLED":
                    menu.uninstall(data)
                # TemporaryDirectory deletes only its isolated test folder.
                # os.environ was never mutated (only the child env was).
                assert os.environ.get("XDG_DATA_HOME") == old_xdg


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256")
    parser.add_argument("--timeout", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        result = run(
            args.binary, expected_sha=args.expected_binary_sha256,
            timeout=args.timeout,
        )
        print("CLASSIC_REAL_MENU_QT_PASS: actual compiled Qt window from "
              "temporary GIO desktop entry; Cinnamon/session unchanged")
        return 0
    except (MenuRuntimeError, menu.RegistrationError,
            OSError, subprocess.TimeoutExpired) as exc:
        print("CLASSIC_REAL_MENU_QT_FAIL:", type(exc).__name__,
              str(exc)[:180], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
