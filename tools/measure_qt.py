#!/usr/bin/env python3
"""Collect a bounded, informational Qt process baseline on Linux.

This is not a release threshold or a five-minute idle benchmark.
No shell commands and no elevated privileges are required.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def read_pss_kib(pid: int) -> int:
    path = Path(f"/proc/{pid}/smaps_rollup")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Pss:"):
            return int(line.split()[1])
    raise ValueError("Pss field missing")


def read_cpu_ticks(pid: int) -> int:
    # The comm field in /proc/PID/stat may contain spaces or parentheses.
    record = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    end = record.rfind(")")
    if end < 0:
        raise ValueError("Malformed process stat")
    fields_after_comm = record[end + 2:].split()
    return int(fields_after_comm[11]) + int(fields_after_comm[12])


def measure(exe: Path, duration: float, app_args: tuple[str, ...] = ()) -> dict:
    if not exe.is_file():
        raise FileNotFoundError(exe)
    process = subprocess.Popen([str(exe), *app_args], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, env=os.environ.copy())
    try:
        # Read the pipe at the file-descriptor level. Buffered readline() can
        # swallow several QML warnings and the readiness marker in one read,
        # leaving select() waiting even though Python already buffered it.
        import select
        deadline = time.monotonic() + 12
        stderr_tail = bytearray()
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Canopy exited early: {process.returncode}; stderr: {stderr_tail.decode(errors='replace')[-1000:]}")
            if process.stderr is None:
                raise RuntimeError("Missing startup channel")
            ready, _, _ = select.select([process.stderr.fileno()], [], [], 0.25)
            if ready:
                chunk = os.read(process.stderr.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("Canopy closed startup channel")
                stderr_tail.extend(chunk)
                if len(stderr_tail) > 65536:
                    del stderr_tail[:-65536]
                if b"CANOPY_CLASSIC_WINDOW_READY" in stderr_tail:
                    break
        else:
            raise TimeoutError(f"Canopy did not report window readiness; stderr: {stderr_tail.decode(errors='replace')[-1000:]}")
        ticks_start = read_cpu_ticks(process.pid)
        pss_start = read_pss_kib(process.pid)
        started = time.monotonic()
        time.sleep(duration)
        if process.poll() is not None:
            raise RuntimeError(f"Canopy exited during sample: {process.returncode}")
        elapsed = time.monotonic() - started
        ticks_end = read_cpu_ticks(process.pid)
        pss_end = read_pss_kib(process.pid)
        tick_rate = os.sysconf("SC_CLK_TCK")
        return {
            "schema": 1,
            "kind": "short-headless-baseline-not-mint-acceptance",
            "duration_seconds": round(elapsed, 3),
            "cpu_percent_one_core": round(100 * (ticks_end - ticks_start) / tick_rate / elapsed, 3),
            "pss_kib_start": pss_start,
            "pss_kib_end": pss_end,
            "backend": os.environ.get("QT_QUICK_BACKEND", "default"),
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--landscape-wallpaper", type=Path)
    parser.add_argument("--approved-art-dir", type=Path)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 30:
        parser.error("--seconds must be between 1 and 30")
    try:
        app_args = []
        if args.landscape_wallpaper:
            app_args.extend(("--landscape-wallpaper", str(args.landscape_wallpaper.resolve())))
        if args.approved_art_dir:
            app_args.extend(("--approved-art-dir", str(args.approved_art_dir.resolve())))
        data = measure(args.executable.resolve(), args.seconds, tuple(app_args))
        data["artwork_mode"] = "external-landscape" if args.landscape_wallpaper else "legacy-demo"
        data["approved_icon_mode"] = bool(args.approved_art_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
