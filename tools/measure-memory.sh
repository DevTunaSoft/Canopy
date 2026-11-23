#!/usr/bin/env bash
# Sample Linux VmRSS for one PID and write a timestamped CSV with min/avg/max.
# Owner-run only: this was syntax-checked with `bash -n` on Windows but NOT
# executed here (/proc is unavailable). Usage:
#   tools/measure-memory.sh <pid> [duration_seconds] [interval_seconds] [out.csv]
set -euo pipefail

pid="${1:?usage: measure-memory.sh <pid> [duration] [interval] [out.csv]}"
duration="${2:-60}"
interval="${3:-1}"
out="${4:-memory-sample.csv}"

if [ ! -r "/proc/${pid}/status" ]; then
  echo "no readable /proc/${pid}/status (Linux only, check PID)" >&2
  exit 1
fi

printf 'elapsed_s,rss_kb\n' > "$out"
deadline=$(( $(date +%s) + duration ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  rss_kb=$(awk '/^VmRSS:/ {print $2}' "/proc/${pid}/status")
  elapsed=$(( duration - (deadline - $(date +%s)) ))
  printf '%s,%s\n' "$elapsed" "$rss_kb" >> "$out"
  sleep "$interval"
done

awk -F, 'NR>1 {s+=$2; n++; if (n==1||$2<mn) mn=$2; if ($2>mx) mx=$2}
         END {printf "samples=%d min_kb=%d avg_kb=%d max_kb=%d\n", n, mn, s/n, mx}' "$out"
