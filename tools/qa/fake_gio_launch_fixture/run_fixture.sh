#!/usr/bin/env bash
# Bounded, deterministic fake-GIO fixture runner for Canopy Classic.
# Reads production sources from a git object only (default HEAD), verifies
# their exact SHA-256, builds two Qt6::Core binaries against a fake GIO shim,
# and gates on 11 mapping/refusal cases + 1 no-GIO refusal case.
#
# No GLib/GIO dev package, desktop database, real launch or X server is used.
# No tracked repository file is written: exports and logs live under OUTPUT_DIR.
# This is SYNTHETIC evidence; it is not Linux Mint and not desktop acceptance.
set -euo pipefail

FIXTURE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${REPO:-${GITHUB_WORKSPACE:-.}}"
TIP="${TIP:-HEAD}"
OUTPUT_DIR="${OUTPUT_DIR:-${RUNNER_TEMP:-/tmp}/canopy-fake-gio-launch-fixture}"

to_native() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

FIXTURE_NATIVE="$(to_native "$FIXTURE_DIR")"
SRC="$OUTPUT_DIR/src"
BUILD="$OUTPUT_DIR/build"
SRC_NATIVE="$(to_native "$SRC")"
BUILD_NATIVE="$(to_native "$BUILD")"

mkdir -p "$SRC" "$BUILD"

echo "STAGE 1: export exact production sources from $TIP (git objects, read-only)"
git -C "$REPO" rev-parse --verify "$TIP^{commit}" >/dev/null
git -C "$REPO" show "$TIP:prototype/classic/SystemAppLauncher.cpp" > "$SRC/SystemAppLauncher.cpp"
git -C "$REPO" show "$TIP:prototype/classic/SystemAppLauncher.h" > "$SRC/SystemAppLauncher.h"
(cd "$SRC" && sha256sum SystemAppLauncher.cpp SystemAppLauncher.h) \
  | tee "$OUTPUT_DIR/source-sha256-check.txt"
(cd "$SRC" && sha256sum -c "$FIXTURE_DIR/expected-source-sha256.txt") \
  | tee "$OUTPUT_DIR/source-sha256-verify.txt"

EXE_SUFFIX=""
case "$(uname -s)" in
  MINGW*|MSYS*) EXE_SUFFIX=".exe" ;;
esac

echo "STAGE 2: configure with Qt6 Core + AUTOMOC (no GLib/GIO dev package needed)"
EXTRA=()
case "$(uname -s)" in
  MINGW*|MSYS*)
    if [ -x /c/msys64/ucrt64/bin/cmake.exe ]; then
      export PATH="/c/msys64/ucrt64/bin:$PATH"
      EXTRA+=("-DCMAKE_PREFIX_PATH=C:/msys64/ucrt64")
    fi
    ;;
esac
cmake -S "$FIXTURE_NATIVE" -B "$BUILD_NATIVE" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  "-DLAUNCHER_SRC_DIR=$SRC_NATIVE" "${EXTRA[@]}" 2>&1 \
  | tee "$OUTPUT_DIR/configure.log"

echo "STAGE 3: build fake-GIO library, mapped-launch binary, no-GIO binary"
cmake --build "$BUILD_NATIVE" --parallel 2 2>&1 | tee "$OUTPUT_DIR/build.log"

echo "STAGE 4: run target-mapping and refusal cases"
LOG="$OUTPUT_DIR/fake-gio.log"
LOG_NATIVE="$(to_native "$LOG")"
"$BUILD_NATIVE/gio_fixture${EXE_SUFFIX}" "$LOG_NATIVE" 2>&1 \
  | tee "$OUTPUT_DIR/gio-fixture.log"
"$BUILD_NATIVE/gio_fixture_fallback${EXE_SUFFIX}" "$LOG_NATIVE" 2>&1 \
  | tee "$OUTPUT_DIR/gio-fallback.log"

echo "STAGE 5: verify all case summaries"
grep -q 'SUMMARY: cases=11 result=ALL_PASS' "$OUTPUT_DIR/gio-fixture.log"
grep -q 'SUMMARY: cases=1 result=ALL_PASS' "$OUTPUT_DIR/gio-fallback.log"
cp "$LOG" "$OUTPUT_DIR/fake-gio-call-log.txt"

echo "CLASSIFICATION: SYNTHETIC fake GIO shim; no real GLib/GIO, no desktop database"
echo "NOT_MINT: no Linux Mint guest, real desktop session or application launch here"
echo "GIO_LAUNCH_FIXTURE_PASS: 6 dock mappings, 1 fallback order, 4 GIO refusals, 1 no-GIO refusal"
