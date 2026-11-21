#!/usr/bin/env bash
# Package the EXACT CI-compiled Qt6 executable plus its runtime libs for
# independent screenshot reproduction with external approved PNGs.
# The artifact contains no user image assets or licensed wallpaper.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "usage: $0 PATH_TO_COMPILED_BINARY OUTPUT_DIRECTORY" >&2
    exit 2
fi
binary="$(realpath "$1")"
destination="$2"
test -x "$binary"
test ! -e "$destination" || { echo "destination must not exist" >&2; exit 2; }
mkdir -p "$destination/bin" "$destination/lib" "$destination/qml" "$destination/plugins"
cp "$binary" "$destination/bin/canopy-classic-spike"

qtbase="/usr/lib/x86_64-linux-gnu/qt6"
test -d "$qtbase/qml" || { echo "Qt6 QML module directory missing" >&2; exit 3; }
test -d "$qtbase/plugins/platforms" || { echo "Qt6 platform plugin missing" >&2; exit 3; }
cp -a "$qtbase/qml/." "$destination/qml/"
cp -a "$qtbase/plugins/platforms" "$destination/plugins/"
for plugin in imageformats iconengines platformthemes; do
    if [ -d "$qtbase/plugins/$plugin" ]; then
        cp -a "$qtbase/plugins/$plugin" "$destination/plugins/"
    fi
done

# Include Qt6 plus transitive ELF dependencies required by the executable
# and the selected QML/plugins. Linux system libraries are copied by name,
# preserving the SONAME expected by the loader. No root installs needed.
while IFS= read -r dependency; do
    case "$dependency" in
        /lib/*|/usr/lib/*)
            # Never ship glibc from Ubuntu in a portable runtime. Mixing a
            # foreign libc with the host loader breaks even compatible hosts.
            case "$(basename "$dependency")" in
                libc.so.*|libm.so.*|libpthread.so.*|libdl.so.*|librt.so.*|libresolv.so.*|libnss_*.so.*|libutil.so.*|ld-linux*.so.*)
                    continue ;;
            esac
            target="$destination/lib/$(basename "$dependency")"
            if [ ! -e "$target" ]; then
                cp -L "$dependency" "$target"
            fi
            ;;
    esac
done < <(
    find "$destination/bin" "$destination/qml" "$destination/plugins" -type f \
        \( -name '*.so' -o -name '*.so.*' -o -name 'canopy-classic-spike' \) -print0 |
    xargs -0 -r -n1 ldd 2>/dev/null |
    awk '$2 == "=>" && $3 ~ /^\// {print $3}' | sort -u
)

cat >"$destination/run-canopy.sh" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export LD_LIBRARY_PATH="$ROOT/lib:${LD_LIBRARY_PATH:-}"
export QT_PLUGIN_PATH="$ROOT/plugins"
export QML_IMPORT_PATH="$ROOT/qml"
export QT_QML_IMPORT_PATH="$ROOT/qml"
export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
exec "$ROOT/bin/canopy-classic-spike" "$@"
LAUNCH
chmod +x "$destination/run-canopy.sh"
echo 'CANOPY_PORTABLE_QT_BUNDLE_CREATED'
du -sh "$destination"
