#!/usr/bin/env python3
"""Canopy read-only Linux desktop process baseline (Python stdlib)."""
import argparse
import json
import os
from pathlib import Path
import platform
import time

NAMES = frozenset(("plasmashell", "kwin_wayland", "kwin_x11", "cinnamon",
                   "muffin", "xfce4-panel", "xfwm4", "mate-panel", "marco",
                   "nemo", "dolphin", "ksmserver", "kded6", "ksystemstats"))

def parse_meminfo(text):
    result = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        parts = val.split()
        if parts and parts[0].isdigit():
            result[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == 'kB' else 1)
    return result

def parse_stat(text):
    # /proc/PID/stat comm can contain spaces and parentheses.
    pos = text.rfind(')')
    if pos < 0:
        raise ValueError('invalid stat')
    tail = text[pos + 2:].split()
    return (int(tail[11]) + int(tail[12]), int(tail[21]))

def sample(root=Path('/proc')):
    processes = {}
    for folder in root.iterdir():
        if not folder.name.isdigit():
            continue
        try:
            name = (folder / 'comm').read_text().strip()
            if name not in NAMES:
                continue
            ticks, rss_pages = parse_stat((folder / 'stat').read_text())
            pss_bytes = None
            try:
                for line in (folder / 'smaps_rollup').read_text().splitlines():
                    if line.startswith('Pss:'):
                        pss_bytes = int(line.split()[1]) * 1024
                        break
            except (OSError, ValueError, IndexError):
                pass
            processes[folder.name] = (name, ticks, rss_pages, pss_bytes)
        except (OSError, ValueError, IndexError):
            pass  # Process disappeared or access denied.
    return processes

def capture(seconds=2.0, root=Path('/proc')):
    initial = sample(root)
    start = time.monotonic()
    time.sleep(seconds)
    elapsed = time.monotonic() - start
    current = sample(root)
    pagesize = os.sysconf('SC_PAGE_SIZE')
    hz = os.sysconf('SC_CLK_TCK')
    items = []
    for pid, (name, ticks, rss, pss) in sorted(current.items(), key=lambda p: int(p[0])):
        before = initial.get(pid)
        cpu = None
        if before and before[0] == name and elapsed > 0:
            cpu = round(max(0, ticks - before[1]) * 100 / hz / elapsed, 3)
        items.append({'pid': int(pid), 'name': name, 'cpu_percent_one_core': cpu,
                      'rss_bytes': rss * pagesize, 'pss_bytes': pss})
    info = parse_meminfo((root / 'meminfo').read_text())
    return {'schema_version': 1, 'captured_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'platform': platform.platform(), 'desktop': os.getenv('XDG_CURRENT_DESKTOP', 'unknown'),
            'session_type': os.getenv('XDG_SESSION_TYPE', 'unknown'),
            'sampling_seconds': round(elapsed, 3),
            'mem_total_bytes': info.get('MemTotal'),
            'mem_available_bytes': info.get('MemAvailable'), 'processes': items,
            'limitations': ['Only selected named desktop processes are included',
                            'PSS may be unavailable due to access permissions',
                            'Short CPU sample is not a long-term idle average',
                            'GPU memory and compositor frame times are not measured',
                            'PID reuse may affect short-lived process samples']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=2.0)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error('--seconds must be between 1 and 60')
    if platform.system() != 'Linux':
        parser.error('Linux /proc required')
    output = json.dumps(capture(args.seconds), indent=2) + '\n'
    if args.output:
        args.output.write_text(output, encoding='utf-8')
    else:
        print(output, end='')

if __name__ == '__main__':
    main()
