#!/usr/bin/env bash
# Read-only-to-session acceptance capture for an installed Linux Mint VM.
# Creates a throwaway build and evidence files; never installs packages or
# changes login/session settings, wallpaper preferences, or desktop services.
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage: bash tools/mint_vm_capture.sh WALLPAPER.png [APPROVED_ART_DIR] [EVIDENCE_DIR]

Run from a normal graphical Linux Mint guest session. WALLPAPER must be an
original/redistribution-licensed landscape photo that meets Canopy validation.
An optional approved-art directory enables the eight selected SHA-locked PNGs;
otherwise the six unapproved engineering icon candidates are used.
This checks a standalone Qt window only. It is NOT Mint shell approval.
USAGE
}
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then usage; exit 0; fi
if [[ "$#" -lt 1 || "$#" -gt 3 ]]; then usage >&2; exit 2; fi
if [[ ! -r /etc/os-release ]]; then
  echo "BLOCKED: cannot verify Linux Mint guest" >&2; exit 2
fi
# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" != "linuxmint" ]]; then
  echo "BLOCKED: run only inside the Linux Mint guest, not an Ubuntu Actions runner" >&2
  exit 2
fi
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "BLOCKED: requires a real interactive graphical Mint session" >&2; exit 2
fi
for tool in cmake python3 timeout git; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "BLOCKED: missing $tool (install dependencies manually in the guest)" >&2
    exit 2
  fi
done

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
WALLPAPER="$(realpath -e -- "$1")"
ART="${2:-}"
if [[ -n "$ART" ]]; then ART="$(realpath -e -- "$ART")"; fi
EVIDENCE="${3:-${HOME}/canopy-mint-evidence}"
mkdir -p -- "$EVIDENCE"
EVIDENCE="$(cd -- "$EVIDENCE" && pwd -P)"
BUILD="$ROOT/build/mint-vm-acceptance"
APP="$BUILD/canopy-classic-spike"
ARGS=(--landscape-wallpaper "$WALLPAPER")
if [[ -n "$ART" ]]; then ARGS+=(--approved-art-dir "$ART" --self-test-approved); fi

{
  printf 'Canopy standalone Mint VM capture (not session acceptance)\n'
  printf 'Captured: %s\n' "$(date -Is)"
  printf 'Git ref: %s\n' "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo 'not a git checkout')"
  printf 'Mint: %s\n' "${PRETTY_NAME:-unknown}"
  printf 'Kernel: %s\n' "$(uname -r)"
  printf 'Session: %s\n' "${XDG_SESSION_TYPE:-unknown}"
  printf 'Wallpaper: externally supplied and validated by Canopy at launch\n'
  printf 'Icon mode: %s\n' "$(if [[ -n "$ART" ]]; then echo 'eight approved SHA-locked PNGs'; else echo 'six unapproved engineering SVGs'; fi)"
} >"$EVIDENCE/environment.txt"

echo "Building standalone Classic Qt executable (no system installation)"
cmake -S "$ROOT/prototype/classic" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release >"$EVIDENCE/configure.log" 2>&1 ||
  { tail -n 60 "$EVIDENCE/configure.log" >&2; exit 1; }
cmake --build "$BUILD" --parallel 2 >"$EVIDENCE/compile.log" 2>&1 ||
  { tail -n 60 "$EVIDENCE/compile.log" >&2; exit 1; }

capture() {
  local name="$1" width="$2" height="$3"
  shift 3
  local log="$EVIDENCE/$name.log" png="$EVIDENCE/$name.png"
  if ! timeout 60s "$APP" "${ARGS[@]}" "$@" \
      --self-test-size "${width}x${height}" --self-test-screenshot "$png" >"$log" 2>&1; then
    echo "FAIL: $name runtime; evidence: $log" >&2
    tail -n 80 "$log" >&2
    return 1
  fi
  grep -q "SELF_TEST_PASS: validated custom landscape wallpaper loaded" "$log" ||
    { echo "FAIL: wallpaper decode not confirmed in $log" >&2; return 1; }
  python3 "$ROOT/tools/check_screenshot.py" "$png" "$width" "$height"
  echo "PASS: $name ($width x $height)"
}

capture desktop-1200 1200 750
capture launcher-1200 1200 750 --self-test-launcher
capture launcher-compact 760 500 --self-test-launcher
capture launcher-search-files 1200 750 --self-test-launcher --self-test-launcher-filter-files
if command -v xrandr >/dev/null 2>&1 &&
   xrandr --current 2>/dev/null | grep -Eq '1920x1080[[:space:]]+[0-9]'; then
  capture desktop-1080p 1920 1080
else
  echo "SKIP: 1920x1080; set the guest display resolution before a full-HD capture" |
    tee "$EVIDENCE/high-dpi-manual-review.txt"
fi

# Informational ten-second baseline using the actual selected wallpaper and
# selected icon mode. This does not replace a five-minute Mint idle review.
MEASURE=(python3 "$ROOT/tools/measure_qt.py" "$APP" "$EVIDENCE/short-baseline.json"
         --seconds 10 --landscape-wallpaper "$WALLPAPER")
if [[ -n "$ART" ]]; then MEASURE+=(--approved-art-dir "$ART"); fi
"${MEASURE[@]}" >"$EVIDENCE/baseline.log" 2>&1 ||
  echo "WARN: informational baseline unavailable; see baseline.log" >&2

printf '\nPASS: standalone Mint capture completed. Evidence: %s\n' "$EVIDENCE"
printf '%s\n' "NOT VERIFIED: login/reboot, high-DPI inspection, five-minute idle, aesthetic approval, or real shell."
