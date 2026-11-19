#!/usr/bin/env python3
"""Run a Qt app under Xvfb and require it to stay alive until terminated."""
import os
from pathlib import Path
import subprocess
import sys
import time

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
        time.sleep(5)
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=3)
            print(stdout.decode(errors="replace"))
            print(stderr.decode(errors="replace"), file=sys.stderr)
            print(f"FAIL: app exited early ({process.returncode})", file=sys.stderr)
            return 1
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        if b"CANOPY_CLASSIC_WINDOW_READY" not in stderr:
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
