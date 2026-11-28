#!/usr/bin/env bash
# Host-side bounded native Plasma soak driver.
#
# Usage (from repository root):
#   DURATION=3600 INTERVAL=60 bash tools/stability/run_native_soak.sh
#
# Uses the pre-existing NAT SSH forward and read-only guest sampler; no VM
# start/stop/snapshot/revert, no guest package/service/settings mutation.
# All output stays under scratch/native_stability/raw.
set -u

DURATION="${DURATION:-3600}"
INTERVAL="${INTERVAL:-60}"
LABEL="${LABEL:-NATIVE_SOAK_BOUNDED}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/scratch/native_stability/raw"
KEY="${KEY:-C:/Users/X1/AppData/Local/hermes/cache/scratch/g1_ubuntu_evidence/ssh/g1_ed25519}"
VBM="${VBM:-/c/Program Files/Oracle/VirtualBox/VBoxManage.exe}"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
     -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
     -p 2223 canopy@127.0.0.1)

mkdir -p "$OUT"
RAW="$OUT/soak.tsv"
ERR="$OUT/soak.err"
META="$OUT/soak.meta"
PRE="$OUT/preflight.txt"
JSON="$OUT/soak.json"

{
  echo "UTC_LAUNCH=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "DURATION_S=$DURATION"
  echo "INTERVAL_S=$INTERVAL"
  echo "LABEL=$LABEL"
  echo "BASE_SHA=ec910d7a7275296ecbc8b5e5c459d356205165d1"
  echo "DIRECTIVE_SHA_PREFIX=79e30d79"
  echo "VM_NAME=Canopy-Test-Plasma6"
  echo "VM_UUID=3aecd840-4dd6-4481-913f-64a289da406d"
  echo "SAMPLER_CMD=ssh -i \$KEY -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 2223 canopy@127.0.0.1 'python3 - $DURATION $INTERVAL $LABEL' < tools/stability/native_soak_sampler.py > scratch/native_stability/raw/soak.tsv 2> scratch/native_stability/raw/soak.err"
  echo "REPORT_CMD=python3 tools/stability/native_soak_report.py scratch/native_stability/raw/soak.tsv scratch/native_stability/raw/soak.json"
  echo "KEY_PATH=$KEY (pre-existing scratch key; private material not committed)"
} > "$META"

{
  echo "=== VBoxManage showvminfo (filtered) ==="
  "$VBM" showvminfo Canopy-Test-Plasma6 --machinereadable 2>&1 \
    | grep -Ei '^(VMState|VMStateChangeTime|memory|cpus|Forwarding|OSType|GuestAdditionsVersion)='
  echo "=== guest preflight ==="
  "${SSH[@]}" 'date -u +%Y-%m-%dT%H:%M:%SZ; hostname; uptime; free -m | head -3; pgrep -af "canopy-classic|kwin_x11|plasmashell|startplasma-x11|native-task-harness" | head -12; echo "---coredump baseline---"; coredumpctl list --no-pager 2>&1 | tail -8' 2>&1
  echo "=== host snapshot ==="
  ps -ef 2>/dev/null | grep -Ei 'vbox|build|qmake|ninja|cmake' | grep -v grep | head -15 || true
} > "$PRE" 2>&1

echo "UTC_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$META"

# Long-running SSH session; output is flushed by the guest sampler per sample.
"${SSH[@]}" "python3 - $DURATION $INTERVAL $LABEL" \
  < "$ROOT/tools/stability/native_soak_sampler.py" > "$RAW" 2> "$ERR"
rc=$?

echo "UTC_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$META"
echo "SAMPLER_RC=$rc" >> "$META"
echo "RAW_LINES=$(wc -l < "$RAW")" >> "$META"

if [ "$rc" -eq 0 ]; then
  (cd "$ROOT" && python3 tools/stability/native_soak_report.py \
      scratch/native_stability/raw/soak.tsv scratch/native_stability/raw/soak.json) \
      > "$OUT/report_stdout.txt" 2> "$OUT/report_stderr.txt"
  echo "REPORT_RC=$?" >> "$META"
fi
echo "UTC_DONE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$META"
exit "$rc"
