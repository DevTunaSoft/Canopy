#!/usr/bin/env bash
# Remaster a verified Mint 22.3 ISO for a DISPOSABLE VirtualBox test VM.
# Never boot this image on a physical computer: installer may erase its disk.
set -euo pipefail
if [[ $# -ne 3 ]]; then echo "Usage: $0 SOURCE.iso EXPECTED_SHA256 OUTPUT.iso" >&2; exit 2; fi
source_iso=$(realpath "$1"); expected=$2; output=$(realpath -m "$3")
[[ "$expected" =~ ^[[:xdigit:]]{64}$ ]] || { echo "Invalid SHA256" >&2; exit 2; }
[[ "$source_iso" != "$output" ]] || { echo "Output must differ from source" >&2; exit 2; }
[[ ! -e "$output" ]] || { echo "Refusing to overwrite existing output" >&2; exit 2; }
# Never allow the output path to be a symlink or the input path to be missing.
[[ -f "$source_iso" && ! -L "$output" ]] || { echo "Invalid source or output path" >&2; exit 2; }
[[ "$(dirname "$output")" != "/" ]] || { echo "Refusing output in filesystem root" >&2; exit 2; }
[[ $(sha256sum "$source_iso" | cut -d' ' -f1) == "${expected,,}" ]] || { echo "ISO hash mismatch" >&2; exit 1; }
for cmd in xorriso python3 openssl; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }; done
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
tmp=$(mktemp -d)
completed=0
cleanup() {
  if [[ "$completed" -ne 1 ]]; then rm -f -- "$output"; fi
  rm -rf -- "$tmp"
}
trap cleanup EXIT
mkdir -p "$tmp/boot/grub" "$tmp/preseed"
# Ensure the source ISO has replayable boot metadata before modifying anything.
xorriso -indev "$source_iso" -report_el_torito as_mkisofs >"$tmp/boot-options.txt" 2>"$tmp/boot-options-errors.txt"
if ! grep -Eq -- "(^-b | -eltorito-boot | -e )" "$tmp/boot-options.txt"; then
  echo "Cannot verify source El Torito boot metadata" >&2; exit 1
fi
# Detect BIOS ISOLINUX/SYSLINUX boot media and patch its actual menu as well.
bios_isolinux=0
if grep -Eq -- '(^|[[:space:]])-b[[:space:]]+[^[:space:]]*(isolinux|syslinux)' "$tmp/boot-options.txt"; then
  bios_isolinux=1
  mkdir -p "$tmp/isolinux"
  if ! xorriso -osirrox on -indev "$source_iso" -extract /isolinux/isolinux.cfg "$tmp/isolinux/isolinux.cfg" >/dev/null 2>&1; then
    echo "BLOCKED: BIOS ISOLINUX boot image lacks /isolinux/isolinux.cfg" >&2
    exit 1
  fi
  python3 "$here/Patch-CanopyBiosMenu.py" "$tmp/isolinux/isolinux.cfg"
fi
# Read the source boot menu, preserving the ISO's native hybrid boot records.
xorriso -osirrox on -indev "$source_iso" -extract /boot/grub/grub.cfg "$tmp/boot/grub/grub.cfg" >/dev/null
python3 "$here/Generate-CanopyMintPreseed.py" "$tmp/preseed/canopy.seed" --disposable-vm
python3 - "$tmp/boot/grub/grub.cfg" <<'PY'
from pathlib import Path
import re
import sys
path = Path(sys.argv[1])
original = path.read_text(encoding="utf-8")
# Only support a known casper Linux kernel line, rather than silently emitting
# an image whose automatic installation does not start.
match = re.search(r"(?m)^\s*linux(?:efi)?\s+(/casper/vmlinuz\S*)\s+([^\n]*)$", original)
if not match:
    raise SystemExit("Unsupported GRUB menu: no /casper/vmlinuz entry")
kernel, args = match.groups()
initrd_match = re.search(r"(?m)^\s*initrd(?:efi)?\s+(/casper/initrd\S*)\s*$", original)
if not initrd_match:
    raise SystemExit("Unsupported GRUB menu: no /casper/initrd entry")
initrd = initrd_match.group(1)
args = re.sub(r"\s+quiet\b|\s+splash\b", "", args)
args = args.replace("---", " ")
args = args.strip()
menu = (
    "set timeout=1\n"
    "set default=0\n"
    "menuentry 'Canopy disposable VM automatic installation' {\n"
    f"    linux {kernel} {args} automatic-ubiquity only-ubiquity "
    "file=/cdrom/preseed/canopy.seed noprompt ---\n"
    f"    initrd {initrd}\n"
    "}\n"
)
# Original boot menu remains available for inspection/recovery.
path.write_text(menu + "\n" + original, encoding="utf-8")
PY
# Replay original El Torito and system-area boot equipment instead of guessing
# boot image offsets. Replay must succeed or output is rejected.
map_bios=()
if [[ "$bios_isolinux" -eq 1 ]]; then
  map_bios=(-map "$tmp/isolinux/isolinux.cfg" /isolinux/isolinux.cfg)
fi
xorriso -indev "$source_iso" -outdev "$output" \
  "${map_bios[@]}" \
  -map "$tmp/boot/grub/grub.cfg" /boot/grub/grub.cfg \
  -map "$tmp/preseed/canopy.seed" /preseed/canopy.seed \
  -boot_image any replay -commit -end
# Verify the resulting image contains the expected boot menu and seed.
xorriso -osirrox on -indev "$output" -extract /boot/grub/grub.cfg "$tmp/check-grub.cfg" \
  -extract /preseed/canopy.seed "$tmp/check-seed" >/dev/null
grep -q 'automatic-ubiquity' "$tmp/check-grub.cfg"
grep -q 'partman/confirm' "$tmp/check-seed"
if [[ "$bios_isolinux" -eq 1 ]]; then
  xorriso -osirrox on -indev "$output" -extract /isolinux/isolinux.cfg "$tmp/check-bios.cfg" >/dev/null
  grep -q 'canopy-auto' "$tmp/check-bios.cfg"
fi
# Verify the output still advertises boot images after remastering.
xorriso -indev "$output" -report_el_torito plain >"$tmp/output-boot.txt" 2>&1
if ! grep -qi "El Torito" "$tmp/output-boot.txt"; then
  rm -f -- "$output"
  echo "Remastered image lacks verifiable El Torito metadata; deleted unsafe output" >&2; exit 1
fi
completed=1
echo "Created test-only ISO: $output"
echo "WARNING: NOT verified to install Mint. Never boot on a physical computer."
